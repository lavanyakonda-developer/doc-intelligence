"""Phase 5 experiment: retry effectiveness + abstention policies (precision vs coverage).

1. Runs extract -> validate -> retry-once on every doc of the given runs (API calls only for
   docs with failed fields; everything else is cached).
2. Self-consistency: for the text-layer config we have 3 replicate runs; a field "agrees"
   when all 3 replicates give matching values (same match rules as the evals).
3. Scores abstention policies on the TEST split: abstaining = returning no value for a field.

  uv run python scripts/run_validation.py
"""

import json
from collections import Counter
from pathlib import Path

from docintel.corpus import ground_truth
from docintel.eval.match import match
from docintel.eval.score import micro, score
from docintel.extraction.extractor import Extractor, RunConfig
from docintel.parsing.base import CACHE_DIR
from docintel.schema.fields import FIELDS
from docintel.schema.types import ContractRecord
from docintel.validation.pipeline import process

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "RESULTS.md"
BASE = RunConfig("gpt-6-luna", "low", "extract_v3", "pypdf", "clean")
SCANS = [
    RunConfig("gpt-6-luna", "low", "extract_v3", "vision-gpt-6-luna", "heavy"),
    RunConfig("gpt-6-luna", "low", "extract_v3", "docling", "heavy"),
]


def text_for(cfg: RunConfig, doc: str) -> str:
    return json.loads((CACHE_DIR / cfg.parser / cfg.condition / f"{doc}.json").read_text())["text"]


SUMMARY: list[str] = []  # lines for RESULTS.md


def run_pipeline(cfg: RunConfig, docs: list[str]) -> dict:
    ex = Extractor(cfg)
    out = {d: process(ex, d, text_for(cfg, d)) for d in docs}
    failed = sum(len(r.failed_before) for r in out.values())
    fixed = sum(len(r.fixed_by_retry) for r in out.values())
    retried = [r for r in out.values() if r.retry]
    cost = sum(r.retry.cost_usd for r in retried)
    n_fields = sum(1 for r in out.values() for c in r.checks.values() if c.status != "absent")
    print(
        f"{cfg.run_id}: {len(docs)} docs, {n_fields} non-absent fields, {failed} failed "
        f"({100 * failed / max(n_fields, 1):.1f}%), {len(retried)} docs retried (${cost:.4f}), "
        f"retry fixed {fixed}/{failed}"
    )
    SUMMARY.append(
        f"| {cfg.parser} / {cfg.condition} | {len(docs)} | {n_fields} | {failed} | {fixed} | "
        f"${cost:.4f} |"
    )
    for r in retried:
        print(f"   {r.doc_id[:40]:40s} failed={list(r.failed_before)} fixed={r.fixed_by_retry}")
    return out


def agreement(docs: list[str], gt: dict) -> dict[tuple[str, str], bool]:
    """(doc, field) -> True if all 3 replicate runs agree on the value."""
    reps = []
    for r in range(3):
        ex = Extractor(RunConfig(**{**BASE.__dict__, "replicate": r}))
        reps.append({d: ContractRecord.model_validate(ex.extract(d, "").record) for d in docs})
    agree = {}
    for d in docs:
        for f in FIELDS:
            vals = [getattr(rep[d], f.name).value for rep in reps]
            agree[(d, f.name)] = all(set(match(f.type, v, vals[0])) <= {"tp", "tn"} for v in vals)
    return agree


def evaluate(policy: str, results: dict, gt: dict, keep) -> dict:
    """Score with abstention: fields where keep(doc, field) is False return no value."""
    kept = predicted = 0
    as_results = {}
    for d, r in results.items():
        rec = r.record.model_dump(mode="json")
        for f in FIELDS:
            if rec[f.name]["value"] in (None, False, []):
                continue
            predicted += 1
            if keep(d, f.name, r.checks[f.name].status):
                kept += 1
            else:
                rec[f.name] = {"value": None, "evidence": None}
        as_results[d] = {"status": "ok", "record": rec}
    m = micro(score(as_results, gt))
    return {
        "policy": policy,
        "P": m.precision,
        "R": m.recall,
        "F1": m.f1,
        "coverage": kept / predicted,
        "fp": m.fp,
        "fn": m.fn,
    }


