"""Assemble hf/ as a ready-to-upload Hugging Face dataset folder (does not upload anything).

hf/
  README.md                  dataset card (kept as is)
  synthetic.jsonl            split "synthetic": clean + 5 generated degradations (37 pages x 6 = 222 rows)
  native.jsonl               split "native": degraded pages shipped in the source packs (38 rows)
  images/<page_id>/<condition>.png
  gt/{gritworks,docling,doclang}/...
  gt_corrections.json, inventory.json, doclang_validation.json
  predictions/<engine>/...   saved Docling OCR outputs (JSON cells + DocLang) used for results/

Each JSONL row: file_name (image path), page/condition metadata, gt paths, and the ground-truth fields inline.
Run:  .venv/bin/python -I scripts/make_hf.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HF = ROOT / "hf"


def main():
    for sub in ("images", "gt", "predictions"):
        if (HF / sub).exists():
            shutil.rmtree(HF / sub)
    for f in ("synthetic.jsonl", "native.jsonl", "gt_corrections.json", "inventory.json", "doclang_validation.json"):
        (HF / f).unlink(missing_ok=True)
    shutil.copytree(ROOT / "data" / "images", HF / "images")
    for fmt in ("gritworks", "docling", "doclang"):
        shutil.copytree(ROOT / "data" / "gt" / fmt, HF / "gt" / fmt)
    shutil.copytree(ROOT / "results" / "predictions", HF / "predictions")
    shutil.copy2(ROOT / "data" / "gt_corrections.json", HF / "gt_corrections.json")
    shutil.copy2(ROOT / "data" / "inventory.json", HF / "inventory.json")
    shutil.copy2(ROOT / "data" / "gt" / "doclang_validation.json", HF / "doclang_validation.json")

    rows = [json.loads(l) for l in (ROOT / "data" / "pairs.jsonl").read_text().splitlines() if l.strip()]
    out = {"synthetic": [], "native": []}
    for r in rows:
        gt = json.loads((ROOT / r["gt"]).read_text())
        stem = Path(r["gt"]).stem
        rec = {
            "file_name": r["image"].replace("data/", "", 1),
            "page_id": r["page_id"], "condition": r["condition"], "pack": r["pack"], "document": r["document"],
            "family": r["family"], "language": r["language"], "script": r["script"], "page": r["page"],
            "image_size_px": gt["image_size_px"], "dpi": gt["dpi"],
            "degradation_params": json.dumps(gt.get("degradation_params") or {}),
            "gt_gritworks": f"gt/gritworks/{stem}.json", "gt_docling": f"gt/docling/{stem}.json",
            "gt_doclang": f"gt/doclang/{stem}.dclg",
            "n_fields": r["n_fields"], "n_scored": r["n_scored"],
            "fields": [{k: f.get(k) for k in ("key", "display_value", "canonical_value", "value", "bbox_px",
                                              "visibility", "scored", "comb", "printed_form_rule")}
                       for f in gt["fields"]],
        }
        for f in rec["fields"]:  # keep a stable string type for the viewer
            f["value"] = None if f["value"] is None else str(f["value"])
        out["native" if r["condition"].startswith("native:") else "synthetic"].append(rec)
    for split, recs in out.items():
        (HF / f"{split}.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in recs) + "\n")
    files = [p for p in HF.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    print(f"hf/: {len(files)} files, {size / 1e6:.1f} MB; synthetic={len(out['synthetic'])} native={len(out['native'])}")


if __name__ == "__main__":
    main()
