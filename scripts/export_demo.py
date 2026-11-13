"""Export precomputed results for the static demo (web/public/data/). $0: everything is cached.

  index.json            contract list + per-contract status summary
  contracts/<key>.json  {result: ContractResult (with text), truth: {field: {gold, outcome}}}
  evals.json            headline + paired comparisons + per-field + breakdowns + parsers

The same files seed the local API (`make serve`) when its store is empty, so "run locally"
works without downloading CUAD. Contract text is CUAD (CC BY 4.0), attributed in the UI.

  uv run python scripts/export_demo.py
"""

import hashlib
import json
import shutil
from pathlib import Path

import duckdb
from parser_report import QUERY as PARSER_QUERY  # noqa: E402  (scripts/ is on sys.path)

from docintel.corpus import find_pdf, golden_set, ground_truth
from docintel.demo_models import DemoContract, DemoIndex
from docintel.eval.db import build
from docintel.eval.match import match
from docintel.eval.metrics import (
    bootstrap_f1,
    counts_by,
    doc_counts,
    list_field_macro,
    paired_bootstrap,
    prf,
    total,
)
from docintel.pipeline import process_pdf
from docintel.schema.fields import FIELDS
from docintel.schema.types import ContractRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "data"
PRODUCTION = "6-luna-low-extract_v3-pypdf-clean-r0"


def key_for(doc_id: str) -> str:
    return hashlib.sha1(doc_id.encode()).hexdigest()[:12]  # filenames safe for URLs


def r1(x: float | None) -> float | None:
    return None if x is None else round(100 * x, 1)


def truth_for(result, gt_item: dict) -> dict:
    truth = ContractRecord.model_validate(gt_item["record"])
    out = {}
    for f in FIELDS:
        if f.name in gt_item["excluded_fields"]:
            out[f.name] = {"gold": None, "outcome": "excluded"}
            continue
        p, g = getattr(result.record, f.name).value, getattr(truth, f.name).value
        outcomes = match(f.type, p, g)
        out[f.name] = {
            "gold": getattr(truth, f.name).model_dump(mode="json")["value"],
            "outcome": "correct" if set(outcomes) <= {"tp", "tn"} else "partial"
            if "tp" in outcomes else "wrong",
        }  # fmt: skip
    return out


def export_contracts(gt: dict) -> list[dict]:
    (OUT / "contracts").mkdir(parents=True)
    index = []
    for g in golden_set():
        doc = g["file"]
        r = process_pdf(find_pdf(doc), doc_id=doc, condition="clean")  # cached: $0
        assert r.status == "ok", (doc, r.error)
        truth = truth_for(r, gt[doc])
        key = key_for(doc)
        demo = DemoContract.model_validate({"result": r, "truth": truth})  # schema-checked
        (OUT / "contracts" / f"{key}.json").write_text(demo.model_dump_json())
        statuses = [f.status for f in r.fields.values()]
        outcomes = [t["outcome"] for t in truth.values() if t["outcome"] != "excluded"]
        index.append(
            {
                "key": key,
                "doc_id": doc,
                "document_name": r.record.document_name.value,
                "parties": r.record.parties.value or [],
                "contract_type": g["contract_type"],
                "pages": r.pages,
                "split": g["split"],
                "parser": r.parser,
                "cost_usd": r.cost_usd,
                "verified": statuses.count("verified"),
                "unverified": statuses.count("unverified"),
                "failed": statuses.count("failed"),
                "correct": outcomes.count("correct"),
                "scored": len(outcomes),
            }
        )
    return sorted(index, key=lambda x: (x["document_name"] or "").lower())


