# Degraded-scan OCR benchmark for Docling

This benchmark uses matched clean/degraded document pages with field-level ground truth and bounding boxes. It ships code that runs Docling's OCR engines over every pair and reports accuracy per degradation type.

> **Status: first pass (v0.1.1, 2026-11-18), public. Methodology review with the Docling team is in progress; numbers may change.**
> The data is **synthetic**, the degradations are **simulated**, and the results below are **preliminary**. See [Limitations](#limitations) and [REVIEW_NOTES.md](REVIEW_NOTES.md).

## Why

Most OCR comparisons report a single accuracy number on clean pages. In practice the same form arrives blurred, skewed, photocopied, photographed in poor light or faxed. This benchmark holds the document constant and varies only the capture conditions. Any change in accuracy is therefore attributable to the degradation, not to a different document.

## Dataset

- **Source.** Six public GritWorks sample packs: OCR & Extraction, Banking, Insurance, Diagnostics, US KYC and Indian Languages. All documents are synthetic, generated from templates, and use fictional people, organisations, identifiers and amounts. ID and passport pages are specimens.
- **37 source pages** from 30 clean documents. 27 are Latin script; 6 are Devanagari (Hindi, Marathi) and 4 are Bengali.
  - **Families:** invoices and purchase orders, bank and account statements, paystub, W-2, utility bills, CMS-1500 claim, insurance statements and EOB, lab requisition, lab report, patient forms, passport and ID specimens, and Indian savings-scheme and account-opening forms.
- **260 page images** at 150 DPI:
  - 37 × 6 synthetic conditions: `clean`, `blur`, `skew`, `photocopy`, `low_light` and `fax`.
  - 38 `native:*` pages: the degraded PDFs that ship in the packs (photocopy, blur, coffee stain, low light, crop, skew and bad photo), with the packs' own projected boxes.
- **Ground truth per field:** the field name, the printed text (`display_value`, the scored value), the pack's original display string (`canonical_value`), the normalised value, a box in image pixels (plus a polygon for skew), and visibility. There are 766 scored fields per condition. A further 45 fields are kept but not scored: checkbox marks and one-character flags.
- **Why we generated degradations.** Each pack ships exactly one degraded variant per document, and that variant differs from document to document. That gives no balanced clean × degradation matrix. `scripts/build_pairs.py` therefore generates the five synthetic conditions from every clean page with a fixed seed, so the ground truth carries over exactly. Photometric changes leave coordinates untouched, and skew boxes go through the same affine matrix as the image. All parameters are stored in each GT file.

### Formats

| path | format |
|---|---|
| `data/gt/gritworks/*.json` | the original GritWorks field schema, with boxes converted to image pixels |
| `data/gt/docling/*.json` | `DoclingDocument` (docling-core): `field_region` → `field_item` → key/value, TOPLEFT pixel boxes |
| `data/gt/doclang/*.dclg` | [DocLang](https://doclang.ai) 0.9 via `DoclingDocument.export_to_doclang`; location grid = image size, so lossless at integer pixels |
| `results/predictions/<engine>/*.dclg` | Docling's output for each page, also as DocLang |

All 260 ground-truth `.dclg` files pass the reference validator (`doclang validate`, XSD + Schematron). One caveat: docling-core omits the `xmlns`, so validation runs with `allow_empty_namespace`; see [RESEARCH.md](RESEARCH.md).

## Reproduce

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -I scripts/fetch_packs.py      # download 6 public packs, verify SHA-256, extract to _src/
.venv/bin/python -I scripts/inventory.py        # data/inventory.json
.venv/bin/python -I scripts/build_pairs.py      # data/images, data/gt/gritworks, data/pairs.jsonl
.venv/bin/python -I scripts/to_doclang.py       # data/gt/docling, data/gt/doclang + validation report
.venv/bin/python -I scripts/run_eval.py         # results/*.json, results/SUMMARY.md
```

`scripts/build_pairs.py` is deterministic: rebuilding gives byte-identical images. To re-score without running OCR, copy the Hugging Face `predictions/` folder to `results/predictions/` and run `run_eval.py --aggregate-only`.

`run_eval.py` runs each engine in its own process. It skips pages that already have saved predictions; use `--force` to recompute them.
- `--aggregate-only` rescores the saved predictions, which is useful when changing matching rules.
- `--engines`, `--conditions` and `--limit-pages` select subsets.
- `--engine-pages easyocr=19` sets the per-engine page cap used in the first pass.

### Engines and settings

| engine | status | notes |
|---|---|---|
| ocrmac (Apple Vision) | run | macOS only; Vision has no Indic scripts, so Indic cells are `n/a` |
| RapidOCR (onnxruntime) | run | Docling's default engine; `en` for Latin, `devanagari` for Hindi and Marathi; no Bengali model |
| EasyOCR (PyTorch, CPU) | run on a 19-page stratified subset | about 15–20 s per page on CPU, so the full set would exceed the 60-minute budget |
| Tesseract (CLI / tesserocr) | skipped | not installed on the run machine; supported by the script once installed |
| PaddleOCR | skipped | not run locally by policy; not a built-in Docling engine |
| Nemotron-OCR | skipped | NVIDIA GPU |
| KServe v2 | skipped | remote service |
| VLM presets (MiniCPM-OCR, granite-docling, …) | skipped | GPU-class models with no per-word boxes; proposed as a separate GPU run |

Docling 2.150.1 runs on CPU with `force_full_page_ocr=True`, table structure off, and **`ocr scale=1.0`**. That means OCR at the scan's native 150 DPI instead of Docling's default 3× upsample; see REVIEW_NOTES C4. The exact versions, thread counts and per-engine page subsets are in `results/run_meta.json`.

### Printed-form rule (ground-truth correction, v0.1.1)

The scored value (`display_value`) must equal what is printed on the page. In some places the packs' own `display_value` was a formatted variant of the printed text, so `scripts/build_pairs.py` applies these rules in order and keeps the pack's string as `canonical_value`:

1. **Manual, verified.** Packs without authored word boxes use hand-checked corrections in `data/gt_corrections.json`, each verified against a 576 DPI render. This affects 3 passport fields: "12 Jan, 2021" → "12 Jan 2021", "12 Jan, 2031" → "12 Jan 2031" and "CALIFORNIA, U.S.A." → "CALIFORNIA, U.S.A".
2. **Authored words.** Where a pack ships word boxes for the clean page (the exact text authored before rasterisation), the printed form is those words joined by single spaces. This restores the `$` sign on 28 Banking amounts, e.g. "13,943.16" → "$13,943.16".
3. **Comb fields.** If every authored word is a single character (one character per printed box), the field gets `comb: true` and is scored with whitespace removed. This affects 11 Marathi CIF fields (dates, PAN, mobile, PIN).

Case is stored as printed; scoring is case-insensitive. Each field records which rule applied in `printed_form_rule`. In total, 42 of 811 fields per condition changed.

We checked every pack for dates, currency and case. The authored-word comparison covers the 14 documents that ship word boxes. For the 16 that do not, every Latin field that neither ocrmac nor RapidOCR matched case-sensitively on the clean page was reviewed visually; only the passport fields were wrong. Separately, a scan for `$`, `€`, `£`, `₹` or `%` printed next to a value found nothing beyond the Banking fields above. Indic fields in packs without word boxes could not be OCR-screened, because accuracy there is too low, but all three Indic documents ship word boxes.

## Metrics

All metrics are computed per field, then aggregated per engine × condition (and per script and per family in `metrics.json`). Text is normalised with NFKC, uppercase and collapsed whitespace.

- **Field EM (primary).** The printed value appears as a substring of the OCR text lines that fall in the field's box. The box is padded by half its height, and a line counts if at least half its height overlaps the box.
- **Field EM-alnum.** The same check on letters, digits and combining marks only.
- **Field EM-anywhere.** The value appears anywhere on the page. This is diagnostic: it separates "misread" from "found outside the box".
- **Field CER / WER.** The edit distance (characters or words) between the printed value and its best-matching contiguous span in the box text, divided by the value length. Each field is capped at 1, and the results are micro-averaged over fields.
- **Drift CER.** The CER between an engine's page text on a degraded page and its own text on the clean page. It shows how much the output changes, without needing a full-page transcript.

Full-page CER/WER against a complete transcript is **not** reported. The ground truth covers populated fields only, not every printed word.

## First-pass results

See [`results/SUMMARY.md`](results/SUMMARY.md) for all tables, and `results/metrics.json` / `results/page_scores.jsonl` for the detail.

Common subset: 14 Latin pages (291 scored fields per condition), with identical images for every engine. The table shows **field EM %** (higher is better), with field CER % in brackets (lower is better).

| Engine | clean | blur | skew | photocopy | low light | fax |
|---|---|---|---|---|---|---|
| ocrmac | 92.8 (3.4) | 85.6 (3.2) | 92.1 (5.2) | 91.4 (1.1) | 95.9 (0.7) | 61.5 (7.6) |
| RapidOCR | 98.6 (0.2) | 93.1 (1.2) | 97.6 (0.3) | 91.4 (1.1) | 97.2 (0.5) | 68.4 (9.5) |
| EasyOCR | 70.5 (7.3) | 4.8 (89.6) | 62.2 (9.8) | 57.0 (12.5) | 63.6 (10.3) | 17.2 (52.6) |

- **Fax** is the hardest synthetic condition for every engine. **Blur** is the hardest for EasyOCR, and the pack-native "strong blur" defeats all three engines (0% EM).
- On the full 27 Latin pages, ocrmac and RapidOCR show the same ordering: fax is worst for both, and photocopy is RapidOCR's second-worst (90.9%).
- **Indic.** RapidOCR (Devanagari) and EasyOCR (Devanagari, Bengali) reach only about 42–55% field EM even on clean pages; Apple Vision has no Indic support.
- **Ablations** (`results/ablation_*.md`, 4 pages). OCR `scale=3.0` (Docling's default) instead of 1.0 changes EM by at most a few points but doubles EasyOCR's time. EasyOCR's `confidence_threshold=0.5` default drops much of the text on degraded pages: setting it to 0.0 cuts blur CER from 81% to 28% and fax CER from 40% to 11%. **EasyOCR's low numbers therefore partly reflect a default filter, not only recognition quality.**
- Speeds in SUMMARY.md were measured with the three engines running in parallel on one laptop. Use them only as a rough ordering (ocrmac < RapidOCR < EasyOCR).

## Limitations

- **Synthetic data.** The documents are template-generated, with clean typography and consistent layouts. Real archives have more variety in fonts, handwriting, stamps and layout.
- **Simulated degradations.** Blur, skew, photocopy, low light and fax are image-processing simulations with one severity band each. They approximate, but do not reproduce, real scanners, fax machines and phone cameras.
- **Small sample.** 37 source pages; EasyOCR ran on 19 of them. Differences of a few points are within noise. The main tables therefore compare engines on the identical page subset.
- **Field-level ground truth.** Static labels and disclosure text are not annotated, so we cannot score full-page OCR or reading order.
- **Matching rules shape the numbers.** Substring matching inside a padded box is fairly lenient; see REVIEW_NOTES B for the open questions.
- **Settings.** `scale=1.0`, CPU only, table structure off. Docling's defaults or a GPU would change both speed and possibly accuracy.
- **Not a product comparison.** This measures open-source OCR engines inside Docling on one synthetic set. It does not rank vendors or tools in general.

## Licence

- **Data** (`data/`, published tables): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **Code** (`scripts/`): [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

Both texts are in [LICENSE](LICENSE). Docling, EasyOCR, RapidOCR, ocrmac and the other dependencies keep their own licences.

## Repository layout

```
scripts/        fetch_packs.py, inventory.py, build_pairs.py, to_doclang.py, run_eval.py,
                ablation_scale.py, ablation_easyocr_conf.py, make_hf.py
data/           pairs.jsonl, inventory.json, gt_corrections.json, gt/{gritworks,docling,doclang}/
                (images/ is not in git: ≈352 MB, on Hugging Face or rebuilt by build_pairs.py)
results/        SUMMARY.md, metrics.json, page_scores.jsonl, run_meta.json, ablation_*.md
                (predictions/<engine>/ is not in git: 9 MB, on Hugging Face under predictions/)
hf/README.md    Hugging Face dataset card; scripts/make_hf.py assembles the rest of hf/ for upload
RESEARCH.md     DocLang, Docling OCR presets and docling-eval notes, with links
REVIEW_NOTES.md open methodology questions
BLOG_DRAFT.md   draft post for the Docling blog
```
