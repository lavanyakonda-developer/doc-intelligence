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
| 8 | API: FastAPI upload → job → result, tests | ✅ |
| 9 | Static demo (GitHub Pages, precomputed results, no backend) + README + 90 s video | 🟡 built; your UI components, Pages setup, video pending |
| 10 | Observability: Arize Phoenix locally, OpenInference + custom spans, traces linked to eval results | ✅ (screenshots pending) |
| 11 | Portfolio & interview pack | |

## Phase 9: static demo, no live API (decided 2026-11-13)
- No card, no cloud deployment, nothing paid. Hosting would be free, but every upload is a paid LLM call and an open endpoint is a cost and abuse risk, so the public demo serves **precomputed results**.
- **React UI on GitHub Pages:** golden-set results (fields, evidence offsets, contract text), eval tables and the parser comparison, exported as static JSON. Click a field to highlight its evidence in the contract.
- **README:** problem, architecture diagram, results tables, parser cost vs quality, what worked and what didn't, run locally (`make setup` → `make serve`), demo link.
- **90-second video** of a real contract going through the local API.

## Phase 10: observability (decided 2026-11-13)
- Arize Phoenix running locally, no account. OpenInference instrumentation for OpenAI calls + custom spans: parse, extract, validate, retry, store.
- Span attributes: doc_id, prompt_version, model, parser, tokens, cost_usd, validation errors.
- Traces linked to eval results ("all traces where field X was wrong"); 2–3 README screenshots; DECISIONS note on moving to a hosted backend.

## Phase 11 additions
- README top: **90-second demo GIF**, results table, architecture diagram.
