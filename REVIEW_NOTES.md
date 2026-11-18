# Review notes: open methodology questions

For: Darshil (GritWorks) and Michele Dolfi (IBM Research, Docling)
Status: first-pass run, 2026-11-17. Nothing has been published yet.

These notes list the choices we made for the first pass and the questions we would like the Docling team to weigh in on before the dataset and code go public. Each item gives what we did now and the options we see.

---

## A. Ground truth and data

### A1. Field-level GT, not full-page transcripts
- **Now:** The packs annotate *selected populated fields*: each field's printed value and its box. Static form labels, instructions and disclosure text are not annotated. We therefore score at field level, by checking whether each printed value appears in the OCR output near its box.
- **Consequence:** We cannot compute a classic page-level CER/WER, or docling-eval's word-level OCR F1, without penalising engines for reading unannotated text.
- **Question:** Is field-level scoring acceptable for a Docling blog post? Or should the final version add full-page word transcripts? We can generate those from the authoring templates for the clean pages; the degraded versions inherit them.

### A2. Matched pairs: generated vs pack-native degradations
- **Now:** Each public pack has one clean PDF and *one* degraded PDF per document, and each document gets a different degradation. That does not give a balanced matrix. We therefore generated five degradations from every clean page with `scripts/build_pairs.py` at a fixed seed: blur, skew, photocopy (contrast + JPEG + specks), low light and fax (204×98 dpi binarisation + streaks). The pack's own degraded PDFs are reported separately as "native" conditions.
- **Question:** Are these five the right axes? Possible additions are perspective warp, moiré from phone photos of screens, stamps or handwriting over printed fields, and severity levels (mild, medium, strong) per axis. Severity levels would let the post show degradation curves rather than single points.

### A3. Field exclusions
- Fields whose printed value has fewer than 2 non-space characters (checkbox "X", "F", single digits) are excluded from scoring: 45 of 811 fields per condition (5.5%). Checkboxes are better scored as `<checkbox class="selected">` detection than as OCR.
- **Question:** Should checkbox state be a separate metric in v1?

### A4. Dataset size for the final version
- **Now:** 37 source pages from 30 clean documents in 6 packs, giving 260 page images (37 × 6 synthetic conditions + 38 pack-native). Of these, 27 pages are Latin script, 6 Devanagari (Hindi, Marathi) and 4 Bengali. This is small. Per-cell confidence intervals on 50–200 fields are wide, roughly ±5–10 pp for EM.
- **Options:**
  1. ~300 source pages (about 50 per family) × 5 degradations × 3 severities ≈ 4,500 images. This is still laptop-friendly for ocrmac and RapidOCR, but needs a GPU or a few hours for EasyOCR.
  2. 1,000+ source pages for a docling-eval-sized benchmark, with the GPU and VLM presets run on a cloud box.
- **Question:** What size makes the post credible without making reproduction painful? We lean toward option 1 and would publish bootstrap CIs.

### A4b. Ground-truth quality issues found by this run
- **Printed form vs pack display string: FIXED in v0.1.1.** Some `display_value`s did not match the page. The passport printed "12 Jan 2021" where the GT had "12 Jan, 2021"; Banking amounts were printed with `$` but stored without it; Marathi comb fields were printed one character per box. The scored `display_value` is now the printed form, and the pack's string is kept as `canonical_value`. The rules are described in the README under "Printed-form rule"; 42 of 811 fields per condition changed. The images are byte-identical, so the saved predictions were re-scored, not re-run.
  - *Effect:* ocrmac and RapidOCR moved by no more than about 1 point. EasyOCR fell 4–5 points on clean, skew, photocopy and low light, because it reads `$` as `S` and that is now counted.
  - *Open:* the passport issue date has a faint background mark after "Jan" that ocrmac reads as a comma; we judged it to be pattern, not print. Please confirm.
  - *Open:* should comb fields be scored with whitespace removed (current rule), or should the spacing be kept as printed?
