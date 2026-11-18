"""Run Docling OCR engines over the matched clean/degraded pages and score them.

  .venv/bin/python -I scripts/run_eval.py                       # all CPU engines, all pages
  .venv/bin/python -I scripts/run_eval.py --engines ocrmac --limit-pages 10
  .venv/bin/python -I scripts/run_eval.py --aggregate-only      # rebuild results/ from saved predictions

Each engine runs in its own subprocess (in parallel), converts every page image with Docling's
standard pipeline (layout + OCR, full-page OCR forced, table structure off), and saves the OCR
text-line cells. Scoring is done afterwards from the saved predictions, so it is cheap to change
matching rules and re-aggregate. Outputs:

  results/predictions/<engine>/<page_id>.<condition>.json   OCR cells (px, top-left) + page text
  results/predictions/<engine>/<page_id>.<condition>.dclg   Docling output serialised as DocLang
  results/page_scores.jsonl                                 per page x engine scores + per-field detail
  results/metrics.json                                      aggregates (engine x condition, x script, x family)
  results/run_meta.json                                     versions, settings, counts, timings, skipped engines
  results/SUMMARY.md                                        human-readable tables
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RES = ROOT / "results"
PRED = RES / "predictions"

CPU_ENGINES = ["ocrmac", "rapidocr", "easyocr", "tesseract"]

# Language per engine and script. None = the engine has no model for this script on this setup.
LANGS = {
    "ocrmac":    {"Latin": ["en-US"], "Devanagari": None, "Bengali": None},
    "rapidocr":  {"Latin": ["en"], "Devanagari": ["devanagari"], "Bengali": None},
    "easyocr":   {"Latin": ["en"], "Devanagari": ["hi", "en"], "Bengali": ["bn", "en"]},
    "tesseract": {"Latin": ["eng"], "Devanagari": ["hin", "mar", "eng"], "Bengali": ["ben", "eng"]},
}
EASYOCR_MARATHI = ["mr", "en"]

SKIPPED_ALWAYS = {
    "paddleocr": "Not run on this Mac by policy (too heavy locally); not a built-in Docling OCR engine.",
    "nemotron_ocr": "NVIDIA Nemotron-OCR targets CUDA GPUs; not runnable on a Mac CPU.",
    "kserve_v2": "Remote inference service, not a local engine.",
    "auto": "OcrAutoOptions only picks one of the engines above; it would duplicate a row.",
    "vlm_presets (minicpm_ocr, granite_docling, glm_ocr, lightonocr, dots_ocr, ...)":
        "VLM conversion presets, not OCR-engine presets; 0.3B-27B parameter models that need a GPU "
        "(or many minutes per page on CPU). MiniCPM-OCR (added in v2.149.0) is proposed for a GPU run, see REVIEW_NOTES.md.",
}


# ============================================================== prediction (worker)
def engine_available(engine: str) -> tuple[bool, str]:
    if engine == "ocrmac":
        if platform.system() != "Darwin":
            return False, "ocrmac needs macOS (Apple Vision)."
        try:
            import ocrmac  # noqa: F401
        except Exception as e:  # pragma: no cover
            return False, f"ocrmac not importable: {e}"
        return True, ""
    if engine == "rapidocr":
        try:
            import rapidocr  # noqa: F401
        except Exception as e:
            return False, f"rapidocr not importable: {e}"
        return True, ""
    if engine == "easyocr":
        try:
            import easyocr  # noqa: F401
        except Exception as e:
            return False, f"easyocr not importable: {e}"
        return True, ""
    if engine == "tesseract":
        if shutil.which("tesseract") is None:
            return False, "Tesseract binary not installed on this machine (brew install tesseract tesseract-lang to enable)."
        return True, ""
    return False, "unknown engine"


def lang_for(engine: str, row: dict):
    if engine == "easyocr" and row["language"] == "marathi":
        return EASYOCR_MARATHI
    return LANGS[engine].get(row["script"])


def make_converter(engine: str, lang: list[str], threads: int, scale: float = 1.0):
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (EasyOcrOptions, OcrMacOptions, PdfPipelineOptions,
                                                    RapidOcrOptions, TesseractCliOcrOptions)
    from docling.document_converter import DocumentConverter, ImageFormatOption

    cls = {"ocrmac": OcrMacOptions, "rapidocr": RapidOcrOptions, "easyocr": EasyOcrOptions,
           "tesseract": TesseractCliOcrOptions}[engine]
    # scale=1.0: the page images are already 150 DPI scans; Docling's default (3.0) would upsample
    # them 3x before OCR, which costs 2-3x runtime and is not how a real scan arrives.
    ocr = cls(lang=lang, force_full_page_ocr=True, scale=scale)
    po = PdfPipelineOptions(do_ocr=True, ocr_options=ocr, do_table_structure=False, generate_parsed_pages=True,
                            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=threads))
    return DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=po)})


def worker(engine: str, rows: list[dict], threads: int, force: bool):
    from docling_core.types.doc import CoordOrigin

    out_dir = PRED / engine
    out_dir.mkdir(parents=True, exist_ok=True)
    convs = {}
    done = 0
    t_start = time.time()
    for row in rows:
        lang = lang_for(engine, row)
        stem = f"{row['page_id']}.{row['condition'].replace(':', '__')}"
        out = out_dir / f"{stem}.json"
        if lang is None or (out.exists() and not force):
            continue
        key = tuple(lang)
        if key not in convs:
            convs[key] = make_converter(engine, lang, threads)
        t0 = time.time()
        res = convs[key].convert(ROOT / row["image"])
        dt = time.time() - t0
        page = res.pages[0]
        H = page.size.height
        cells = []
        for c in (page.parsed_page.textline_cells if page.parsed_page else []):
            bb = c.rect.to_bounding_box()
            if bb.coord_origin != CoordOrigin.TOPLEFT:
                bb = bb.to_top_left_origin(page_height=H)
            cells.append({"text": c.text, "bbox": [round(bb.l, 1), round(bb.t, 1), round(bb.r, 1), round(bb.b, 1)],
                          "conf": round(float(c.confidence), 4) if c.confidence is not None else None})
        rec = {"engine": engine, "lang": lang, "page_id": row["page_id"], "condition": row["condition"],
               "seconds": round(dt, 3), "page_size": [page.size.width, page.size.height],
               "status": str(res.status), "cells": cells,
               "document_text": res.document.export_to_text()}
        out.write_text(json.dumps(rec, ensure_ascii=False))
        try:
            (out_dir / f"{stem}.dclg").write_text(res.document.export_to_doclang(xsize=int(page.size.width), ysize=int(page.size.height)))
        except Exception as e:  # serialiser problems must not kill the run
            rec["doclang_error"] = repr(e)
        done += 1
        if done % 10 == 0:
            print(f"[{engine}] {done} pages, {time.time() - t_start:.0f}s", flush=True)
    print(f"[{engine}] finished {done} new pages in {time.time() - t_start:.0f}s", flush=True)


# ============================================================== scoring
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").upper()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def alnum(s: str) -> str:
    # letters, digits and combining marks (Indic vowel signs) only
    return "".join(ch for ch in norm(s) if unicodedata.category(ch)[0] in "LNM")


def semi_global(gt, hyp) -> int:
    """Min edit distance between gt and any contiguous substring of hyp (free start/end in hyp)."""
    n = len(gt)
    if n == 0:
        return 0
    if not hyp:
        return n
    prev = list(range(n + 1))
    best = prev[n]
    for j in range(1, len(hyp) + 1):
        cur = [0] * (n + 1)  # free start in hyp
        hj = hyp[j - 1]
        for i in range(1, n + 1):
            cur[i] = min(prev[i] + 1, cur[i - 1] + 1, prev[i - 1] + (gt[i - 1] != hj))
        best = min(best, cur[n])
        prev = cur
    return best


def overlap_frac(cell, box):
    l, t, r, b = cell
    L, T, R, B = box
    iw = max(0.0, min(r, R) - max(l, L))
    ih = max(0.0, min(b, B) - max(t, T))
    a = max(1e-6, (r - l) * (b - t))
    return iw * ih / a, ih / max(1e-6, (b - t))


def region_text(cells, bbox, pad_frac=0.5):
    l, t, r, b = bbox
    h = max(4.0, b - t)
    box = [l - pad_frac * h, t - pad_frac * h, r + pad_frac * h, b + pad_frac * h]
    picked = []
    for c in cells:
        area_frac, v_frac = overlap_frac(c["bbox"], box)
        # keep a line if it overlaps the field vertically and touches the field horizontally
        if v_frac >= 0.5 and area_frac > 0:
            picked.append(c)
    picked.sort(key=lambda c: (round(c["bbox"][1] / max(4.0, h)), c["bbox"][0]))
    return " ".join(c["text"] for c in picked)


def page_text(cells):
    if not cells:
        return ""
    hs = sorted(c["bbox"][3] - c["bbox"][1] for c in cells)
    lh = max(4.0, hs[len(hs) // 2])
    cs = sorted(cells, key=lambda c: (round(((c["bbox"][1] + c["bbox"][3]) / 2) / lh), c["bbox"][0]))
    return " ".join(c["text"] for c in cs)


def lev(a, b) -> int:
    from rapidfuzz.distance import Levenshtein
    return Levenshtein.distance(a, b)


def score_page(gt: dict, pred: dict) -> dict:
    cells = pred["cells"]
    full = norm(page_text(cells))
    full_an = alnum(full)
    fields = []
    for f in gt["fields"]:
        if not f["scored"]:
            continue
        g = norm(f["display_value"])
        reg = norm(region_text(cells, f["bbox_px"]))
        if f.get("comb"):  # one character per printed box: spacing is layout, not content
            g, reg = g.replace(" ", ""), reg.replace(" ", "")
        g_an, reg_an = alnum(g), alnum(reg)
        cd = semi_global(g, reg)
        gw, rw = g.split(), reg.split()
        wd = semi_global(gw, rw)
        rw_bag = defaultdict(int)
        for w in rw:
            rw_bag[w] += 1
        hit = 0
        for w in gw:
            if rw_bag[w] > 0:
                rw_bag[w] -= 1
                hit += 1
        fields.append({
            "key": f["key"], "gt": f["display_value"], "region_text": reg,
            "visibility": f.get("visibility", "visible"),
            "em_region": bool(g) and g in reg,
            "em_region_alnum": bool(g_an) and g_an in reg_an,
            "em_anywhere": bool(g) and g in full,
            "char_edits": min(cd, len(g)), "chars": len(g),
            "word_edits": min(wd, len(gw)), "words": len(gw),
            "token_hits": hit,
        })
    return {"fields": fields, "page_text": page_text(cells)}


def stats(field_rows: list[dict]) -> dict:
    n = len(field_rows)
    if n == 0:
        return {"n_fields": 0}
    chars = sum(f["chars"] for f in field_rows)
    words = sum(f["words"] for f in field_rows)
    return {
        "n_fields": n,
        "cer": round(sum(f["char_edits"] for f in field_rows) / max(1, chars), 4),
        "wer": round(sum(f["word_edits"] for f in field_rows) / max(1, words), 4),
        "em_region": round(sum(f["em_region"] for f in field_rows) / n, 4),
        "em_region_alnum": round(sum(f["em_region_alnum"] for f in field_rows) / n, 4),
        "em_anywhere": round(sum(f["em_anywhere"] for f in field_rows) / n, 4),
        "token_recall": round(sum(f["token_hits"] for f in field_rows) / max(1, words), 4),
    }


def aggregate(rows: list[dict], engines: list[str], subsets: dict):
    page_scores = []
    for engine in engines:
        clean_text = {}
        for row in rows:
            if row["page_id"] not in subsets[engine]:
                continue
            p = PRED / engine / f"{row['page_id']}.{row['condition'].replace(':', '__')}.json"
            if not p.exists():
                continue
            pred = json.loads(p.read_text())
            gt = json.loads((ROOT / row["gt"]).read_text())
            sc = score_page(gt, pred)
            rec = {k: row[k] for k in ("page_id", "pack", "document", "family", "language", "script", "condition")}
            rec.update(engine=engine, seconds=pred["seconds"], fields=sc["fields"], page_text=sc["page_text"])
            if row["condition"] == "clean":
                clean_text[row["page_id"]] = norm(sc["page_text"])
            page_scores.append(rec)
        for rec in page_scores:  # drift: degraded page text vs the same engine's clean-page text
            if rec["engine"] == engine and rec["condition"] != "clean" and rec["page_id"] in clean_text:
                ref = clean_text[rec["page_id"]]
                rec["drift_cer"] = round(min(1.0, lev(ref, norm(rec["page_text"])) / max(1, len(ref))), 4)
    def group(keyf):
        g = defaultdict(list)
        pages = defaultdict(list)
        for r in page_scores:
            k = keyf(r)
            if k is None:
                continue
            g[k].extend(r["fields"])
            pages[k].append(r)
        out = {}
        for k, fr in g.items():
            s = stats(fr)
            s["n_pages"] = len(pages[k])
            drift = [p["drift_cer"] for p in pages[k] if "drift_cer" in p]
            if drift:
                s["drift_cer"] = round(sum(drift) / len(drift), 4)
            s["sec_per_page"] = round(sum(p["seconds"] for p in pages[k]) / len(pages[k]), 2)
            out["|".join(k)] = s
        return out

    # "common" = page images that every engine supporting that script actually ran, so engines are
    # compared on identical inputs. With the EasyOCR cap this is the EasyOCR subset.
    have = defaultdict(set)
    for r in page_scores:
        have[(r["page_id"], r["condition"])].add(r["engine"])
    script_of = {r["page_id"]: r["script"] for r in rows}
    def is_common(r):
        need = {e for e in engines if LANGS[e].get(script_of[r["page_id"]]) is not None}
        return need <= have[(r["page_id"], r["condition"])]
    for r in page_scores:
        r["common"] = is_common(r)

    metrics = {
        "common_engine_condition_latin": group(lambda r: (r["engine"], r["condition"]) if r["script"] == "Latin" and r["common"] else None),
        "common_engine_condition_script": group(lambda r: (r["engine"], r["condition"], r["script"]) if r["common"] else None),
        "common_engine_condition": group(lambda r: (r["engine"], r["condition"]) if r["common"] else None),
        "engine_condition": group(lambda r: (r["engine"], r["condition"])),
        "engine_condition_latin": group(lambda r: (r["engine"], r["condition"]) if r["script"] == "Latin" else None),
        "engine_condition_script": group(lambda r: (r["engine"], r["condition"], r["script"])),
        "engine_family_condition": group(lambda r: (r["engine"], r["family"], r["condition"])),
        "engine_overall_synthetic": group(lambda r: (r["engine"],) if not r["condition"].startswith("native:") else None),
    }
    with open(RES / "page_scores.jsonl", "w") as fh:
        for r in page_scores:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (RES / "metrics.json").write_text(json.dumps(metrics, indent=1, ensure_ascii=False))
    return metrics, page_scores


# ============================================================== report
SYNTH = ["clean", "blur", "skew", "photocopy", "low_light", "fax"]


def fmt(x, pct=True):
    if x is None:
        return "–"
    return f"{100 * x:.1f}" if pct else f"{x:.2f}"


def write_summary(metrics, meta, engines):
    ec = metrics["common_engine_condition_latin"]      # identical page images for every engine
    ecs = metrics["common_engine_condition_script"]
    full = metrics["engine_condition_latin"]            # each engine on all pages it ran
    L = []
    L.append("# Results summary (first pass)\n")
    L.append(f"Generated {meta['finished_utc']} · Docling {meta['versions'].get('docling')} · "
             f"{meta['host']['machine']} {meta['host']['system']} · CPU only · full-page OCR at the scan's native 150 DPI.\n")
    L.append("All numbers are on **synthetic GritWorks documents with simulated degradations**. "
             "Field metrics cover only the populated fields in the ground truth, not every printed word. "
             "Treat them as a first pass for methodology review, not a leaderboard.\n")
    L.append("## Counts\n")
    L.append(f"- Source pages: {meta['counts']['source_pages']} (from {meta['counts']['source_documents']} clean documents in 6 public sample packs)")
    L.append(f"- Page images: {meta['counts']['page_images']} = {meta['counts']['source_pages']} pages × 6 synthetic conditions + {meta['counts']['native_images']} pack-native degraded pages")
    L.append(f"- Scored fields per synthetic condition: {meta['counts']['scored_fields_per_condition']} "
             f"(fields with <2 non-space characters, e.g. checkbox marks, are excluded: {meta['counts']['excluded_fields_per_condition']})")
    for e in engines:
        L.append(f"- {e}: {meta['counts']['pages_run'].get(e, 0)} page images converted "
                 f"({meta['engine_source_pages'].get(e)} source pages; {meta['counts']['conversion_seconds_sum'].get(e)} s total conversion time)")
    L.append("")
    L.append("**Tables 1-5 compare engines on the common subset**: the page images that every engine supporting "
             "that script ran (EasyOCR's seeded, script-stratified subset). Table 6 shows each engine on every page it ran.\n")
    nf = {e: ec.get(f"{e}|clean", {}).get("n_fields") for e in engines}
    np_ = {e: ec.get(f"{e}|clean", {}).get("n_pages") for e in engines}
    L.append("Common subset, Latin pages, per condition: " + ", ".join(f"{e} {np_[e]} pages / {nf[e]} fields" for e in engines) + "\n")
    L.append("## 1. Field exact match (EM, %) by degradation — Latin-script pages\n")
    L.append("EM = the normalised printed value appears inside the OCR text found in the field's box (case-insensitive, whitespace-collapsed).\n")
    L.append("| Engine | " + " | ".join(SYNTH) + " |")
    L.append("|---|" + "---:|" * len(SYNTH))
    for e in engines:
        L.append(f"| {e} | " + " | ".join(fmt(ec.get(f"{e}|{c}", {}).get("em_region")) for c in SYNTH) + " |")
    L.append("")
    L.append("## 2. Field CER (%) by degradation — Latin-script pages\n")
    L.append("CER = edit distance between the printed value and its best-matching span in the box text ÷ value length (micro-averaged, capped at 1 per field).\n")
    L.append("| Engine | " + " | ".join(SYNTH) + " |")
    L.append("|---|" + "---:|" * len(SYNTH))
    for e in engines:
        L.append(f"| {e} | " + " | ".join(fmt(ec.get(f"{e}|{c}", {}).get("cer")) for c in SYNTH) + " |")
    L.append("")
    L.append("## 3. Field WER (%) by degradation — Latin-script pages\n")
    L.append("| Engine | " + " | ".join(SYNTH) + " |")
    L.append("|---|" + "---:|" * len(SYNTH))
    for e in engines:
        L.append(f"| {e} | " + " | ".join(fmt(ec.get(f"{e}|{c}", {}).get("wer")) for c in SYNTH) + " |")
    L.append("")
    L.append("## 4. Indic pages (Devanagari: Hindi, Marathi; Bengali) — field EM % / CER %\n")
    L.append("| Engine | Script | " + " | ".join(SYNTH) + " |")
    L.append("|---|---|" + "---|" * len(SYNTH))
    for e in engines:
        for s in ("Devanagari", "Bengali"):
            cells = []
            for c in SYNTH:
                m = ecs.get(f"{e}|{c}|{s}")
                cells.append(f"{fmt(m['em_region'])} / {fmt(m['cer'])}" if m else "n/a")
            L.append(f"| {e} | {s} | " + " | ".join(cells) + " |")
    L.append("\n`n/a` = the engine has no recognition model for that script in this setup (Apple Vision has no Indic scripts; RapidOCR's ONNX models have no Bengali).\n")
    L.append("## 5. Pack-native degraded pages (all scripts) — EM % / CER %\n")
    L.append("These are the degraded PDFs shipped in the packs; each covers a different subset of documents, so compare engines within a column, not across columns.\n")
    natives = sorted({k.split("|")[1] for k in metrics["common_engine_condition"] if "|native:" in k})
    L.append("| Engine | " + " | ".join(n.replace("native:", "") for n in natives) + " |")
    L.append("|---|" + "---|" * len(natives))
    for e in engines:
        cells = []
        for n in natives:
            m = metrics["common_engine_condition"].get(f"{e}|{n}")
            cells.append(f"{fmt(m['em_region'])} / {fmt(m['cer'])} (n={m['n_fields']})" if m and m.get("n_fields") else "–")
        L.append(f"| {e} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## 6. Full set: each engine on every Latin page it ran — field EM %\n")
    L.append("| Engine | pages | " + " | ".join(SYNTH) + " |")
    L.append("|---|---:|" + "---:|" * len(SYNTH))
    for e in engines:
        L.append(f"| {e} | {full.get(f'{e}|clean', {}).get('n_pages', '–')} | " + " | ".join(fmt(full.get(f"{e}|{c}", {}).get("em_region")) for c in SYNTH) + " |")
    L.append("")
    L.append("## 7. Speed and stability (Latin pages, common subset)\n")
    L.append("| Engine | sec/page (clean) | drift CER vs own clean output, mean over degradations (%) |")
    L.append("|---|---:|---:|")
    for e in engines:
        sp = ec.get(f"{e}|clean", {}).get("sec_per_page")
        dr = [ec.get(f"{e}|{c}", {}).get("drift_cer") for c in SYNTH[1:]]
        dr = [d for d in dr if d is not None]
        L.append(f"| {e} | {sp if sp is not None else '–'} | {fmt(sum(dr) / len(dr)) if dr else '–'} |")
    L.append("")
    L.append("## 8. Best and worst degradation per engine (Latin, common subset, by field EM)\n")
    for e in engines:
        vals = {c: ec.get(f"{e}|{c}", {}).get("em_region") for c in SYNTH[1:]}
        vals = {c: v for c, v in vals.items() if v is not None}
        if vals:
            b = max(vals, key=vals.get)
            w = min(vals, key=vals.get)
            L.append(f"- **{e}**: clean {fmt(ec[f'{e}|clean']['em_region'])}% → best {b} {fmt(vals[b])}%, worst {w} {fmt(vals[w])}%")
    L.append("")
    for ab in ("ablation_scale.md", "ablation_easyocr_conf.md"):
        if (RES / ab).exists():
            L.append("## " + (RES / ab).read_text().lstrip("# "))
    L.append("Note: the three engines ran as parallel processes on one laptop, so sec/page values interfere with each other; use them as an ordering only.\n")
    L.append("## Engines skipped\n")
    for k, v in meta["skipped_engines"].items():
        L.append(f"- **{k}**: {v}")
    L.append("\nPer-family breakdowns are in `metrics.json` (`engine_family_condition`); per-field detail is in `page_scores.jsonl`.\n")
    (RES / "SUMMARY.md").write_text("\n".join(L))


# ============================================================== main
def load_rows(args):
    rows = [json.loads(l) for l in (DATA / "pairs.jsonl").read_text().splitlines() if l.strip()]
    if args.conditions:
        keep = set(args.conditions.split(","))
        rows = [r for r in rows if r["condition"] in keep or (r["condition"].startswith("native:") and "native" in keep)]
    if args.limit_pages:
        pages = sorted({r["page_id"] for r in rows})
        random.Random(args.seed).shuffle(pages)
        keep = set(pages[: args.limit_pages])
        rows = [r for r in rows if r["page_id"] in keep]
    return rows


def engine_page_subset(rows, engine, cap, seed):
    """Seeded, script-stratified subset of source pages (proportional allocation, at least 1 per script)."""
    by_script = defaultdict(set)
    for r in rows:
        if lang_for(engine, r) is not None:
            by_script[r["script"]].add(r["page_id"])
    total = sum(len(v) for v in by_script.values())
    if not cap or cap >= total:
        return set().union(*by_script.values()) if by_script else set()
    keep = set()
    for script, pages in sorted(by_script.items()):
        k = max(1, round(cap * len(pages) / total))
        pl = sorted(pages)
        random.Random(f"{seed}|{engine}|{script}").shuffle(pl)
        keep.update(pl[:k])
    return keep


def versions():
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for p in ("docling", "docling-core", "docling-ibm-models", "docling-parse", "doclang", "easyocr", "rapidocr",
              "onnxruntime", "ocrmac", "torch", "opencv-python-headless", "pypdfium2", "rapidfuzz"):
        try:
            out[p] = version(p)
        except PackageNotFoundError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default=",".join(CPU_ENGINES))
    ap.add_argument("--conditions", default="", help="comma list; 'native' selects all pack-native variants")
    ap.add_argument("--limit-pages", type=int, default=0, help="random subsample of source pages (seeded)")
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--engine-pages", default="easyocr=19",
                    help="per-engine cap on source pages, stratified by script and seeded, e.g. easyocr=19; "
                         "'' = no cap. EasyOCR on CPU is ~15-20 s/page, so the full set would exceed the 60-minute budget.")
    ap.add_argument("--threads", type=str, default="ocrmac=2,rapidocr=4,easyocr=4,tesseract=2")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--worker", default="")
    ap.add_argument("--rows-file", default="")
    args = ap.parse_args()

    if args.worker:
        rows = json.loads(Path(args.rows_file).read_text())
        threads = dict(kv.split("=") for kv in args.threads.split(","))
        worker(args.worker, rows, int(threads.get(args.worker, 2)), args.force)
        return

    RES.mkdir(exist_ok=True)
    rows = load_rows(args)
    requested = [e for e in args.engines.split(",") if e]
    skipped = dict(SKIPPED_ALWAYS)
    engines = []
    for e in requested:
        ok, why = engine_available(e)
        (engines.append(e) if ok else skipped.__setitem__(e, why))
    for e in engines:
        miss = sorted({r["script"] for r in rows if lang_for(e, r) is None})
        if miss:
            skipped[f"{e} on {', '.join(miss)} pages"] = "No recognition model for this script in this engine/setup; those pages are not scored for it."

    caps = dict(kv.split("=") for kv in args.engine_pages.split(",") if kv)
    subsets = {e: engine_page_subset(rows, e, int(caps.get(e, 0)), args.seed) for e in engines}

    t0 = time.time()
    timings = {}
    if not args.aggregate_only:
        procs = {}
        for e in engines:
            rf = RES / f"_rows_{e}.json"
            rf.write_text(json.dumps([r for r in rows if r["page_id"] in subsets[e]]))
            env = dict(os.environ)
            th = dict(kv.split("=") for kv in args.threads.split(",")).get(e, "2")
            env.update(OMP_NUM_THREADS=th, MKL_NUM_THREADS=th)
            cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", e, "--rows-file", str(rf),
                   "--threads", args.threads] + (["--force"] if args.force else [])
            log = open(RES / f"_log_{e}.txt", "a")
            procs[e] = (subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT), time.time(), log)
        for e, (p, ts, log) in procs.items():
            rc = p.wait()
            log.close()
            timings[e] = {"wall_seconds": round(time.time() - ts, 1), "returncode": rc}
            print(f"{e}: rc={rc} wall={timings[e]['wall_seconds']}s")
        for e in engines:
            (RES / f"_rows_{e}.json").unlink(missing_ok=True)

    metrics, page_scores = aggregate(rows, engines, subsets)
    synth_clean = [r for r in rows if r["condition"] == "clean"]
    gts = [json.loads((ROOT / r["gt"]).read_text()) for r in synth_clean]
    prev = {}
    if (RES / "run_meta.json").exists():
        prev = json.loads((RES / "run_meta.json").read_text())
    meta = {
        "finished_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "versions": versions(),
        "host": {"system": f"{platform.system()} {platform.release()}", "machine": platform.machine(),
                 "processor": platform.processor(), "python": platform.python_version(), "device": "cpu"},
        "settings": {"ocr_scale": 1.0, "force_full_page_ocr": True, "do_table_structure": False,
                     "image_dpi": gts[0]["dpi"] if gts else None, "langs": LANGS, "easyocr_marathi": EASYOCR_MARATHI,
                     "threads": args.threads, "region_pad": "0.5 x field height", "limit_pages": args.limit_pages},
        "counts": {
            "source_documents": len({(r["pack"], r["document"]) for r in synth_clean}),
            "source_pages": len(synth_clean),
            "page_images": len(rows),
            "native_images": sum(r["condition"].startswith("native:") for r in rows),
            "scored_fields_per_condition": sum(sum(f["scored"] for f in g["fields"]) for g in gts),
            "excluded_fields_per_condition": sum(sum(not f["scored"] for f in g["fields"]) for g in gts),
            "pages_run": {e: sum(1 for p in page_scores if p["engine"] == e) for e in engines},
            "conversion_seconds_sum": {e: round(sum(p["seconds"] for p in page_scores if p["engine"] == e), 1) for e in engines},
        },
        "engines_run": engines,
        "engine_page_caps": caps,
        "engine_source_pages": {e: len(subsets[e]) for e in engines},
        "engine_page_subsets": {e: sorted(subsets[e]) for e in engines},
        "skipped_engines": skipped,
        "timings": timings or prev.get("timings", {}),
        "total_wall_seconds": round(time.time() - t0, 1) if timings else prev.get("total_wall_seconds"),
    }
    (RES / "run_meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    write_summary(metrics, meta, engines)
    print((RES / "SUMMARY.md").read_text())


if __name__ == "__main__":
    main()
