.PHONY: setup data explore golden degrade gt test lint parsers extract validate eval seed ci serve demo-data web phoenix traces

setup:            ## install deps + git hooks
	uv sync
	uv run pre-commit install

data:             ## download CUAD into data/raw (gitignored)
	uv run python scripts/download_cuad.py

explore: data     ## profile CUAD -> data/explore/*.csv
	uv run python scripts/explore_cuad.py

golden: explore   ## select 30-doc golden set -> evalsets/golden_set.csv
	uv run python scripts/select_docs.py

degrade:          ## synthetic scans of the degraded subset -> data/degraded/
	uv run python scripts/make_degraded_pdfs.py

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

gt:               ## CUAD labels -> evalsets/ground_truth.jsonl
	uv run python scripts/build_ground_truth.py

parsers:          ## parser comparison (cached; vision costs ~$0.10 on first run)
	uv run --group research python scripts/run_parsers.py
	uv run python scripts/parser_report.py

extract:          ## extraction on dev with the current prompt (cached; ~$0.01 first run)
	uv run python scripts/run_extraction.py --model gpt-6-luna --prompt extract_v3 --split dev

validate:         ## Phase 5: retry + self-consistency + abstention table -> docs/RESULTS.md (cached)
	uv run python scripts/run_validation.py

eval:             ## Phase 6: DuckDB + all breakdowns -> RESULTS.md, error CSV, regression gate ($0)
	uv run python scripts/error_review.py
	uv run python scripts/eval_report.py > /dev/null
	uv run python scripts/eval_check.py

seed:             ## load the golden set into the results store (data/docintel.duckdb, $0)
	uv run docintel seed

ci:               ## what GitHub Actions runs: lint, tests, eval gate on the committed snapshot
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest
	uv run python scripts/eval_check.py --snapshot

serve:            ## run the API on http://127.0.0.1:8000 (docs at /docs)
	uv run uvicorn docintel.api.app:app --reload

demo-data:        ## export precomputed results + TS types for the static demo ($0, needs data/)
	uv run python scripts/export_demo.py
	uv run python scripts/export_schema.py
	cd web && npm run types

web:              ## run the demo UI locally (http://localhost:5173/doc-intelligence/)
	cd web && npm install && npm run dev

phoenix:          ## local Phoenix UI + trace collector on http://localhost:6006 (no account)
	uvx --from "arize-phoenix==21.0.0" phoenix serve

traces:           ## traced golden-set run (~$0.05) + eval outcomes as span annotations
	uv run --group observability python scripts/traced_run.py
	uv run --group observability python scripts/annotate_traces.py
