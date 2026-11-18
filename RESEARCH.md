# Research notes: DocLang, Docling OCR presets, docling-eval

Compiled 2026-11-17 for the degraded-scan benchmark. The sources are linked inline. Statements marked *(local)* were checked against the packages installed in this repo's `.venv`: docling 2.150.1, docling-core 2.107.1 and doclang 0.9.0.

## 1. DocLang (doclang.ai)

**What it is.** DocLang is an open, AI-native document markup standard. The site calls it "a constrained XML format built from the ground up for LLM tokenizers". It is a specification, not a converter. The LF AI & Data Foundation launched the DocLang Specification Working Group on 2026-06-09 under the Joint Development Foundation's governance model. The founding members are IBM, NVIDIA, Red Hat, ABBYY and HumanSignal. The specification is licensed under Apache-2.0.
- Site: https://doclang.ai
- Spec and reference toolkit: https://github.com/doclang-project/doclang (`spec.md` is authoritative; `exports/` holds other renderings)
- LF announcement: https://www.linuxfoundation.org/press/lf-ai-data-foundation-launches-doclang-specification-working-group-to-advance-an-open-standard-for-ai-native-documents
- ABBYY announcement: https://www.abbyy.com/company/news/doclang-ai-native-document-standard/

**Format essentials (spec v0.9).**
- The root element is `<doclang version="MAJOR.MINOR">`. The default namespace is `https://www.doclang.ai/ns/v0`. `<head>` is optional and must be the first child. It carries document properties such as `<default_resolution width=".." height=".."/>`.
- **Geometry.** A component's head may contain four `<location value="N"/>` children in the order x_min, y_min, x_max, y_max. The origin is the page's top-left corner. Values are integers in `[0, resolution)`. The resolution comes from `default_resolution` or a per-location `resolution` attribute, and falls back to 512.
- **Pagination.** `<page_break/>` separates pages, and `<page_header>`/`<page_footer>` mark furniture. `<thread thread_id>` joins content split across pages.
- **Text and structure.** `<text>`, `<heading level>`, `<list>`, `<table>` (OTSL tokens such as `<fcel/>`, `<ched/>` and `<nl/>`), `<picture>`, `<formula>`, `<code>` and `<footnote>`. Inline formatting includes `<bold>` and `<handwriting>`. `<layer value="body|background|furniture"/>` sets a component's layer.
- **Forms and key-value pairs.** These are expressed as `<field_region>` → `<field_item>` → `<key>` + `<value class="read_only|fillable">`. Optional elements are `<field_heading>`, `<hint>`, `<checkbox class="selected|unselected"/>` and `<marker>`. This maps directly onto our per-field ground truth: field name, printed value and box.
- **Ground truth and predictions.** The spec has **no dedicated ground-truth or prediction construct**, and no confidence attribute in the visible text. Both sides of an evaluation are therefore ordinary DocLang documents. We emit one `.dclg` per page for the ground truth and one per page and engine for Docling's output.
- **Toolkit** (`pip install "doclang[schematron-saxon]"`): `doclang validate` (XSD and Schematron), `doclang pack` (builds a `.dclx` archive with `document.xml`, page images and assets) and `doclang migrate`. `.dclg` is the markup file and `.dclx` the packaged archive. Toolkit README: https://github.com/doclang-project/doclang/blob/main/doclang/README.md
- **Docling integration** *(local)*. docling-core ships `DoclingDocument.export_to_doclang()`, `save_as_doclang()`, `save_as_doclang_archive()` and `load_from_doclang_archive()`, plus `DocLangDocDeserializer`. DoclingDocument has first-class `FieldRegionItem` and `FieldItem` objects, created with `add_field_region`, `add_field_item`, `add_field_key` and `add_field_value`, and these serialise to DocLang `<field_region>`. Docling v2.145.0 changed DocLang locations to scale to the page size.
- **Caveat found while building** *(local)*. docling-core's serialiser writes `<doclang version="0.9">` without an `xmlns`. Validation passes with `allow_empty_namespace=True` (CLI: `--allow-empty-namespace`). With that flag, all 260 ground-truth files pass both XSD and Schematron. This is worth raising with the Docling team: should the serialiser emit the namespace?

## 2. Docling OCR engines and presets (latest release)

