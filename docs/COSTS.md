# Costs log

Budget target: **< $5 total API spend**. Prices: [OpenAI pricing](https://developers.openai.com/api/docs/pricing), checked 2026-11-13.

| Date | Experiment | Model | Docs / pages | Input tok | Output tok | $ | Notes |
|---|---|---|---|---|---|---|---|
| 2026-11-09 | Phase 0–2 | n/a | n/a | 0 | 0 | 0.00 | no API calls |
| 2026-11-13 | Vision capability + reasoning-effort probes | gpt-6-luna, gpt-5.6-luna | 6 calls, 1 image crop | ~800 | ~770 | <0.001 | confirmed gpt-6-luna accepts images; effort=none → 0 reasoning tokens |
| 2026-11-13 | Phase 3 vision parser: 6 docs × clean/light/heavy | gpt-6-luna | 18 / 171 pages | 450,414 | 118,372 | 0.104 | ~2.6k in + ~690 out per page; estimate was $0.30 (assumed 900 out tok + reasoning) |

**Running total: ~$0.11**

Per-page vision cost, measured: **$0.00061/page** ($0.61 per 1,000 pages).
