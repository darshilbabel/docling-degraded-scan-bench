"""Inventory the GritWorks public sample packs extracted under _src/.
Reads manifest.json + per-document GT JSON; never executes anything from the packs."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "_src"

def main():
    rows = []
    for man in sorted(SRC.glob("*/*/manifest.json")):
        pack_dir = man.parent
        m = json.loads(man.read_text())
        for d in m["documents"]:
            boxes = json.loads((pack_dir / d["boxes"]).read_text())
            gt = json.loads((pack_dir / d["json"]).read_text())
            nbox = sum(1 for f in boxes["fields"] if f.get("bbox"))
            rows.append(dict(pack=m.get("pack") or m.get("name"), id=d["id"], pdf=str(pack_dir.relative_to(ROOT) / d["pdf"]),
                             variant=d["variant"], pages=d["pages"], fields=len(boxes["fields"]),
                             fields_with_bbox=nbox, words=sum(len(f.get("words") or []) for f in boxes["fields"]),
                             doc_type=gt.get("document_type"), language=gt.get("language"), script=gt.get("script"),
                             page_sizes_pt=gt.get("page_sizes_pt")))
    out = ROOT / "data" / "inventory.json"
    out.write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(f'{r["pack"][:18]:18} {r["id"]:42} {r["variant"]:13} p={r["pages"]} f={r["fields"]:3} bb={r["fields_with_bbox"]:3} w={r["words"]:3} {r["language"]}/{r["script"]} | {r["doc_type"]}')
    print(len(rows), "documents")

if __name__ == "__main__":
    main()
