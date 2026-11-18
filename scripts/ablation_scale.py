"""Ablation: Docling's default OCR scale (3.0, i.e. 3x upsampling of our 150 DPI pages) vs the
scale=1.0 used in the main run, on a small seeded subset of Latin pages from the common subset.

Run:  .venv/bin/python -I scripts/ablation_scale.py [--pages 4] [--conditions clean,blur,fax]
Writes results/ablation_scale.json and results/ablation_scale.md
"""
import argparse, json, random, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--conditions", default="clean,blur,fax")
    ap.add_argument("--engines", default="ocrmac,rapidocr,easyocr")
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=20261117)
    args = ap.parse_args()
    rows = [json.loads(l) for l in (R.DATA / "pairs.jsonl").read_text().splitlines() if l.strip()]
    easy = R.engine_page_subset(rows, "easyocr", 19, args.seed)
    latin = sorted({r["page_id"] for r in rows if r["script"] == "Latin" and r["page_id"] in easy})
    random.Random(f"{args.seed}|ablation").shuffle(latin)
    pages = sorted(latin[: args.pages])
    conds = args.conditions.split(",")
    sel = [r for r in rows if r["page_id"] in pages and r["condition"] in conds]
    out = {"pages": pages, "conditions": conds, "scale_ablation": args.scale, "results": {}}
    for e in args.engines.split(","):
        conv = R.make_converter(e, R.LANGS[e]["Latin"], 4, scale=args.scale)
        for cond in conds:
            f1, f3, t1, t3 = [], [], [], []
            for r in [x for x in sel if x["condition"] == cond]:
                gt = json.loads((R.ROOT / r["gt"]).read_text())
                stem = f"{r['page_id']}.{cond.replace(':', '__')}"
                p1 = json.loads((R.PRED / e / f"{stem}.json").read_text())
                f1 += R.score_page(gt, p1)["fields"]; t1.append(p1["seconds"])
                t0 = time.time()
                res = conv.convert(R.ROOT / r["image"])
                t3.append(time.time() - t0)
                page = res.pages[0]
                cells = [{"text": c.text, "bbox": list(c.rect.to_bounding_box().as_tuple())}
                         for c in page.parsed_page.textline_cells]
                f3 += R.score_page(gt, {"cells": cells})["fields"]
            s1, s3 = R.stats(f1), R.stats(f3)
            s1["sec_per_page"] = round(sum(t1) / len(t1), 2); s3["sec_per_page"] = round(sum(t3) / len(t3), 2)
            out["results"][f"{e}|{cond}"] = {"scale_1.0": s1, f"scale_{args.scale}": s3}
            print(e, cond, "EM", s1["em_region"], "->", s3["em_region"], "s/page", s1["sec_per_page"], "->", s3["sec_per_page"], flush=True)
    (R.RES / "ablation_scale.json").write_text(json.dumps(out, indent=1))
    L = [f"# Ablation: OCR scale 1.0 (main run) vs {args.scale} (Docling default)\n",
         f"{len(pages)} Latin pages ({', '.join(pages)}), conditions {', '.join(conds)}; field EM % / CER % / sec per page.\n",
         f"| Engine | Condition | scale 1.0 | scale {args.scale} |", "|---|---|---|---|"]
    for k, v in out["results"].items():
        e, c = k.split("|")
        a, b = v["scale_1.0"], v[f"scale_{args.scale}"]
        L.append(f"| {e} | {c} | {100*a['em_region']:.1f} / {100*a['cer']:.1f} / {a['sec_per_page']} | {100*b['em_region']:.1f} / {100*b['cer']:.1f} / {b['sec_per_page']} |")
    (R.RES / "ablation_scale.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
