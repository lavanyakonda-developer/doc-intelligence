.PHONY: setup data explore golden degrade test lint

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