def export_evals() -> dict:
    con = build()  # rebuild from cached runs
    runs = dict(con.execute("SELECT run_id, model FROM runs").fetchall())
    rid = next(r for r in runs if r.startswith(PRODUCTION))

    headline = []
    for r, model, prompt, rep, cost in con.execute(
        """SELECT run_id, model, prompt, replicate, cost_usd / n_docs FROM runs
           WHERE parser = 'pypdf' AND n_docs = 30 ORDER BY run_id"""
    ).fetchall():
        c = doc_counts(con, r, split="test")
        p, rec, _ = prf(*total(c))
        e = bootstrap_f1(c)
        headline.append(
            {"model": model, "prompt": prompt, "replicate": rep, "precision": r1(p),
             "recall": r1(rec), "f1": r1(e.value), "ci": [r1(e.lo), r1(e.hi)],
             "usd_per_doc": round(cost, 5), "production": r == rid}
        )  # fmt: skip

    base = doc_counts(con, rid, split="test")
    paired = []
    for label, prefix in [
        ("Replicate r1 vs r0 (run-to-run noise)", "6-luna-low-extract_v3-pypdf-clean-r1"),
        ("gpt-6.1-terra (10× cost) vs gpt-6-luna", "6.1-terra-low-extract_v3-pypdf-clean-r0"),
    ]:
        other = next(r for r in runs if r.startswith(prefix))
        pb = paired_bootstrap(base, doc_counts(con, other, split="test"))
        paired.append({"label": label, "delta": r1(pb.diff), "ci": [r1(pb.lo), r1(pb.hi)]})

    per_field = []
    groups = counts_by(con, rid, "field", split="test")
    for f in FIELDS:
        tp, fp, fn = total(groups.get(f.name, {}))
        p, rec, f1 = prf(tp, fp, fn)
        macro = (
            list_field_macro(con, rid, f.name, split="test") if f.type == "entity_list" else None
        )
        per_field.append(
            {"field": f.name, "type": f.type, "precision": r1(p), "recall": r1(rec),
             "f1": r1(f1), "doc_macro_f1": r1(macro), "tp": tp, "fp": fp, "fn": fn}
        )  # fmt: skip

    def breakdown(column: str) -> list[dict]:
        rows = []
        for g, c in sorted(counts_by(con, rid, column, split="test").items()):
            tp, fp, fn = total(c)
            if tp + fp + fn:
                e = bootstrap_f1(c)
                rows.append({"group": g, "docs": e.n_docs, "f1": r1(e.value),
                             "ci": [r1(e.lo), r1(e.hi)]})  # fmt: skip
        return rows

    degraded = [d for (d,) in con.execute("SELECT doc_id FROM docs WHERE degraded").fetchall()]
    end_to_end = []
    for r, parser, cond in con.execute(
        """SELECT run_id, parser, condition FROM runs WHERE prompt = 'extract_v3'
           AND model = 'gpt-6-luna' AND replicate = 0 ORDER BY condition, parser"""
    ).fetchall():
        c = {d: x for d, x in doc_counts(con, r).items() if d in degraded}
        e = bootstrap_f1(c)
        end_to_end.append({"parser": parser, "condition": cond, "f1": r1(e.value),
                           "ci": [r1(e.lo), r1(e.hi)]})  # fmt: skip

    rel = duckdb.sql(PARSER_QUERY)  # same aggregation as docs/RESULTS.md (Phase 3)
    parsers = [dict(zip(rel.columns, row, strict=True)) for row in rel.fetchall()]

    return {
        "test_docs": len(base),
        "headline": headline,
        "paired": paired,
        "per_field": per_field,
        "by_type": breakdown("type"),
        "by_length": breakdown("d.bucket"),
        "by_status": breakdown("coalesce(status, 'n/a')"),
        "end_to_end_scans": end_to_end,
        "parsers": parsers,
    }


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    index = export_contracts(ground_truth())
    (OUT / "index.json").write_text(
        DemoIndex.model_validate({"contracts": index}).model_dump_json(indent=1)
    )
    (OUT / "evals.json").write_text(json.dumps(export_evals(), indent=1))
    size = sum(p.stat().st_size for p in OUT.rglob("*.json"))
    biggest = max(OUT.rglob("*.json"), key=lambda p: p.stat().st_size)
    print(f"{len(index)} contracts -> {OUT.relative_to(ROOT)} ({size / 1e6:.1f} MB; "
          f"largest file {biggest.stat().st_size / 1e3:.0f} KB)")  # fmt: skip


if __name__ == "__main__":
    main()
