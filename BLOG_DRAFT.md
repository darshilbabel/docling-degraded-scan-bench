# Measuring Docling OCR presets on degraded scans

*Draft for the Docling blog. Authors: [Docling team author(s), TBC] and [author], GritWorks (dataset provider). Status: first-pass numbers for methodology review. Do not publish.*

Most OCR evaluations show a model a clean page and report one number. Production documents do not arrive like that. The same invoice turns up as a phone photo taken under a desk lamp, a third-generation photocopy, or a fax. If you are choosing an OCR engine inside Docling, the useful question is not "which engine is best?" but **"which engine degrades least on the kind of damage my documents actually have?"**

This post describes a small, open benchmark built to answer that question. Each page is held constant and only the capture conditions change. We then run Docling's CPU OCR engines over every version.

## The setup

**Matched pairs.** We started from 37 synthetic pages: invoices, purchase orders, bank and account statements, a paystub, a W-2, utility bills, a CMS-1500 claim, an explanation of benefits, lab requisition and report forms, passport and ID specimens, and Hindi, Marathi and Bengali account-opening forms. Every page has field-level ground truth: the value of each populated field exactly as printed (currency signs included), plus its bounding box. All people, identifiers and amounts are fictional.

From each clean page we generated five degraded versions with a fixed seed:

- **blur**: Gaussian, σ ≈ 2 px at 150 DPI
- **skew**: 2–5° rotation
- **photocopy**: harsh contrast, uneven toner, specks, heavy JPEG
- **low light**: gamma, vignette, sensor noise, warm cast
- **fax**: half vertical resolution, binarisation, scan-line streaks

Photometric changes leave coordinates untouched. For skew, the boxes go through the same affine transform as the image, so the ground truth carries over exactly. We also kept 38 degraded pages that came with the source data, such as coffee stains, crops and a very strong blur, as a separate "native" set. That makes 260 page images in total.

**Engines.** On a laptop CPU (Apple M4, Docling 2.150.1), we ran Docling's standard pipeline with full-page OCR and three engines:

- **RapidOCR**: Docling's default, on onnxruntime
- **EasyOCR**: PyTorch
- **ocrmac**: Apple Vision

Tesseract was not installed on the test machine and will be added. GPU-oriented options were left for a follow-up. These include Nemotron-OCR and the VLM presets, among them the MiniCPM-OCR preset added in v2.149.0. EasyOCR runs at about 10 s per page on CPU, so it ran on a seeded, script-stratified subset of 19 source pages. All engine comparisons below use the pages that every engine ran.

