# Results

<!-- parsers:start -->
## Parser comparison (Phase 3)

Same 6 contracts / 57 pages per row. `evidence_*` = share of CUAD's lawyer-highlighted spans recoverable from the parsed text (exact after whitespace normalization; fuzzy = best alignment ≥ 90). WER is against CUAD's own .txt, itself a machine extraction, so it favours text-layer parsers. Seconds measured on an M2 Pro, CPU only.

| parser | condition | docs | pages | evidence_exact_pct | evidence_fuzzy_pct | wer_pct | sec_per_page | usd_per_1k_pages | page_errors |
|---|---|---|---|---|---|---|---|---|---|
| docling | clean | 6 | 57 | 94.4 | 97.2 | 2.4 | 0.48 | 0.0 | 0 |
| docling | light | 6 | 57 | 71.8 | 93.0 | 11.0 | 3.54 | 0.0 | 0 |
| docling | heavy | 6 | 57 | 26.8 | 84.5 | 23.7 | 2.92 | 0.0 | 0 |
| pypdf | clean | 6 | 57 | 93.0 | 100.0 | 0.7 | 0.0 | 0.0 | 0 |
| pypdf | light | 6 | 57 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0 |
| pypdf | heavy | 6 | 57 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0 |
| vision-gpt-6-luna | clean | 6 | 57 | 91.5 | 100.0 | 0.9 | 2.33 | 0.609 | 0 |
| vision-gpt-6-luna | light | 6 | 57 | 90.1 | 100.0 | 0.9 | 1.56 | 0.61 | 0 |
| vision-gpt-6-luna | heavy | 6 | 57 | 81.7 | 100.0 | 1.5 | 1.72 | 0.609 | 0 |
<!-- parsers:end -->
