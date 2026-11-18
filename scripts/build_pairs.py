"""Build matched clean/degraded page pairs from the GritWorks public sample packs.

Inputs : _src/<pack>/<pack-dir>/manifest.json + per-document PDFs and *.boxes.json
         (extracted from the public zips; treated as data only, nothing in them is executed).
Outputs: data/images/<page_id>/<condition>.png      page images (all OCR input is raster)
         data/gt/gritworks/<page_id>.<condition>.json  ground truth in the original GritWorks
                                                       field schema, boxes converted to image pixels
         data/pairs.jsonl                            one row per (page, condition)

Conditions
  clean                         the clean page, rendered at --dpi
  blur, skew, photocopy,        generated here from the clean render with a fixed seed;
  low_light, fax                 the ground truth carries over exactly (skew boxes are
                                 transformed with the same affine matrix)
  native:<variant>              the degraded PDF shipped in the pack (photocopy, blur, coffee
                                 stain, low light, crop, skew, bad photo), with the pack's own
                                 forward-projected field boxes

Run:  .venv/bin/python -I scripts/build_pairs.py [--dpi 150] [--seed 20261117]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
import cv2
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "_src"
DATA = ROOT / "data"

SYNTH_CONDITIONS = ["blur", "skew", "photocopy", "low_light", "fax"]

# Map each pack document to a coarse family used in the report.
FAMILY = {
    "checking_statement": "bank_statement", "paystub": "paystub", "w2": "tax_form",
    "mortgage_statement": "bank_statement", "utility_bill": "utility_bill",
    "patient_registration": "medical_form", "lab_requisition": "lab_requisition",
    "physician_authorization": "medical_form", "specimen_query": "medical_form",
    "lab_report": "lab_report", "premium_statement": "insurance_statement",
    "cms1500_claim": "cms1500_claim", "itemized_invoice": "invoice",
    "explanation_of_benefits": "insurance_statement", "patient_statement": "insurance_statement",
    "purchase_order": "invoice", "goods_invoice": "invoice", "services_invoice": "invoice",
    "credit_memo": "invoice", "account_statement": "bank_statement",
    "passport": "passport_specimen", "driving_license": "id_card", "passport_card": "id_card",
    "social_security_card": "id_card", "proof_of_address": "utility_bill",
    "bengali": "indic_form", "hindi": "indic_form", "marathi": "indic_form",
}


def family_of(doc_id: str) -> str:
    for k in sorted(FAMILY, key=len, reverse=True):  # longest prefix wins (passport_card vs passport)
        if doc_id.startswith(k):
            return FAMILY[k]
    return "other"


def seed_for(base: int, *parts: str) -> int:
    h = hashlib.sha256(("|".join(parts) + f"|{base}").encode()).hexdigest()
    return int(h[:8], 16)


# ---------------------------------------------------------------- degradations
def deg_blur(img, rng):
    sigma = 1.6 + rng.uniform(0, 0.6)
    return cv2.GaussianBlur(img, (0, 0), sigma), {"sigma_px": round(sigma, 3)}, None


def deg_skew(img, rng):
    angle = float(rng.choice([-1, 1]) * rng.uniform(2.0, 5.0))
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    out = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return out, {"angle_deg": round(angle, 3)}, M


def deg_photocopy(img, rng):
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = (g - 128) * 1.6 + 140                      # harsh contrast, washed highlights
    h, w = g.shape
    grad = np.linspace(0, rng.uniform(15, 30), w)[None, :]  # uneven toner across the page
    g = g + grad
    speck = rng.random((h, w))
    g[speck < 0.002] = 20                          # toner specks
    g = np.clip(g, 0, 255).astype(np.uint8)
    q = int(rng.integers(18, 30))
    ok, enc = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, q])
    g = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB), {"contrast": 1.6, "jpeg_quality": q, "speck_rate": 0.002}, None


def deg_low_light(img, rng):
    f = img.astype(np.float32) / 255.0
    gamma = rng.uniform(1.8, 2.3)
    f = np.power(f, gamma) * rng.uniform(0.45, 0.6)  # darker and lower dynamic range
    h, w = f.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    vign = 1.0 - 0.35 * np.clip(r, 0, 1.4) ** 2
    f = f * vign[..., None]
    noise_sd = rng.uniform(0.025, 0.04)
    f = f + rng.normal(0, noise_sd, f.shape)
    f = np.clip(f, 0, 1)
    tint = np.array([1.0, 0.93, 0.8], dtype=np.float32)  # warm indoor light
    f = np.clip(f * tint, 0, 1)
    out = (f * 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return cv2.imdecode(enc, cv2.IMREAD_UNCHANGED), {"gamma": round(gamma, 3), "noise_sd": round(noise_sd, 4), "vignette": 0.35}, None


def deg_fax(img, rng):
    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # ITU-T T.4 "standard" mode samples ~2x coarser vertically than horizontally (204x98 dpi):
    # keep horizontal resolution, resample vertical by 98/204, binarize, then stretch back.
    small = cv2.resize(g, (w, int(h * 98 / 204)), interpolation=cv2.INTER_AREA)
    thr = int(rng.integers(150, 175))
    bw = np.where(small > thr, 255, 0).astype(np.uint8)
    flips = rng.random(bw.shape) < 0.004             # salt-and-pepper line noise
    bw[flips] = 255 - bw[flips]
    n_lines = int(rng.integers(2, 6))
    for _ in range(n_lines):                         # horizontal streaks from the scan head
        y = int(rng.integers(0, bw.shape[0]))
        bw[y, :] = 0 if rng.random() < 0.5 else 255
    out = cv2.resize(bw, (w, h), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2RGB), {"threshold": thr, "flip_rate": 0.004, "streaks": n_lines, "vertical_resample": round(98 / 204, 3)}, None


DEGRADE = {"blur": deg_blur, "skew": deg_skew, "photocopy": deg_photocopy,
           "low_light": deg_low_light, "fax": deg_fax}


def transform_bbox(b, M, w, h):
    x0, y0, x1, y1 = b
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], dtype=np.float64)
    tp = pts @ M.T
    poly = [[round(float(x), 2), round(float(y), 2)] for x, y in tp]
    nb = [max(0.0, tp[:, 0].min()), max(0.0, tp[:, 1].min()), min(w, tp[:, 0].max()), min(h, tp[:, 1].max())]
    return [round(float(v), 2) for v in nb], poly


# ---------------------------------------------------------------- helpers
def render(pdf_path: Path, page_idx: int, dpi: int) -> np.ndarray:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pil = pdf[page_idx].render(scale=dpi / 72.0).to_pil().convert("RGB")
    finally:
        pdf.close()
    return np.array(pil)


def save_png(arr: np.ndarray, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))


CORRECTIONS = {}
_cp = DATA / "gt_corrections.json"
if _cp.exists():
    for c in json.loads(_cp.read_text())["corrections"]:
        CORRECTIONS[(c["document"], c["page"], c["key"])] = c


def printed_form_rule(document: str, clean_field: dict):
    """Return (printed_text, rule, comb) for a field, using the clean page's annotation.

    Rule 1 (authored words): when the pack ships word boxes for the clean page (the exact text
      authored before rasterisation), the printed form is those words joined by single spaces.
      This restores e.g. '$' signs that the pack's display_value omits.
    Rule 2 (comb fields): if every authored word is a single character (one character per printed
      box, e.g. Marathi CIF dates/PAN), the field is marked comb=True and scored with whitespace removed.
    Rule 3 (manual): for packs without word boxes, hand-verified corrections in data/gt_corrections.json.
    Otherwise the pack's display_value is kept.
    """
    dv = clean_field.get("display_value")
    dv = "" if dv is None else str(dv)
    words = [w["text"] for w in (clean_field.get("words") or []) if w.get("text")]
    man = CORRECTIONS.get((document, clean_field.get("page"), clean_field["key"]))
    if man:
        return man["printed"], "manual (data/gt_corrections.json)", False
    if words:
        joined = " ".join(words)
        comb = len(words) > 1 and all(len(w) == 1 for w in words)
        if " ".join(joined.split()) != " ".join(dv.split()):
            return joined, "authored word boxes", comb
        return dv, None, comb
    return dv, None, False


def fields_for_page(boxes: dict, page_no: int, scale: float, min_chars: int, document: str = "", clean_boxes: dict | None = None):
    out = []
    clean_by_key = {(f["key"], f.get("page")): f for f in (clean_boxes or boxes)["fields"]}
    for f in boxes["fields"]:
        if f.get("page") != page_no or not f.get("bbox"):
            continue
        orig = f.get("display_value")
        orig = "" if orig is None else str(orig)
        cf = clean_by_key.get((f["key"], f.get("page")), f)
        dv, rule, comb = printed_form_rule(document, cf)
        scored = len("".join(dv.split())) >= min_chars
        out.append({
            "key": f["key"],
            "value": f.get("value"),
            "display_value": dv,
            "canonical_value": orig,
            "printed_form_rule": rule,
            "comb": comb,
            "bbox_px": [round(v * scale, 2) for v in f["bbox"]],
            "bbox_pt": f["bbox"],
            "visibility": f.get("visibility") or "visible",
            "scored": scored,
            "exclusion_reason": None if scored else f"display_value shorter than {min_chars} non-space chars (checkbox/flag)",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--min-chars", type=int, default=2)
    args = ap.parse_args()

    for sub in ("images", "gt/gritworks"):
        if (DATA / sub).exists():
            shutil.rmtree(DATA / sub)
    scale = args.dpi / 72.0
    rows = []
    for man_path in sorted(SRC.glob("*/*/manifest.json")):
        pack_dir = man_path.parent
        man = json.loads(man_path.read_text())
        pack = (man.get("pack") or man.get("name") or pack_dir.name).replace("GritWorks", "").replace("Sample Pack", "").strip(" -")
        pack_slug = pack_dir.name.replace("GritWorks-", "").replace("-10-PDF-Sample", "").lower()
        docs = man["documents"]
        clean = {d["id"]: d for d in docs if d["variant"] == "clean"}
        for cid, cd in clean.items():
            base = cid[: -len("_clean")]
            natives = [d for d in docs if d["variant"] != "clean" and d["id"].startswith(base + "_")]
            cboxes = json.loads((pack_dir / cd["boxes"]).read_text())
            cgt = json.loads((pack_dir / cd["json"]).read_text())
            for p in range(cd["pages"]):
                page_no = p + 1
                page_id = f"{pack_slug}__{base}__p{page_no}"
                img = render(pack_dir / cd["pdf"], p, args.dpi)
                h, w = img.shape[:2]
                fields = fields_for_page(cboxes, page_no, scale, args.min_chars, base, cboxes)
                if not fields:
                    continue
                meta = {"page_id": page_id, "pack": pack_slug, "document": base, "family": family_of(base),
                        "document_type": cgt.get("document_type"), "language": cgt.get("language", "english"),
                        "script": cgt.get("script", "Latin"), "page": page_no, "dpi": args.dpi,
                        "image_size_px": [w, h], "synthetic": True,
                        "source_pdf": str((pack_dir / cd["pdf"]).relative_to(ROOT))}

                def emit(cond, arr, flds, params, source_pdf=None, provenance="clean"):
                    ip = DATA / "images" / page_id / f"{cond.replace(':', '__')}.png"
                    save_png(arr, ip)
                    gt = dict(meta, condition=cond, degradation_params=params, gt_provenance=provenance,
                              coordinate_system="image pixels, top-left origin", fields=flds)
                    if source_pdf:
                        gt["source_pdf"] = source_pdf
                    gp = DATA / "gt" / "gritworks" / f"{page_id}.{cond.replace(':', '__')}.json"
                    gp.parent.mkdir(parents=True, exist_ok=True)
                    gp.write_text(json.dumps(gt, indent=1, ensure_ascii=False))
                    rows.append({**{k: meta[k] for k in ("page_id", "pack", "document", "family", "language", "script", "page")},
                                 "condition": cond, "image": str(ip.relative_to(ROOT)), "gt": str(gp.relative_to(ROOT)),
                                 "n_fields": len(flds), "n_scored": sum(f["scored"] for f in flds)})

                emit("clean", img, fields, {}, provenance="exact authored geometry (pack clean boxes)")
                for cond in SYNTH_CONDITIONS:
                    rng = np.random.default_rng(seed_for(args.seed, page_id, cond))
                    out, params, M = DEGRADE[cond](img, rng)
                    flds = json.loads(json.dumps(fields))
                    if M is not None:
                        for f in flds:
                            f["bbox_px"], f["polygon_px"] = transform_bbox(f["bbox_px"], M, w, h)
                    params["seed"] = seed_for(args.seed, page_id, cond)
                    emit(cond, out, flds, params, provenance="clean geometry; " + ("affine-transformed" if M is not None else "photometric change, coordinates unchanged"))
                for nd in natives:
                    nb = json.loads((pack_dir / nd["boxes"]).read_text())
                    narr = render(pack_dir / nd["pdf"], p, args.dpi)
                    if narr.shape[:2] != (h, w):
                        narr = cv2.resize(narr, (w, h), interpolation=cv2.INTER_AREA)
                    nf = fields_for_page(nb, page_no, scale, args.min_chars, base, cboxes)
                    emit(f"native:{nd['variant']}", narr, nf, {"pack_variant": nd["variant"]},
                         source_pdf=str((pack_dir / nd["pdf"]).relative_to(ROOT)),
                         provenance="pack-supplied forward projection of clean geometry")
    (DATA / "pairs.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    pages = sorted({r["page_id"] for r in rows})
    print(f"{len(pages)} source pages, {len(rows)} page images, "
          f"{sum(r['n_scored'] for r in rows if r['condition']=='clean')} scored fields per condition (clean)")


if __name__ == "__main__":
    main()
