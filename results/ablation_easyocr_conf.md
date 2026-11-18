# Ablation: EasyOCR confidence_threshold 0.5 (Docling default, main run) vs 0.0

Pages: banking__w2__p1, ocr__credit_memo__p1, ocr__purchase_order__p1, us_kyc__proof_of_address__p1; scale 1.0; field EM % / CER %.

| Condition | threshold 0.5 | threshold 0.0 |
|---|---|---|
| clean | 73.8 / 6.0 | 76.2 / 2.5 |
| blur | 3.6 / 81.3 | 8.3 / 27.9 |
| fax | 27.4 / 40.3 | 36.9 / 11.3 |