def main() -> None:
    gt_all = ground_truth()
    all_docs = sorted(gt_all)
    test_docs = [d for d in all_docs if gt_all[d]["split"] == "test"]
    scan_docs = sorted(p.stem for p in (CACHE_DIR / "vision-gpt-6-luna" / "heavy").glob("*.json"))

    print("== Retry with feedback")
    base = run_pipeline(BASE, all_docs)
    for cfg in SCANS:
        run_pipeline(cfg, scan_docs)

    print("\n== Self-consistency (3 replicates) vs correctness, test split")
    agree = agreement(all_docs, gt_all)
    tally = Counter()
    for d in test_docs:
        truth = ContractRecord.model_validate(gt_all[d]["record"])
        for f in FIELDS:
            v = getattr(base[d].record, f.name).value
            if f.name in gt_all[d]["excluded_fields"] or v in (None, False, []):
                continue
            ok = set(match(f.type, v, getattr(truth, f.name).value)) <= {"tp", "tn"}
            tally[(agree[(d, f.name)], ok)] += 1
    for a in (True, False):
        n = tally[(a, True)] + tally[(a, False)]
        if n:
            label = "agree   " if a else "disagree"
            acc = 100 * tally[(a, True)] / n
            print(f"  replicas {label} n={n:3d} accuracy={acc:5.1f}%")
            SUMMARY.append(f"| replicas {label.strip()} | {n} | {acc:.1f}% |")

    print("\n== Abstention policies, test split (22 docs)")
    gt = {d: gt_all[d] for d in test_docs}
    res = {d: base[d] for d in test_docs}
    rows = [
        evaluate("accept all", res, gt, lambda d, f, s: True),
        evaluate("abstain: failed", res, gt, lambda d, f, s: s != "failed"),
        evaluate("abstain: failed + unverified", res, gt, lambda d, f, s: s == "verified"),
        evaluate("abstain: replicas disagree", res, gt, lambda d, f, s: agree[(d, f)]),
        evaluate(
            "abstain: unverified OR disagree",
            res,
            gt,
            lambda d, f, s: s == "verified" and agree[(d, f)],
        ),
    ]
    table = (
        "| policy | precision | recall | F1 | coverage | FP | FN |\n|---|---|---|---|---|---|---|\n"
    )
    for r in rows:
        table += (
            f"| {r['policy']} | {100 * r['P']:.1f} | {100 * r['R']:.1f} | {100 * r['F1']:.1f} | "
            f"{100 * r['coverage']:.1f}% | {r['fp']} | {r['fn']} |\n"
        )
    print(table)

    section = (
        "<!-- validation:start -->\n## Validation & abstention (Phase 5)\n\n"
        "gpt-6-luna, prompt v3, pypdf text, 22 test docs. Abstaining = returning no value for "
        "a field (it goes to human review). Coverage = share of predicted values still "
        "returned. Self-consistency uses 3 replicate runs (cost 3× extraction).\n\n"
        "**Retry with feedback** (fields failing deterministic checks get one retry):\n\n"
        "| parser / condition | docs | non-absent fields | failed | fixed by retry | retry $ |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(SUMMARY[:3]) + "\n\n"
        "**Self-consistency vs correctness** (test, predicted fields):\n\n"
        "| signal | n | accuracy |\n|---|---|---|\n" + "\n".join(SUMMARY[3:]) + "\n\n"
        "**Abstention policies:**\n\n" + table + "<!-- validation:end -->\n"
    )
    text = RESULTS.read_text()
    if "<!-- validation:start -->" in text:
        import re

        text = re.sub(
            r"<!-- validation:start -->.*<!-- validation:end -->\n", section, text, flags=re.S
        )
    else:
        text += "\n" + section
    RESULTS.write_text(text)


if __name__ == "__main__":
    main()
