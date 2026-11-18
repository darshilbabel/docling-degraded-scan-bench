"""Download the six public GritWorks sample packs, verify SHA-256, and extract each into its own
new empty directory under _src/. Archives are treated as data: members are checked for path
traversal and nothing inside them is executed.

Run:  .venv/bin/python -I scripts/fetch_packs.py
"""
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://gritworks-datasets-public.s3.ap-south-1.amazonaws.com/samples/2026-11/"
PACKS = {
    "GritWorks_OCR_10_PDFs_JSON_BBoxes.zip": "990225ee83cf40cedd44f6fdb39c3c2951a44e64e0ab8d844abf052bbc426083",
    "GritWorks_Banking_10_PDFs_JSON_BBoxes_v2.zip": "c4f3fbddc40ecf40b219e1d291b11edcfcac901fdb8a830fb4494354455cad77",
    "GritWorks_Insurance_10_PDFs_JSON_BBoxes.zip": "4fb527602cc67d0a91bef8419b688ed97b92599472583e1f8b3600d16863c78b",
    "GritWorks_Diagnostics_10_PDFs_JSON_BBoxes.zip": "f8871e38fed125ed77689846bd4fbfb1aa65e2b0ddfe583be895cef03b0c6b0d",
    "GritWorks_US_KYC_10_PDFs_JSON_BBoxes.zip": "e96a2719eafb032ae6411d254b1d805a6a1c5e119f51c30c7fe888f56ab1d462",
    "GritWorks_Indian_Languages_10_PDFs_JSON_BBoxes.zip": "334976ca31a7e58dabdd00e853f1617b08da58139f3192612b8c0701ef762ecf",
}


def main():
    dl = ROOT / "_dl"
    dl.mkdir(exist_ok=True)
    for name, sha in PACKS.items():
        z = dl / name
        if not z.exists():
            urllib.request.urlretrieve(BASE + name, z)
        got = hashlib.sha256(z.read_bytes()).hexdigest()
        if got != sha:
            raise SystemExit(f"SHA-256 mismatch for {name}: {got}")
        dest = ROOT / "_src" / z.stem
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():
                target = (dest / m).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise SystemExit(f"unsafe path in {name}: {m}")
            zf.extractall(dest)
        print(f"ok {name}")


if __name__ == "__main__":
    main()