- **MRZ.** The two MRZ lines are scored as single 44-character strings, and RapidOCR read one line reversed. Should MRZ get its own metric (check-digit validity)?
- **Homoglyphs.** Several misses are Cyrillic or Greek look-alikes (`3В` with a Cyrillic В from Apple Vision; `Ρ` with a Greek Rho from RapidOCR). Should normalisation fold confusables (Unicode TR39 skeletons), or is a homoglyph a real error for downstream use? We currently count it as an error.
- **Apple Vision on the clean lab report** skipped about 16 isolated numeric table cells that it read correctly on the skewed and low-light versions. This is a real engine behaviour, but it means "clean" is not always the upper bound per engine.

### A5. Synthetic only
- All documents are synthetic, generated by GritWorks; no real person or organisation appears. The degradations are simulated, not captured with real scanners or phones. We say so in the README, the dataset card and the post.
- **Question:** Would the Docling team want a small set of *real* captures of the same synthetic documents (printed, then photographed or faxed) as a sim-to-real check? We could produce one.

---

## B. Field matching rules (most important to agree on)

The current rules are implemented in `scripts/run_eval.py` → `score_page`.

1. **Normalisation:** Unicode NFKC, uppercase, collapse whitespace, and unify curly quotes and dashes.
2. **Region:** The field box is padded by 0.5 × the box height on every side. An OCR text line is taken if at least 50% of its height overlaps the padded box vertically and it overlaps it horizontally. The selected lines are concatenated in reading order (row, then x).
3. **EM (exact match, primary):** The normalised printed value is a substring of the normalised region text.
4. **EM-alnum (lenient):** The same check on letters, digits and combining marks only, so punctuation and spaces are ignored.
5. **EM-anywhere:** The value appears anywhere on the page. This is diagnostic: it separates "misread" from "found but outside the box".
6. **Field CER/WER:** The edit distance between the value and its best-matching contiguous span in the region text (semi-global alignment), divided by value length in characters or words. Each field is capped at 1, then the results are micro-averaged.
7. **Drift CER:** The CER between an engine's page text on the degraded page and the same engine's page text on the clean page. This measures stability without needing full transcripts.

**Questions:**
- **Substring vs exact cell match.** Is substring matching too lenient? A line "TOTAL DUE $44.00" contains "$44.00", but docling-eval's KV matching uses exact equality or edit distance ≤ 3. Should we report a stricter "the line equals the value" score too?
- **Format variants.** The GT stores both a normalised `value` (e.g. `1987-08-19`) and the printed `display_value` (`08 19 1987`). We score against `display_value`, which tests OCR rather than normalisation. Agreed?
- **Padding.** 0.5 × box height is a guess. Too small and skew or crop pages lose lines whose boxes shifted; too large and neighbouring fields leak in. Should we sweep it and report sensitivity?
- **Docling layout-assembled text vs raw OCR cells.** We score raw OCR text-line cells (`parsed_page.textline_cells`), not the assembled DoclingDocument text. Assembly can drop cells outside layout clusters. Should the blog report both?

---

## C. Engines and settings

