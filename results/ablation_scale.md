# Ablation: OCR scale 1.0 (main run) vs 3.0 (Docling default)

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