**Formats.** The ground truth ships three ways: the original JSON, `DoclingDocument` with `field_region` → `field_item` key/value pairs, and [DocLang](https://doclang.ai). The DocLang files are produced by docling-core's `export_to_doclang` and pass the reference validator (XSD and Schematron). Docling's predictions are saved as DocLang too, so both sides of the comparison use the same open format.

## What we measure

The ground truth covers populated fields, not every printed word. We therefore score fields rather than full pages:

- **Field exact match (EM)**: after Unicode and whitespace normalisation, does the printed value appear in the OCR text found inside the field's (padded) box?
- **Field CER and WER**: the edit distance between the value and its best-matching span in that box text, divided by the value length.
- **Drift CER**: how much an engine's page text changes between the clean and the degraded version of the same page.

Using the box matters. A value read correctly but attributed to the wrong place is still a problem for downstream extraction.

## Results

Field exact match, in %, on 14 Latin-script pages (291 fields per condition). Field CER, in %, is in brackets.

| Engine | clean | blur | skew | photocopy | low light | fax |
|---|---|---|---|---|---|---|
| ocrmac | 92.8 (3.4) | 85.6 (3.2) | 92.1 (5.2) | 91.4 (1.1) | 95.9 (0.7) | 61.5 (7.6) |
| RapidOCR | 98.6 (0.2) | 93.1 (1.2) | 97.6 (0.3) | 91.4 (1.1) | 97.2 (0.5) | 68.4 (9.5) |
| EasyOCR | 70.5 (7.3) | 4.8 (89.6) | 62.2 (9.8) | 57.0 (12.5) | 63.6 (10.3) | 17.2 (52.6) |

On the Indic pages (field EM, clean → fax):
- RapidOCR's Devanagari model goes from 44.9% to 12.2%.
- EasyOCR goes from 42.9% to 2.0% on Devanagari and from 41.9% to 3.2% on Bengali.
- Apple Vision has no Indic recognition, so ocrmac is not applicable.

On the native set, a strong blur that comes with the source data took all three engines to 0% EM.

## Takeaways by degradation

**Fax is the hardest synthetic condition for every engine.** Binarisation at half vertical resolution destroys thin strokes and punctuation. RapidOCR and ocrmac lose about 30 points of EM. Notably, their CER stays under 10%: most fields are *almost* right, with a lost slash, a broken digit or a merged word. If your pipeline validates fields such as dates and IDs against a format, fax output may be recoverable. If it needs exact strings, it mostly is not.

**Skew and low light are largely handled.** Both RapidOCR and ocrmac stay within a few points of their clean scores at 2–5° of rotation and under our low-light simulation. Drift CER is high under skew (around 30%), but that reflects text lines being reordered, not misread. It is a reminder that page-level text metrics punish reading-order changes that field-level metrics forgive.

**Photocopy mostly costs punctuation.** RapidOCR drops from 98.6% to 91.4% EM on photocopies. On the full 27-page Latin set, a lenient match that ignores spaces and punctuation scores 97.9% versus 90.9% for strict EM. Most of the gap is dropped spaces and separators, not wrong characters.

**Blur splits the engines.** Moderate blur costs RapidOCR and ocrmac 5–7 points. EasyOCR nearly stops returning text under Docling's default settings. An ablation showed why: Docling's EasyOCR integration drops cells below 0.5 confidence. Setting the threshold to 0 cut EasyOCR's blur CER from 81% to 28% on a four-page sample. Part of what looks like a recognition failure is a filtering default. This is worth knowing before you conclude an engine "can't read" a document.

## Takeaways by engine

- **RapidOCR**, Docling's default, was the most accurate on Latin pages in every condition, tying with ocrmac on photocopy (91.4% each). It was the only engine here with a working Devanagari model.
- **ocrmac** was the fastest option on a Mac and close in accuracy on most conditions. One surprise: on one clean lab report it skipped isolated numeric table cells that it read correctly on the skewed and low-light versions. "Clean" is not always the ceiling.
- **EasyOCR** is the one to tune. Its defaults were least robust in this setup, it is the slowest on CPU, and it is the only engine here that covers Bengali.
- **Indic forms are the open problem.** No CPU engine reached 60% field EM on clean Hindi, Marathi or Bengali forms. Under degradation, fax in particular, the numbers fall toward zero.

## Caveats

This is a first pass. The documents are synthetic and template-based. The degradations are simulations with one severity level each. The sample is small: 14–37 pages per comparison, so differences of a few points are noise. Our matching rule, a substring inside a padded box, is a choice we are still discussing. Speeds were measured with engines running side by side, so treat them as an ordering only. The next version will add Tesseract, severity sweeps, confidence intervals, real print-and-capture versions of a subset, and a GPU run of the VLM presets, including MiniCPM-OCR.

## Reproduce it

```bash
git clone <repo> && cd docling-bench
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -I scripts/fetch_packs.py
.venv/bin/python -I scripts/build_pairs.py
.venv/bin/python -I scripts/to_doclang.py
.venv/bin/python -I scripts/run_eval.py
```

The dataset is CC BY 4.0 and the code is Apache-2.0. `run_eval.py --aggregate-only` rescores saved predictions in seconds, so you can try your own matching rules. We would like to hear which degradations matter for your documents.

*The synthetic documents and ground truth in this benchmark were provided by GritWorks.*
