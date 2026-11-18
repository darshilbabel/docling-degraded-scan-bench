"""Ablation: EasyOCR confidence_threshold (Docling default 0.5) vs 0.0 on the blur and clean
conditions of the scale-ablation pages. Writes results/ablation_easyocr_conf.md
Run:  .venv/bin/python -I scripts/ablation_easyocr_conf.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as R  # noqa: E402
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, ImageFormatOption

abl = json.loads((R.RES / "ablation_scale.json").read_text())
rows = [json.loads(l) for l in (R.DATA / "pairs.jsonl").read_text().splitlines() if l.strip()]
L = ["# Ablation: EasyOCR confidence_threshold 0.5 (Docling default, main run) vs 0.0\n",
     f"Pages: {', '.join(abl['pages'])}; scale 1.0; field EM % / CER %.\n",
     "| Condition | threshold 0.5 | threshold 0.0 |", "|---|---|---|"]
for cond in ("clean", "blur", "fax"):
    po = PdfPipelineOptions(do_ocr=True, do_table_structure=False, generate_parsed_pages=True,
                            ocr_options=EasyOcrOptions(lang=["en"], force_full_page_ocr=True, scale=1.0, confidence_threshold=0.0),
                            accelerator_options=AcceleratorOptions(device="cpu", num_threads=8))
    conv = DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=po)})
    a, b = [], []
    for r in rows:
        if r["page_id"] in abl["pages"] and r["condition"] == cond:
            gt = json.loads((R.ROOT / r["gt"]).read_text())
            a += R.score_page(gt, json.loads((R.PRED / "easyocr" / f"{r['page_id']}.{cond}.json").read_text()))["fields"]
            page = conv.convert(R.ROOT / r["image"]).pages[0]
            cells = [{"text": c.text, "bbox": list(c.rect.to_bounding_box().as_tuple())} for c in page.parsed_page.textline_cells]
            b += R.score_page(gt, {"cells": cells})["fields"]
    sa, sb = R.stats(a), R.stats(b)
    L.append(f"| {cond} | {100*sa['em_region']:.1f} / {100*sa['cer']:.1f} | {100*sb['em_region']:.1f} / {100*sb['cer']:.1f} |")
    print(L[-1], flush=True)
(R.RES / "ablation_easyocr_conf.md").write_text("\n".join(L) + "\n")