- Releases: https://github.com/docling-project/docling/releases. **v2.149.0 (Nov 8) added the MiniCPM-OCR preset.** The latest release, v2.150.1 (Nov 14), adds no OCR changes; its notes include a `TESSDATA_PREFIX` documentation note.
- OCR concepts page: https://docling-project.github.io/docling/concepts/OCR/. Model catalogue: https://docling-project.github.io/docling/usage/model_catalog. Pipeline options: https://docling-project.github.io/docling/reference/pipeline_options
- **OCR engines (`OcrEngine` enum, local)**: `auto`, `easyocr`, `tesseract_cli`, `tesseract` (tesserocr), `ocrmac` and `rapidocr`. Option classes also exist for `NemotronOcrOptions` and `KserveV2OcrOptions` (remote).
  - **RapidOCR** (`RapidOcrOptions`) is the default engine. It runs on onnxruntime by default and uses one language per conversion. `model_size` can be tiny, small or medium for PP-OCRv6 languages. `detect_orientation` was added in v2.145.0. The ONNX backend resolves script codes `latin`, `devanagari`, `cyrillic` and `arabic`; **there is no Bengali model** *(local)*.
  - **EasyOCR** (`EasyOcrOptions`) uses PyTorch and accepts several languages at once, with defaults en, es, fr and de. It needs `pip install easyocr`. It supports `hi`, `mr` and `bn`.
  - **ocrmac** (`OcrMacOptions`) wraps Apple Vision and is macOS only. Apple Vision on this machine supports 30 languages and **no Indic scripts** *(local)*.
  - **Tesseract** (`TesseractCliOcrOptions` / `TesseractOcrOptions`) needs the system binary or tesserocr plus traineddata. It is **not installed on this Mac**, so it was skipped.
  - **Nemotron-OCR** targets NVIDIA GPUs and accepts english or multilingual. **KServe v2** sends requests to a remote server, which requires `enable_remote_services=True`.
- **Shared OCR options** *(local)*: `lang`, `force_full_page_ocr` (also exposed as `mode=OcrMode.FULL_PAGE`), `replace_broken_text_layer` (v2.144.0) and **`scale`, default 3.0**. The page is rendered at 72 DPI × `scale` before OCR. For image inputs, Docling treats one image pixel as one point, so the default upsamples a 150 DPI scan threefold. We run with `scale=1.0`; see REVIEW_NOTES.md.
- **VLM "presets"** (`VlmConvertOptions.register_preset`, local): granite_docling, smoldocling, gemma, dolphin, glm_ocr, **minicpm_ocr**, lightonocr (×3), falcon_ocr, chandra_ocr2, surya_ocr2_5, unlimited_ocr (×3) and dots_ocr/dots_mocr. These replace the whole layout+OCR pipeline rather than plugging in as an OCR engine.
  - The `minicpm_ocr` preset uses `openbmb/MiniCPM-OCR-1.0`, a 1.3B-parameter model pinned to revision `c5833cdd…`. Its prompt is "Convert this page to markdown." and its output is markdown. It runs on Transformers (bf16, transformers ≥ 5.21) or through OpenAI-compatible, Ollama or LM Studio APIs, with scale 2.0.

## 3. docling-eval

- Repo: https://github.com/docling-project/docling-eval. CLI: `docling-eval create | create-gt | create-eval | evaluate | visualize`.
- Datasets are Hugging Face-style parquet shards of `DatasetRecord`s. Each record holds the ground-truth `DoclingDocument`, page images and, for OCR, **segmented pages** (`GROUNDTRUTH_SEGMENTED_PAGES` / `PREDICTED_SEGMENTED_PAGES`).
- The evaluators live in `docling_eval/evaluators/`: layout, table, OCR, markdown text, reading order, key-value, document structure, bbox-text, timings and pixel layout. Source: https://github.com/docling-project/docling-eval/tree/main/docling_eval/evaluators
  - **OCR** (`ocr_evaluator.py`). Compares GT and predicted word cells on the first page. It matches spatially, then counts a true positive only on an exact text match. It reports precision, recall, F1, word accuracy and character accuracy, each in case-sensitive and case-insensitive variants. It writes per-document metadata and green/blue/red overlay visualisations. **It assumes the GT covers every word on the page.** Our field-level GT does not, so unannotated printed text would count as false positives. That is why we score at field level ourselves; see REVIEW_NOTES.md.
  - **Key-value** (`keyvalue_evaluator.py`). Reads `DoclingDocument.key_value_items[0]`, a graph of cells and links, **not** `field_items`. Entities are matched by text (strict, or edit distance ≤ 3 / ratio ≥ 0.8) and, when layout-aware, by Hungarian assignment on IoU. It reports precision, recall and F1 for entities and relations.
  - **Layout** uses mAP-style detection metrics on DocLayNet-like labels. Table structure uses TEDS.
- The listed benchmarks are DP-Bench, OmniDocBench, DocLayNet v1.2, FinTabNet, PubTabNet and Pub1M. "OmniOCR" is listed as upcoming.

## 4. Implications for this benchmark

1. We ship the ground truth three ways: GritWorks' original JSON, `DoclingDocument` JSON (field_region/field_items with TOPLEFT pixel boxes) and DocLang `.dclg`. All `.dclg` files pass the reference toolkit with Schematron.
2. Docling predictions are also saved as DocLang, so both sides of the comparison use the same format.
3. Packaging this as a docling-eval dataset needs one of two changes. (a) Add full-page word transcripts to the ground truth so `OCREvaluator` is fair. (b) Express the fields as `key_value_items` so `KeyValueEvaluator` can read them, or add a field-item-aware evaluator. This is an open question for the Docling team.
