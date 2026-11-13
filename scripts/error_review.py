"""Write every test error of the production run to evalsets/error_review.csv for human review.

Re-running keeps the human columns (draft_category, final_category, note) for rows that
still exist, keyed by (doc_id, field), so the review survives prompt/model changes.
Prints the category summary (final_category if reviewed, else draft, else auto).

  uv run python scripts/error_review.py
"""

import csv
from collections import Counter
from pathlib import Path

from docintel.eval.db import connect
from docintel.eval.taxonomy import CATEGORIES, error_rows

PRODUCTION = "6-luna-low-extract_v3-pypdf-clean-r0"
CSV = Path(__file__).resolve().parents[1] / "evalsets" / "error_review.csv"
HUMAN = ["draft_category", "final_category", "note"]
COLUMNS = ["doc_id", "field", "outcomes", "auto_category", *HUMAN, "pred", "gold",
           "pred_evidence", "gold_evidence"]  # fmt: skip


def category(row: dict) -> str:
    return row.get("final_category") or row.get("draft_category") or row["auto_category"]


def main() -> None:
    con = connect()
    (rid,) = con.execute(
        "SELECT run_id FROM runs WHERE starts_with(run_id, ?)", [PRODUCTION]
    ).fetchone()
    old = {}
    if CSV.exists():
        with open(CSV) as f:
            old = {(r["doc_id"], r["field"]): r for r in csv.DictReader(f)}
    rows = []
    for r in error_rows(con, rid):
        prev = old.get((r["doc_id"], r["field"]), {})
        for h in HUMAN:
            r[h] = prev.get(h, "")
        bad = [c for c in (r["draft_category"], r["final_category"]) if c and c not in CATEGORIES]
        if bad:
            raise SystemExit(f"unknown category {bad} for {r['doc_id']} / {r['field']}")
        rows.append({k: (r[k] or "")[:600] for k in COLUMNS})
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    reviewed = sum(bool(r["final_category"]) for r in rows)
    print(f"{len(rows)} error rows -> {CSV.name} ({reviewed} human-reviewed)")
    for cat, n in Counter(category(r) for r in rows).most_common():
        print(f"  {cat:14s} {n}")


if __name__ == "__main__":
    main()
