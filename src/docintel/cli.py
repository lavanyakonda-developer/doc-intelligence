"""Command line: `docintel extract contract.pdf`, `docintel query expiring_soon days=60`.

argparse, not click/typer: three subcommands don't justify another dependency.
"""

import argparse
import json
import sys
from pathlib import Path

from docintel.config import get_settings


def _store():
    from docintel.storage.store import DuckDBStore

    return DuckDBStore(get_settings().duckdb_path)


def cmd_extract(args) -> int:
    from docintel.pipeline import process_pdf

    store = None if args.no_store else _store()
    worst = 0
    for pdf in args.pdfs:
        r = process_pdf(Path(pdf))
        if r.status != "ok":
            print(f"{pdf}: ERROR {r.error}", file=sys.stderr)
            worst = 1
            continue
        if store:
            store.save(r)
        if args.json:
            print(r.model_dump_json(indent=2, exclude={"text"}))
            continue
        print(f"\n{r.filename}  [{r.parser}, {r.pages} pages, ${r.cost_usd:.4f}, {r.seconds}s]")
        for name, f in r.fields.items():
            v = getattr(r.record, name).value
            if f.status == "absent":
                continue
            mark = {"verified": "✓", "unverified": "?", "failed": "✗"}[f.status]
            shown = json.dumps(v if not hasattr(v, "model_dump") else v.model_dump(
                exclude_none=True), default=str)  # fmt: skip
            print(f"  {mark} {name:36s} {shown[:90]}")
        if r.needs_review:
            print(f"  needs review: {', '.join(r.needs_review)}")
    return worst


def cmd_query(args) -> int:
    from docintel.storage.store import QUERIES

    if args.name not in QUERIES:
        print(f"queries: {', '.join(sorted(QUERIES))}", file=sys.stderr)
        return 2
    params = dict(p.split("=", 1) for p in args.params)
    rows = _store().query(args.name, **params)
    for row in rows:
        print(json.dumps(row, default=str))
    print(f"({len(rows)} rows)", file=sys.stderr)
    return 0


def cmd_seed(args) -> int:
    """Load the 30 golden-set contracts (reuses the experiments' caches: $0)."""
    from docintel.corpus import find_pdf, golden_set
    from docintel.pipeline import process_pdf

    store = _store()
    for g in golden_set():
        r = process_pdf(find_pdf(g["file"]), doc_id=g["file"], condition="clean")
        if r.status == "ok":
            store.save(r)
        else:
            print(f"{g['file']}: {r.error}", file=sys.stderr)
    print(f"store: {get_settings().duckdb_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="docintel", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="PDF(s) -> validated record (stored unless --no-store)")
    e.add_argument("pdfs", nargs="+")
    e.add_argument("--json", action="store_true", help="print the full ContractResult JSON")
    e.add_argument("--no-store", action="store_true")
    e.set_defaults(fn=cmd_extract)
    q = sub.add_parser("query", help="run a named analytics query, e.g. expiring_soon days=60")
    q.add_argument("name")
    q.add_argument("params", nargs="*", help="key=value")
    q.set_defaults(fn=cmd_query)
    s = sub.add_parser("seed", help="load the golden set into the store ($0, cached)")
    s.set_defaults(fn=cmd_seed)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
