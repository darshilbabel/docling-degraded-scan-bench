# Results summary (first pass)

Generated 2026-11-18 03:59 UTC · Docling 2.150.1 · arm64 Darwin 25.6.0 · CPU only · full-page OCR at the scan's native 150 DPI.

All numbers are on **synthetic GritWorks documents with simulated degradations**. Field metrics cover only the populated fields in the ground truth, not every printed word. Treat them as a first pass for methodology review, not a leaderboard.

## Counts

- Source pages: 37 (from 30 clean documents in 6 public sample packs)
- Page images: 260 = 37 pages × 6 synthetic conditions + 38 pack-native degraded pages
- Scored fields per synthetic condition: 766 (fields with <2 non-space characters, e.g. checkbox marks, are excluded: 45)
- ocrmac: 190 page images converted (27 source pages; 286.1 s total conversion time)
- rapidocr: 232 page images converted (33 source pages; 706.6 s total conversion time)
- easyocr: 133 page images converted (19 source pages; 1496.1 s total conversion time)

**Tables 1-5 compare engines on the common subset**: the page images that every engine supporting that script ran (EasyOCR's seeded, script-stratified subset). Table 6 shows each engine on every page it ran.

Common subset, Latin pages, per condition: ocrmac 14 pages / 291 fields, rapidocr 14 pages / 291 fields, easyocr 14 pages / 291 fields

## 1. Field exact match (EM, %) by degradation — Latin-script pages

EM = the normalised printed value appears inside the OCR text found in the field's box (case-insensitive, whitespace-collapsed).

| Engine | clean | blur | skew | photocopy | low_light | fax |
|---|---:|---:|---:|---:|---:|---:|
| ocrmac | 92.8 | 85.6 | 92.1 | 91.4 | 95.9 | 61.5 |
| rapidocr | 98.6 | 93.1 | 97.6 | 91.4 | 97.2 | 68.4 |
| easyocr | 70.5 | 4.8 | 62.2 | 57.0 | 63.6 | 17.2 |

## 2. Field CER (%) by degradation — Latin-script pages

CER = edit distance between the printed value and its best-matching span in the box text ÷ value length (micro-averaged, capped at 1 per field).

| Engine | clean | blur | skew | photocopy | low_light | fax |
|---|---:|---:|---:|---:|---:|---:|
| ocrmac | 3.4 | 3.2 | 5.2 | 1.1 | 0.7 | 7.6 |
| rapidocr | 0.2 | 1.2 | 0.3 | 1.1 | 0.5 | 9.5 |
| easyocr | 7.3 | 89.6 | 9.8 | 12.5 | 10.3 | 52.6 |

## 3. Field WER (%) by degradation — Latin-script pages

| Engine | clean | blur | skew | photocopy | low_light | fax |
|---|---:|---:|---:|---:|---:|---:|
| ocrmac | 6.7 | 10.7 | 9.1 | 7.9 | 3.6 | 33.5 |
| rapidocr | 1.8 | 8.3 | 3.0 | 9.3 | 4.0 | 27.8 |
| easyocr | 19.1 | 93.8 | 26.8 | 30.9 | 25.6 | 73.8 |

## 4. Indic pages (Devanagari: Hindi, Marathi; Bengali) — field EM % / CER %

| Engine | Script | clean | blur | skew | photocopy | low_light | fax |
|---|---|---|---|---|---|---|---|
| ocrmac | Devanagari | n/a | n/a | n/a | n/a | n/a | n/a |
| ocrmac | Bengali | n/a | n/a | n/a | n/a | n/a | n/a |
| rapidocr | Devanagari | 44.9 / 26.9 | 16.3 / 57.5 | 36.7 / 31.9 | 26.5 / 34.5 | 38.8 / 35.9 | 12.2 / 52.3 |
| rapidocr | Bengali | n/a | n/a | n/a | n/a | n/a | n/a |
| easyocr | Devanagari | 42.9 / 42.2 | 8.2 / 87.6 | 32.6 / 40.9 | 20.4 / 74.2 | 30.6 / 68.3 | 2.0 / 94.0 |
| easyocr | Bengali | 41.9 / 35.7 | 0.0 / 100.0 | 54.8 / 42.4 | 32.3 / 54.9 | 35.5 / 43.4 | 3.2 / 96.4 |

`n/a` = the engine has no recognition model for that script in this setup (Apple Vision has no Indic scripts; RapidOCR's ONNX models have no Bengali).

## 5. Pack-native degraded pages (all scripts) — EM % / CER %

These are the degraded PDFs shipped in the packs; each covers a different subset of documents, so compare engines within a column, not across columns.

| Engine | blur | coffee_stain | crop | low_light | photocopy | photocopy_coffee_stain | skew |
|---|---|---|---|---|---|---|---|
| ocrmac | 0.0 / 96.0 (n=73) | 100.0 / 0.0 (n=16) | 82.3 / 2.0 (n=17) | 95.2 / 0.4 (n=21) | 94.1 / 1.6 (n=68) | 78.3 / 6.1 (n=60) | 97.2 / 0.2 (n=36) |
| rapidocr | 0.0 / 93.7 (n=73) | 100.0 / 0.0 (n=16) | 64.7 / 15.5 (n=34) | 69.6 / 17.8 (n=46) | 90.7 / 5.0 (n=75) | 100.0 / 0.0 (n=60) | 100.0 / 0.0 (n=36) |
| easyocr | 0.0 / 100.0 (n=104) | 68.8 / 6.5 (n=16) | 50.0 / 29.2 (n=34) | 28.3 / 47.1 (n=46) | 68.0 / 10.7 (n=75) | 88.3 / 2.4 (n=60) | 69.4 / 2.7 (n=36) |

## 6. Full set: each engine on every Latin page it ran — field EM %

| Engine | pages | clean | blur | skew | photocopy | low_light | fax |
|---|---:|---:|---:|---:|---:|---:|---:|
| ocrmac | 27 | 93.2 | 78.6 | 95.6 | 91.5 | 96.4 | 63.0 |
| rapidocr | 27 | 98.2 | 94.1 | 97.5 | 90.9 | 96.9 | 67.2 |
| easyocr | 14 | 70.5 | 4.8 | 62.2 | 57.0 | 63.6 | 17.2 |

## 7. Speed and stability (Latin pages, common subset)

| Engine | sec/page (clean) | drift CER vs own clean output, mean over degradations (%) |
|---|---:|---:|
| ocrmac | 1.67 | 20.9 |
| rapidocr | 3.58 | 21.5 |
| easyocr | 10.07 | 49.3 |

## 8. Best and worst degradation per engine (Latin, common subset, by field EM)

- **ocrmac**: clean 92.8% → best low_light 95.9%, worst fax 61.5%
- **rapidocr**: clean 98.6% → best skew 97.6%, worst fax 68.4%
- **easyocr**: clean 70.5% → best low_light 63.6%, worst blur 4.8%

## Ablation: OCR scale 1.0 (main run) vs 3.0 (Docling default)

4 Latin pages (banking__w2__p1, ocr__credit_memo__p1, ocr__purchase_order__p1, us_kyc__proof_of_address__p1), conditions clean, blur, fax; field EM % / CER % / sec per page.

| Engine | Condition | scale 1.0 | scale 3.0 |
|---|---|---|---|
| ocrmac | clean | 97.6 / 0.3 / 1.42 | 97.6 / 0.3 / 1.53 |
| ocrmac | blur | 96.4 / 0.3 / 1.44 | 98.8 / 0.1 / 0.86 |
| ocrmac | fax | 77.4 / 2.8 / 1.2 | 76.2 / 3.2 / 0.92 |
| rapidocr | clean | 100.0 / 0.0 / 2.62 | 100.0 / 0.0 / 1.84 |
| rapidocr | blur | 100.0 / 0.0 / 2.36 | 97.6 / 0.2 / 1.51 |
| rapidocr | fax | 79.8 / 3.6 / 2.3 | 79.8 / 3.4 / 1.62 |
| easyocr | clean | 73.8 / 6.0 / 7.33 | 78.6 / 4.0 / 13.68 |
| easyocr | blur | 3.6 / 81.3 / 7.27 | 4.8 / 84.9 / 14.34 |
| easyocr | fax | 27.4 / 40.3 / 7.09 | 17.9 / 40.2 / 13.68 |

## Ablation: EasyOCR confidence_threshold 0.5 (Docling default, main run) vs 0.0

Pages: banking__w2__p1, ocr__credit_memo__p1, ocr__purchase_order__p1, us_kyc__proof_of_address__p1; scale 1.0; field EM % / CER %.

| Condition | threshold 0.5 | threshold 0.0 |
|---|---|---|
| clean | 73.8 / 6.0 | 76.2 / 2.5 |
| blur | 3.6 / 81.3 | 8.3 / 27.9 |
| fax | 27.4 / 40.3 | 36.9 / 11.3 |

Note: the three engines ran as parallel processes on one laptop, so sec/page values interfere with each other; use them as an ordering only.

## Engines skipped

- **paddleocr**: Not run on this Mac by policy (too heavy locally); not a built-in Docling OCR engine.
- **nemotron_ocr**: NVIDIA Nemotron-OCR targets CUDA GPUs; not runnable on a Mac CPU.
- **kserve_v2**: Remote inference service, not a local engine.
- **auto**: OcrAutoOptions only picks one of the engines above; it would duplicate a row.
- **vlm_presets (minicpm_ocr, granite_docling, glm_ocr, lightonocr, dots_ocr, ...)**: VLM conversion presets, not OCR-engine presets; 0.3B-27B parameter models that need a GPU (or many minutes per page on CPU). MiniCPM-OCR (added in v2.149.0) is proposed for a GPU run, see REVIEW_NOTES.md.
- **tesseract**: Tesseract binary not installed on this machine (brew install tesseract tesseract-lang to enable).
- **ocrmac on Bengali, Devanagari pages**: No recognition model for this script in this engine/setup; those pages are not scored for it.
- **rapidocr on Bengali pages**: No recognition model for this script in this engine/setup; those pages are not scored for it.

Per-family breakdowns are in `metrics.json` (`engine_family_condition`); per-field detail is in `page_scores.jsonl`.
