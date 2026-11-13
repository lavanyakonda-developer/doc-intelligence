# docintel — Contract Intelligence Pipeline

Messy commercial contracts in → validated JSON records out → stored, queryable, evaluated, served via API.

Built on [CUAD](https://github.com/The-Atticus-Project/cuad) (Atticus Project, CC BY 4.0).

> 🚧 Work in progress. Current evaluation results (with confidence intervals) are in [`docs/RESULTS.md`](docs/RESULTS.md).

## Quickstart
```bash
make setup       # uv sync + pre-commit hooks
cp .env.example .env   # add OPENAI_API_KEY
make data        # download CUAD
make test
```

## Usage
```bash
uv run docintel extract contract.pdf          # route parser -> extract -> validate -> store
uv run docintel extract contract.pdf --json   # full result: values, evidence offsets, status, cost
uv run docintel seed                          # load the 30-contract golden set ($0, cached)
uv run docintel query expiring_soon days=90
```

Each field comes back with a validation status (`verified` / `unverified` / `failed`) and the
character offsets of its evidence quote in the parsed text.

## API
```bash
make serve    # http://127.0.0.1:8000, interactive docs at /docs
```
Extraction takes ~5 s for a digital contract and ~40 s for a scan, so the API is job-based:

```bash
curl -F "file=@contract.pdf" localhost:8000/v1/jobs        # 202 {job_id, status_url}
curl localhost:8000/v1/jobs/<job_id>                       # queued | running | done (+ result) | error
curl "localhost:8000/v1/contracts/<doc_id>?include_text=true"   # result + parsed text for highlighting
curl "localhost:8000/v1/queries/expiring_soon?days=90"
```
Uploading the same file again returns the stored result immediately (documents are keyed by a
content hash), and a duplicate upload while the first is still processing joins that job
instead of paying twice. Uploads are checked (≤10 MB, real PDF, ≤60 pages) and deleted after
processing.

## Analytics on extracted contracts
Validated records are stored in DuckDB as typed columns (dates, durations in days, booleans),
so portfolio questions become SQL ([`storage/store.py`](src/docintel/storage/store.py)):

| query | question it answers |
|---|---|
| `expiring_soon as_of=… days=…` | Which contracts expire in the next N days? |
| `renewal_notice_deadlines` | Auto-renewing contracts: last day to send a non-renewal notice |
| `uncapped_liability` | Where is our liability uncapped, with the clause quoted |
| `governing_law_mix` | Which jurisdictions govern the portfolio |
| `needs_review` | Fields that failed or couldn't be verified, with reasons |
| `risk_flags` | Contracts ranked by exclusivity / non-compete / uncapped / change-of-control |

## Development
```bash
make ci      # same checks as GitHub Actions: lint, tests, eval regression gate (no API calls)
make eval    # rebuild the eval DB from cached runs; all tables -> docs/RESULTS.md
```
CI re-scores committed model outputs (`evalsets/snapshot/`) with the current code, so a change
to normalizers, match rules or ground truth that moves F1 fails the build. It needs no API key.