### C1. Engines run (CPU, Mac M4, docling 2.150.1)
- **ocrmac** (Apple Vision), **RapidOCR** (onnxruntime; Docling's default engine) and **EasyOCR** (PyTorch CPU).

### C2. Engines skipped, and why
- **Tesseract** (CLI and tesserocr): the binary is not installed on this Mac. It is one `brew install tesseract tesseract-lang` away, so we propose adding it before publishing.
- **PaddleOCR:** not run on this Mac by policy, and not a built-in Docling engine.
- **Nemotron-OCR:** NVIDIA GPU.
- **KServe v2:** remote service.
- **VLM presets, including MiniCPM-OCR:** GPU-class models.
- **Script gaps:** Apple Vision has no Indic scripts, and RapidOCR's ONNX models have no Bengali. Those cells are reported as `n/a`, not 0.

### C3. MiniCPM-OCR preset on GPU, and VLM presets in general
- The `minicpm_ocr` preset (v2.149.0, `openbmb/MiniCPM-OCR-1.0`, 1.3B parameters, markdown output) is a **VLM conversion preset**, not an OCR engine. It replaces layout and OCR and returns markdown *without per-word boxes*.
- **Proposal:** run it, and perhaps `granite_docling` and one LightOnOCR preset, on a single cloud GPU (e.g. one A10G/L4 for under an hour) over the same 260 images. Score with **EM-anywhere and field CER against the full page text**, since there are no boxes. Report those columns separately so readers do not compare box-aware and box-free scores directly.
- **Questions:** Does the Docling team want this in the first post or a follow-up? Is there a preferred engine type (Transformers vs vLLM) and batch setting for fair timing?

### C4. `scale=1.0` instead of the default 3.0
- For image inputs, Docling treats one pixel as one point and upsamples the page 3× before OCR. Our pages are 150 DPI scans, so the default means OCR on a ~450 DPI upsample. We used `scale=1.0`, OCR at the scan's native pixels, which cut EasyOCR time by about 2×.
- **Question:** Is this the right "preset" behaviour to report, or should the main table use the defaults? We can add a `scale=3.0` ablation.

### C4b. EasyOCR `confidence_threshold`
- Docling's EasyOCR default drops text cells with confidence < 0.5. On 4 ablation pages, setting it to 0.0 changed field CER from 6.0 to 2.5 (clean), from 81.3 to 27.9 (blur) and from 40.3 to 11.3 (fax). EM rose by only 2–10 points, because punctuation errors remain (e.g. `/` read as `1`, `$` as `S`). See `results/ablation_easyocr_conf.md`.
- **Question:** Should the main table use each engine's defaults ("what users get") or tuned thresholds ("what the engine can do")? We lean toward defaults plus a tuned column.

### C4c. Timing was measured with engines running concurrently
- To stay within the 60-minute budget, ocrmac, RapidOCR and EasyOCR ran as three parallel processes, so their timings interfere with each other. In the isolated ablation, RapidOCR ran at about 1.5–2.6 s/page instead of 3.3 s. For the blog we should either re-time one engine at a time or report speed only as an ordering.

### C5. Other settings
- `force_full_page_ocr=True`; table structure off; CPU device for both layout and OCR.
- EasyOCR uses `["hi","en"]` for Hindi, `["mr","en"]` for Marathi and `["bn","en"]` for Bengali. RapidOCR uses `["devanagari"]`. Latin pages use `en`/`en-US`.

---

## D. Formats

- Ground truth is shipped as (1) the original GritWorks JSON, (2) DoclingDocument JSON with `field_region` → `field_item` → key/value plus TOPLEFT pixel boxes, and (3) DocLang `.dclg` with the location grid set to the image size, so it is lossless at integer pixels. All 260 GT files pass `doclang.validate` (XSD + Schematron) with `allow_empty_namespace=True`.
- Docling's predictions are saved as `.dclg` too.
- **Questions for the Docling team:**
  1. docling-core's `export_to_doclang` omits `xmlns="https://www.doclang.ai/ns/v0"`. Is that intended?
  2. docling-eval's `KeyValueEvaluator` reads `key_value_items`, not `field_items`. Should we also emit `key_value_items`, or would you prefer a field-item-aware evaluator upstream?
  3. Should the HF dataset follow docling-eval's parquet `DatasetRecord` layout, so `docling-eval evaluate` works directly?

---

## E. Before publishing (checklist)

- [ ] Agree on matching rules (B) and dataset size (A4).
- [ ] Add Tesseract; decide on the GPU or VLM run (C3).
- [ ] Run EasyOCR on all 37 pages (it ran on a 19-page stratified subset); re-time engines one at a time (C4c).
- [x] Fix printed-form mismatches (A4b), done in v0.1.1.
- [ ] Confirm the passport issue-date reading and the comb-field rule (A4b).
- [ ] Re-run with severity levels and bootstrap CIs.
- [ ] Final licence check: CC BY 4.0 for data, Apache-2.0 for code.
- [ ] Michele reviews the blog draft; GritWorks is named only as dataset provider.
- [ ] Create the GitHub repo and HF dataset (not done yet, by design).
