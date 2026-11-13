"""Does validation status predict correctness? (Validator quality, measured against GT.)

For each run: every predicted (non-absent) field gets a validator status; we compare it with
whether the value is actually correct. A useful validator has high accuracy on 'verified'
and low accuracy on 'failed'.

  uv run python scripts/validation_report.py --runs 6-luna-low-extract_v3-pypdf-clean-r0
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from docintel.corpus import ground_truth
from docintel.eval.match import match
from docintel.extraction.extractor import RUNS
from docintel.parsing.base import CACHE_DIR
from docintel.schema.fields import FIELDS
from docintel.schema.types import ContractRecord
from docintel.validation.validate import validate


def find_run(prefix: str) -> Path:
    hits = [p for p in RUNS.iterdir() if p.name.startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit(f"{prefix!r} matches {len(hits)} runs")
    return hits[0]


def analyze(run: Path, split: str | None) -> None:
    cfg = json.loads((run / "config.json").read_text())
    gt = ground_truth()
    tally: dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    for f in sorted(run.glob("*.json")):
        if f.name == "config.json":  # retries live in a retries/ subfolder, not matched by glob
            continue
        r = json.loads(f.read_text())
        doc = r["doc_id"]
        if r["status"] != "ok" or (split and gt[doc]["split"] != split):
            continue
        text = json.loads(
            (CACHE_DIR / cfg["parser"] / cfg["condition"] / f"{doc}.json").read_text()
        )["text"]
        rec = ContractRecord.model_validate(r["record"])
        truth = ContractRecord.model_validate(gt[doc]["record"])
        checks = validate(rec, text, r["conversion_errors"])
        for s in FIELDS:
            c = checks[s.name]
            if c.status == "absent" or s.name in gt[doc]["excluded_fields"]:
                continue
            outs = match(s.type, getattr(rec, s.name).value, getattr(truth, s.name).value)
            tally[c.status]["correct" if set(outs) <= {"tp", "tn"} else "wrong"] += 1
            reasons.update(why.split(":")[0][:50] for why in c.reasons)

    print(f"\n== {run.name}" + (f"  [{split}]" if split else ""))
    for st in ("verified", "unverified", "failed"):
        t = tally[st]
        n = sum(t.values())
        if n:
            print(
                f"  {st:10s} n={n:3d}  correct={t['correct']:3d}  wrong={t['wrong']:3d}"
                f"  accuracy={100 * t['correct'] / n:5.1f}%"
            )
    print("  reasons:", reasons.most_common(8))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="run-id prefixes")
    ap.add_argument("--split", choices=["dev", "test"])
    args = ap.parse_args()
    for prefix in args.runs:
        analyze(find_run(prefix), args.split)


if __name__ == "__main__":
    main()
