---
license: cc-by-4.0
language:
- en
- hi
- mr
- bn
pretty_name: Degraded-Scan OCR Pairs (synthetic, field-level ground truth)
size_categories:
- n<1K
task_categories:
- image-to-text
- object-detection
tags:
- ocr
- document-ai
- synthetic
- docling
- doclang
- benchmark
- forms
- degradation
configs:
- config_name: default
  data_files:
  - split: synthetic
    path: synthetic.jsonl
  - split: native
    path: native.jsonl
---

# Degraded-Scan OCR Pairs

This dataset holds matched **clean / degraded** page images of synthetic business and government-style forms. Each page comes with **field-level ground truth**: the printed value of every annotated field, plus its bounding box. It is built to measure how OCR accuracy changes as the same page is blurred, skewed, photocopied, shot in low light or faxed.

It is a companion to an open evaluation of Docling's OCR engines. The code is in the accompanying GitHub repository (Apache-2.0), and the first-pass results are in its `results/SUMMARY.md`.

> **Status: first pass (v0.1.1, 2026-11-18; printed-form ground-truth fix), shared for methodology review.** The schema, size and matching rules may still change.

## At a glance

| | |
|---|---|
| Source pages | 37 (from 30 clean documents) |
| Page images | 260 = 37 × 6 synthetic conditions + 38 degraded pages shipped with the source packs |
| Scored fields | 766 per condition (plus 45 checkbox/one-character fields kept but not scored) |
| Scripts | Latin (27 pages), Devanagari: Hindi and Marathi (6), Bengali (4) |
| Families | invoices and purchase orders, bank and account statements, paystub, W-2, utility bills, CMS-1500 claim, EOB and premium statements, lab requisition, lab report, patient forms, passport and ID specimens, Indian savings-scheme and account-opening forms (Hindi, Marathi, Bengali) |
| Resolution | 150 DPI RGB PNG |
| Licence | CC BY 4.0 |

## Conditions

| condition | how it was made |
|---|---|
| `clean` | the clean page rendered at 150 DPI |
| `blur` | Gaussian blur, σ = 1.6–2.2 px |
| `skew` | rotation of ±2–5°, white fill; boxes transformed with the same affine matrix (axis-aligned bbox plus `polygon_px`) |
| `photocopy` | grayscale, contrast ×1.6, uneven toner gradient, 0.2% toner specks, JPEG quality 18–29 |
| `low_light` | gamma 1.8–2.3, exposure ×0.45–0.6, vignette, sensor noise σ = 0.025–0.04, warm tint, JPEG quality 70 |
| `fax` | vertical resample ×98/204 (ITU-T T.4 standard mode), global threshold, 0.4% pixel flips, 2–5 scan-line streaks |
| `native:<variant>` | the degraded PDF shipped in the source pack (photocopy, blur, coffee stain, low light, crop, skew, "bad photo"), with the pack's forward-projected boxes |

All synthetic degradations are deterministic: the per-page seed is SHA-256 of `page_id|condition|20261117`, and the parameters used are stored in each ground-truth file. Photometric degradations leave coordinates unchanged.

## Files

Total: **2,156 files, 376 MB** (images 352 MB, ground truth 13 MB, saved predictions 9 MB).

Splits (config `default`):
- `synthetic`: 222 rows (37 pages × clean + 5 generated degradations), the matched-pair matrix.
- `native`: 38 rows, the degraded pages shipped in the source packs.

Each row has `file_name` (the image path), page and condition metadata, the paths to the ground truth in three formats, and the ground-truth `fields` inline.

```
synthetic.jsonl, native.jsonl       one row per page image (see above)
images/<page_id>/<condition>.png    150 DPI RGB
gt/gritworks/<page_id>.<condition>.json   GritWorks field schema, boxes in image pixels (top-left origin)
gt/docling/<page_id>.<condition>.json     DoclingDocument (docling-core): field_region -> field_item -> key/value with boxes
gt/doclang/<page_id>.<condition>.dclg     DocLang markup (https://doclang.ai), location grid = image size
gt_corrections.json                 hand-verified printed-form corrections (passport)
doclang_validation.json             validator report (260/260 pass, XSD + Schematron)
inventory.json                      what each source pack contains
predictions/<engine>/...            Docling OCR outputs used for the first-pass results (ocrmac, rapidocr, easyocr)
```

### Ground-truth record (GritWorks JSON)

```json
{
  "page_id": "insurance__cms1500_claim__p1", "condition": "skew",
  "family": "cms1500_claim", "language": "english", "script": "Latin",
  "image_size_px": [1425, 1851], "dpi": 150,
  "degradation_params": {"angle_deg": -3.1, "seed": 123456789},
  "fields": [
    {"key": "patient_name", "value": "AVERY MORGAN", "display_value": "MORGAN, AVERY", "canonical_value": "MORGAN, AVERY",
     "printed_form_rule": null, "comb": false,
     "bbox_px": [131.2, 345.0, 277.5, 368.4], "polygon_px": [[...], ...],
     "visibility": "visible", "scored": true}
  ]
}
```

`display_value` is the text exactly as printed on the page and is what OCR is scored against. `canonical_value` is the source pack's original display string; in 42 of 811 fields per condition it differs by formatting, such as a missing `$` or a comma. `printed_form_rule` records why, and `comb: true` marks one-character-per-box fields, which are scored with whitespace removed. `value` is the normalised answer, e.g. ISO dates, which is useful for downstream extraction tasks. The correction rules are documented in the repository README.

### DocLang

```xml
<doclang version="0.9">
  <head><default_resolution width="1425" height="1851"/></head>
  <field_region>
    <location value="131"/><location value="209"/><location value="1238"/><location value="1647"/>
    <field_item>
      <key>patient_name</key>
      <value><location value="131"/><location value="345"/><location value="278"/><location value="368"/>MORGAN, AVERY</value>
    </field_item>
  </field_region>
</doclang>
```

All 260 `.dclg` files pass `doclang validate` (XSD + Schematron, doclang 0.9.0) with `--allow-empty-namespace`, because docling-core's serialiser omits the `xmlns`.

## Intended use

- Measuring OCR robustness per degradation type and per script, using field exact match, field CER/WER, and drift relative to the clean page.
- Testing field-aware or layout-aware extraction on forms.

## Limitations (please read)

- **Synthetic documents.** GritWorks generated every document from templates. All people, organisations, identifiers, addresses and amounts are fictional, and the ID and passport pages are specimens, not real documents. Results may not transfer to real-world scans.
- **Simulated degradations.** The five synthetic conditions are image-processing simulations, not captures from real scanners, fax machines or phones. The pack-native variants were also generated.
- **Field-level, not full-page, ground truth.** Static labels, instructions and disclosure text are not annotated, so the data does not support full-page CER or word-level detection F1 without extra annotation.
- **Small.** With 37 source pages, per-cell confidence intervals are wide. Treat differences of a few points as noise.
- **Uneven native conditions.** Each pack-native condition covers a different subset of documents, so compare engines within a native condition, not across conditions.

## Provenance

The source documents are GritWorks' public sample packs (six packs: OCR & Extraction, Banking, Insurance, Diagnostics, US KYC, Indian Languages), downloaded over HTTPS and verified by SHA-256. No real customer data and no third-party document collections were used.

## Citation

```
@misc{degraded_scan_ocr_pairs_2026,
  title  = {Degraded-Scan OCR Pairs: matched clean/degraded synthetic forms with field-level ground truth},
  author = {GritWorks},
  year   = {2026},
  note   = {v0.1, first pass for methodology review},
  license= {CC BY 4.0}
}
```
