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

<!-- extraction:start -->
## Extraction (Phase 4)

Prompt `extract_v3`, reasoning effort `low`, pypdf text, Structured Outputs. Micro P/R/F1 over all 14 fields
(parties scored per party; see note).

**Model comparison, 22-doc test set**

| model | runs | P | R | F1 | $ / doc (uncached) | mean latency |
|---|---|---|---|---|---|---|
| gpt-6-luna | 3 | 78.5 / 80.3 / 79.6 | 89.9 / 90.3 / 88.4 | **83.8 / 85.0 / 83.8** | $0.0021 | 9.7 s |
| gpt-6.1-terra | 1 | 77.9 | 90.3 | **83.7** | $0.021 | 11.8 s |

**Prompt iterations, 8-doc dev set, gpt-6-luna, 3 runs each**

| prompt | F1 per run | mean | false positives |
|---|---|---|---|
| v1 | 87.1 / 85.1 / 87.1 | 86.4 | 20–23 |
| v2 | 89.4 / 89.3 / 89.7 | 89.5 | 13–14 |
| v3 (chosen) | 90.2 / 87.9 / 88.8 | 89.0 | 13–14 |

**End to end: parser → extraction** (6 scanned test docs, gpt-6-luna, v3, single runs; ±2–3 pts is noise at n=6)

| input | F1 |
|---|---|
| pypdf, clean PDF | 85.0 |
| Docling, light / heavy scan | 80.3 / 76.9 |
| vision gpt-6-luna, light / heavy scan | 87.4 / 84.5 |

Note: one test contract (GWG Holdings) lists 26 trusts individually that CUAD summarizes as one party, which adds 26
party-level false positives and lowers micro precision by ~8 points. Phase 6 adds per-document scoring for list fields.
<!-- extraction:end -->
