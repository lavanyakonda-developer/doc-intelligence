"""Load every cached run into DuckDB so each breakdown is a SQL query, not a new script.

Tables (rebuilt from scratch each time; the source of truth is data/runs/, so this is $0):
  runs      one row per run: config (model, prompt, parser, condition, replicate) + cost
  docs      one row per golden-set doc: split, length bucket, pages, contract type
  outcomes  one row per match outcome. Scalar fields give 1 row per (run, doc, field);
            list fields (parties) give 1 row per matched/unmatched ITEM, so `item` > 0.

  uv run python -c "from docintel.eval.db import build; build()"
"""

import json
from pathlib import Path

import duckdb

from docintel.config import PROJECT_ROOT
from docintel.corpus import CONDITIONS, golden_set, ground_truth
from docintel.eval.score import score
from docintel.extraction.extractor import RUNS
from docintel.extraction.llm_schema import LLMExtraction
from docintel.extraction.to_record import to_record
from docintel.parsing.base import CACHE_DIR
from docintel.schema.types import ContractRecord
from docintel.validation.validate import validate

DB_PATH = PROJECT_ROOT / "data" / "eval.duckdb"

SCHEMA = """
CREATE TABLE runs (
    run_id VARCHAR PRIMARY KEY, model VARCHAR, effort VARCHAR, prompt VARCHAR,
    parser VARCHAR, condition VARCHAR, replicate INTEGER,
    n_docs INTEGER, n_ok INTEGER, cost_usd DOUBLE, seconds DOUBLE
);
CREATE TABLE docs (
    doc_id VARCHAR PRIMARY KEY, split VARCHAR, bucket VARCHAR, pages INTEGER,
    tokens INTEGER, contract_type VARCHAR, degraded BOOLEAN
);
CREATE TABLE outcomes (
    run_id VARCHAR, doc_id VARCHAR, field VARCHAR, type VARCHAR, item INTEGER,
    outcome VARCHAR,          -- tp | fp | fn | tn | wrong
    pred VARCHAR, gold VARCHAR,           -- field-level values as JSON
    pred_evidence VARCHAR, gold_evidence VARCHAR,
    derived BOOLEAN,          -- GT value computed by us (e.g. expiration from a term)
    status VARCHAR,           -- validator: absent | verified | unverified | failed | NULL
    reasons VARCHAR,          -- validator reasons, '; '-joined
    conversion_error VARCHAR  -- to_record could not normalize the model's value
);
"""


def _load_run(run: Path, rederive: bool = False) -> tuple[dict, dict[str, dict]]:
    """rederive=True rebuilds each record from the model's raw output with the CURRENT
    to_record/normalizers, so a code change that alters records shows up in the scores."""
    cfg = json.loads((run / "config.json").read_text())
    results = {}
    for f in run.glob("*.json"):  # retries/ is a subfolder, not matched
        if f.name != "config.json":
            r = json.loads(f.read_text())
            if rederive and r["status"] == "ok":
                rec, errors = to_record(r["doc_id"], LLMExtraction.model_validate(r["raw"]))
                r["record"], r["conversion_errors"] = rec.model_dump(mode="json"), errors
            results[r["doc_id"]] = r
    return cfg, results


def _parsed_text(cfg: dict, doc_id: str) -> str | None:
    p = CACHE_DIR / cfg["parser"] / cfg["condition"] / f"{doc_id}.json"
    return json.loads(p.read_text())["text"] if p.exists() else None


def run_rows(cfg: dict, results: dict[str, dict], gt: dict[str, dict]) -> list[tuple]:
    rows: list[tuple] = []
    gt_run = {d: gt[d] for d in results if d in gt}  # degraded runs cover only 6 docs
    per_doc: list[dict] = []
    score(results, gt_run, per_doc=per_doc)
    checks_by_doc: dict[str, dict] = {}
    for d, r in results.items():
        text = _parsed_text(cfg, d)
        if r["status"] == "ok" and text is not None:
            rec = ContractRecord.model_validate(r["record"])
            checks_by_doc[d] = validate(rec, text, r["conversion_errors"])
    for p in per_doc:
        d, name = p["doc_id"], p["field"]
        r = results[d]
        ok = r["status"] == "ok"
        pred_ev = r["record"][name]["evidence"] if ok else None
        gold_ev = gt[d]["record"][name]["evidence"]
        chk = checks_by_doc.get(d, {}).get(name)
        conv = next(
            (e.split(":", 1)[1].strip() for e in r.get("conversion_errors", [])
             if e.split(":", 1)[0] == name),
            None,
        )  # fmt: skip
        for i, outcome in enumerate(p["outcomes"]):
            rows.append(
                (
                    cfg["run_id"], d, name, p["type"], i, outcome, p["pred"], p["gt"],
                    pred_ev, gold_ev, p["derived"],
                    chk.status if chk else None,
                    "; ".join(chk.reasons) if chk else None,
                    conv,
                )
            )  # fmt: skip
    return rows


def build(
    db_path: Path | None = DB_PATH, runs_dir: Path = RUNS, *, rederive: bool = False
) -> duckdb.DuckDBPyConnection:
    """db_path=None -> in-memory (CI)."""
    if db_path is not None:
        db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path) if db_path is not None else ":memory:")
    con.execute(SCHEMA)
    con.executemany(
        "INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                g["file"], g["split"], g["bucket"], int(g["pages"]), int(g["tokens"]),
                g["contract_type"], g["degraded"] == "True",
            )
            for g in golden_set()
        ],
    )  # fmt: skip
    gt = ground_truth()
    for run in sorted(p for p in runs_dir.iterdir() if (p / "config.json").exists()):
        cfg, results = _load_run(run, rederive)
        if cfg["condition"] not in CONDITIONS:  # product traffic ('upload'): no ground truth
            continue
        con.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cfg["run_id"], cfg["model"], cfg["effort"], cfg["prompt"], cfg["parser"],
                cfg["condition"], cfg["replicate"], len(results),
                sum(r["status"] == "ok" for r in results.values()),
                sum(r.get("cost_usd", 0) for r in results.values()),
                sum(r.get("seconds", 0) for r in results.values()),
            ),
        )  # fmt: skip
        rows = run_rows(cfg, results, gt)
        if rows:
            con.executemany(
                "INSERT INTO outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
            )
    return con


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    if not db_path.exists():
        return build(db_path)
    return duckdb.connect(str(db_path))
