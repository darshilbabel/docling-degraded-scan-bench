"""Convert the GritWorks ground truth (data/gt/gritworks/*.json) to DoclingDocument JSON and DocLang.

For every page image x condition:
  data/gt/docling/<stem>.json   DoclingDocument (docling-core), one page, sized in image pixels.
                                Each scored-or-not field becomes a FieldItem (key = field name,
                                value = printed text) inside one FieldRegion, with a TOPLEFT bbox.
  data/gt/doclang/<stem>.dclg   the same document serialised with docling-core's DocLang serializer
                                (export_to_doclang), location grid = image pixel size so boxes are lossless.

Then every .dclg file is validated with the DocLang reference toolkit (`doclang.validate`): XSD plus
Schematron when a Schematron backend (saxonche) is installed, otherwise XSD only. The validation report
is written to data/gt/doclang_validation.json.

Run:  .venv/bin/python -I scripts/to_doclang.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from docling_core.types.doc import BoundingBox, CoordOrigin, DoclingDocument, ProvenanceItem, Size

ROOT = Path(__file__).resolve().parent.parent
GT = ROOT / "data" / "gt"


def prov(bbox, page_no=1):
    l, t, r, b = bbox
    return ProvenanceItem(page_no=page_no, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT),
                          charspan=(0, 0))


def build(gt: dict) -> DoclingDocument:
    stem = f"{gt['page_id']}.{gt['condition'].replace(':', '__')}"
    w, h = gt["image_size_px"]
    doc = DoclingDocument(name=stem)
    doc.add_page(page_no=1, size=Size(width=w, height=h))
    fields = gt["fields"]
    if not fields:
        return doc
    xs = [f["bbox_px"] for f in fields]
    region = doc.add_field_region(prov=prov([min(b[0] for b in xs), min(b[1] for b in xs),
                                             max(b[2] for b in xs), max(b[3] for b in xs)]))
    for f in fields:
        item = doc.add_field_item(parent=region, prov=prov(f["bbox_px"]))
        # The key is the GritWorks field name (a stable identifier, not the printed form label), so it
        # carries no location; the value is the printed text with its box.
        doc.add_field_key(text=f["key"], parent=item)
        doc.add_field_value(text=f["display_value"], parent=item, prov=prov(f["bbox_px"]))
    return doc


def main():
    for sub in ("docling", "doclang"):
        if (GT / sub).exists():
            shutil.rmtree(GT / sub)
        (GT / sub).mkdir(parents=True)
    n = 0
    for p in sorted((GT / "gritworks").glob("*.json")):
        gt = json.loads(p.read_text())
        doc = build(gt)
        w, h = gt["image_size_px"]
        doc.save_as_json(GT / "docling" / p.name)
        (GT / "doclang" / (p.stem + ".dclg")).write_text(doc.export_to_doclang(xsize=int(w), ysize=int(h)))
        n += 1
    print(f"wrote {n} DoclingDocument + DocLang files")

    from doclang import validate
    report = {"files": n, "mode": None, "ok": 0, "failed": {}}
    # docling-core's serializer emits <doclang version=...> without an xmlns; the spec defines the
    # namespace https://www.doclang.ai/ns/v0 as the default, so we validate with allow_empty_namespace.
    mode = {"allow_empty_namespace": True}
    report["allow_empty_namespace"] = True
    try:
        validate(str(next((GT / "doclang").glob("*.dclg"))), **mode)
        report["mode"] = "xsd+schematron"
    except Exception as e:
        if type(e).__name__ == "SchematronBackendNotFound":
            mode["xsd_only"] = True
            report["mode"] = "xsd_only (no Schematron backend installed)"
        else:
            report["mode"] = "xsd+schematron"
    for f in sorted((GT / "doclang").glob("*.dclg")):
        try:
            validate(str(f), **mode)
            report["ok"] += 1
        except Exception as e:
            report["failed"][f.name] = (type(e).__name__ + ": " + str(e))[:600]
    (GT / "doclang_validation.json").write_text(json.dumps(report, indent=1))
    print(f"validation [{report['mode']}]: {report['ok']}/{n} ok, {len(report['failed'])} failed")
    for k, v in list(report["failed"].items())[:3]:
        print(" ", k, v[:300])


if __name__ == "__main__":
    main()
