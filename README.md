# docintel — Contract Intelligence Pipeline

Messy commercial contracts in → validated JSON records out → stored, queryable, evaluated, served via API.

Built on [CUAD](https://github.com/The-Atticus-Project/cuad) (Atticus Project, CC BY 4.0).

> 🚧 Work in progress. Results, architecture and trade-offs will land here. See `docs/DECISIONS.md`.

## Quickstart
```bash
make setup       # uv sync + pre-commit hooks
cp .env.example .env   # add OPENAI_API_KEY
make data        # download CUAD
make test
```
