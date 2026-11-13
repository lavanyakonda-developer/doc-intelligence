# Roadmap

Order is fixed: pipeline and evals first, UI only after they're done.

| # | Phase | Status |
|---|---|---|
| 0 | Scope & setup: uv, ruff, pre-commit + gitleaks, pytest, CUAD download + profiling | ✅ |
| 1 | Golden set: 30 docs, 14 fields, dev/test split, synthetic scans | ✅ |
| 2 | Schema, normalizers, match rules, ground truth + label audit | ✅ |
| 3 | Parsing: pypdf vs Docling vs vision LLM on clean/light/heavy | ✅ |
| 4 | Extraction: structured outputs, model size vs cost, prompt versioning | ✅ |
| 5 | Validation: validators, cross-field checks, retry with feedback, evidence check, abstention | ✅ |
| 6 | Evals: per-field P/R/F1 by type, per parser/model, error taxonomy, threshold tuning on dev, `make eval` → DuckDB | ✅ |
| 7 | Pipeline entry point, results store + analytics queries, CI (GitHub Actions) | ✅ |
| 8 | API: FastAPI upload → job → result, tests | ⏭ next |
| 9 | Deploy: Docker + Cloud Run, secrets, cost controls | |
| **9.5** | **Demo UI + public-demo hardening** (below) | |
| 10 | Observability: Phoenix tracing linked to eval results | |
| 11 | Portfolio & interview pack | |

## Phase 9.5: Demo UI (added 2026-11-13)
- **React UI** (user writes most of it): upload PDF → fields table → click a field to highlight its evidence in the contract text; per document show parser used, latency and cost.
  - *Requirement this puts on earlier phases:* highlighting needs **character offsets** of each evidence quote in the parsed text the user sees, not just the quote string. Resolve offsets with the same normalized/fuzzy alignment used by the evidence check (Phase 5) and return them from the API (Phase 8).
- **`make demo`** runs end to end on **one sample contract committed to the repo** (no CUAD download). CUAD is CC BY 4.0, so committing one contract is fine with attribution in the README.
- **Public-demo safeguards:** max file size and page count, per-IP rate limiting, budget alert + Cloud Run max instances, OpenAI key only server-side (never in the bundle or responses), CORS restricted to the demo origin.

## Phase 11 additions
- README top: **90-second demo GIF**, results table, architecture diagram.
