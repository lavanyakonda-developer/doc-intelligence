"""Regression gate: is a candidate run significantly worse than the committed baseline?

The baseline is a small committed snapshot of per-doc (tp, fp, fn) counts on the test split
(evalsets/baseline.json), so the check works without the gitignored data/ folder of the
baseline run. Paired bootstrap on the same docs:
  FAIL  if the 95% CI of ΔF1 is entirely below 0 (significantly worse)
  WARN  if ΔF1 < -2 points but not significant (22 docs can't resolve small drops)

  uv run python scripts/eval_check.py --write-baseline     # snapshot the production run
  uv run python scripts/eval_check.py --candidate <run-id prefix>
"""

import argparse
import json
import sys
from pathlib import Path

from docintel.eval.db import connect
from docintel.eval.metrics import bootstrap_f1, doc_counts, paired_bootstrap

PRODUCTION = "6-luna-low-extract_v3-pypdf-clean-r0"
BASELINE = Path(__file__).resolve().parents[1] / "evalsets" / "baseline.json"
WARN_DROP = 0.02


def counts_for(con, prefix: str) -> tuple[str, dict]:
    (rid,) = con.execute(
        "SELECT run_id FROM runs WHERE starts_with(run_id, ?)", [prefix]
    ).fetchone()
    return rid, doc_counts(con, rid, split="test")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=PRODUCTION, help="run-id prefix")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()
    con = connect()

    if args.write_baseline:
        rid, counts = counts_for(con, PRODUCTION)
        e = bootstrap_f1(counts)
        BASELINE.write_text(
            json.dumps(
                {"run_id": rid, "split": "test", "f1": round(e.value, 4),
                 "ci": [round(e.lo, 4), round(e.hi, 4)],
                 "per_doc": {d: list(c) for d, c in sorted(counts.items())}},
                indent=1,
            ) + "\n"
        )  # fmt: skip
        print(f"baseline <- {rid}: F1 {e.fmt()}")
        return 0

    base = json.loads(BASELINE.read_text())
    a = {d: tuple(c) for d, c in base["per_doc"].items()}
    rid, b = counts_for(con, args.candidate)
    missing = set(a) - set(b)
    if missing:
        print(f"FAIL: candidate is missing {len(missing)} test docs")
        return 1
    pb = paired_bootstrap(a, b)
    msg = (
        f"{rid} vs baseline {base['run_id']}: ΔF1 {100 * pb.diff:+.1f} "
        f"[{100 * pb.lo:+.1f}, {100 * pb.hi:+.1f}] on {pb.n_docs} docs"
    )
    if pb.hi < 0:
        print("FAIL (significantly worse):", msg)
        return 1
    print(("WARN (drop not significant): " if pb.diff < -WARN_DROP else "PASS: ") + msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
