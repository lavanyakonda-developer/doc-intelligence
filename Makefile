.PHONY: setup data test lint

setup:            ## install deps + git hooks
	uv sync
	uv run pre-commit install

data:             ## download CUAD into data/raw (gitignored)
	uv run python scripts/download_cuad.py

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .
