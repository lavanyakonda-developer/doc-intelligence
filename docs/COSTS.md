# Costs log

Budget target: **< $5 total API spend**. Prices: [OpenAI pricing](https://developers.openai.com/api/docs/pricing), checked 2026-11-13.

| Date | Experiment | Model | Docs / pages | Input tok | Output tok | $ | Notes |
|---|---|---|---|---|---|---|---|
| 2026-11-09 | Phase 0–2 | n/a | n/a | 0 | 0 | 0.00 | no API calls |
| 2026-11-13 | Vision capability + reasoning-effort probes | gpt-6-luna, gpt-5.6-luna | 6 calls, 1 image crop | ~800 | ~770 | <0.001 | confirmed gpt-6-luna accepts images; effort=none → 0 reasoning tokens |
| 2026-11-13 | Phase 3 vision parser: 6 docs × clean/light/heavy | gpt-6-luna | 18 / 171 pages | 450,414 | 118,372 | 0.104 | ~2.6k in + ~690 out per page; estimate was $0.30 (assumed 900 out tok + reasoning) |
| 2026-11-13 | Phase 4 dev: prompts v1/v2/v3 × 3 replicates | gpt-6-luna | 8 docs × 9 runs | ~900k | ~60k | 0.064 | replicates hit prompt cache (~90% input discount): repeat costs understate real cost |
| 2026-11-13 | Phase 4 dev: model comparison | gpt-6.1-terra | 8 docs | 100,568 | 6,151 | 0.119 | |
| 2026-11-13 | Phase 4 test: final v3 | gpt-6-luna (×3), gpt-6.1-terra (×1) | 22 docs | 405k per run | ~19.5k per run | 0.075 + 0.462 | |
| 2026-11-13 | Phase 4 end-to-end parser runs | gpt-6-luna | 6 docs × 4 parser/conditions | ~110k | ~6k | 0.029 | |
| 2026-11-13 | Phase 5 retry-with-feedback | gpt-6-luna | 4 docs (pypdf 3, docling 1) | ~55k | ~3k | 0.010 | self-consistency reused Phase 4 replicates: $0 |
| 2026-11-13 | Phase 6 eval harness (DuckDB, bootstrap, taxonomy) | n/a | cached runs | 0 | 0 | 0.00 | no API calls |

**Running total: ~$0.87** (Phase 3: $0.105, Phase 4: $0.750, Phase 5: $0.010)

Per-document extraction cost, first (uncached) run, ~13.5k input tokens: **gpt-6-luna ≈ $0.002**, **gpt-6.1-terra ≈ $0.021**.

Per-page vision cost, measured: **$0.00061/page** ($0.61 per 1,000 pages).
