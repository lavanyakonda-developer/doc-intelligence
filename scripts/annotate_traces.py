"""Attach eval outcomes to traces: one span annotation per (document, field) on the
document's root span, plus a document-level F1. In Phoenix you can then filter, e.g.
    annotations['governing_law'].label == 'wrong'
to open every trace where that field was wrong.

Annotations come from the eval harness (ground truth), never from the pipeline itself:
the pipeline must not see labels. Re-running is safe: annotations upsert by identifier.

  uv run --group observability python scripts/annotate_traces.py
"""

import json
from collections import defaultdict

from phoenix.client import Client

from docintel.config import PROJECT_ROOT
from docintel.eval.db import build
from docintel.eval.metrics import f1

TRACED = PROJECT_ROOT / "data" / "results" / "traced_run.json"
IDENTIFIER = "eval-v1"  # bump if the scoring rules change


def outcome(outs: list[str]) -> tuple[str, float]:
    if set(outs) <= {"tp", "tn"}:
        return "correct", 1.0
    return ("partial", 0.5) if "tp" in outs else ("wrong", 0.0)


def main() -> None:
    traced = json.loads(TRACED.read_text())
    run_ids = {v["run_id"] for v in traced.values() if v["run_id"]}
    assert len(run_ids) == 1, run_ids
    (run_id,) = run_ids
    con = build()  # picks up the traced run from data/runs/
    rows = con.execute(
        """SELECT o.doc_id, field, list(outcome), d.split FROM outcomes o
           JOIN docs d USING (doc_id) WHERE run_id = ? GROUP BY ALL""",
        [run_id],
    ).fetchall()
    per_doc = defaultdict(lambda: [0, 0, 0])
    annotations = []
    for doc, field, outs, split in rows:
        span_id = traced[doc]["span_id"]
        label, score = outcome(outs)
        annotations.append({
            "name": field, "annotator_kind": "CODE", "span_id": span_id,
            "identifier": IDENTIFIER,
            "result": {"label": label, "score": score},
            "metadata": {"outcomes": outs, "split": split},
        })  # fmt: skip
        c = per_doc[doc]
        c[0] += outs.count("tp")
        c[1] += outs.count("fp") + outs.count("wrong")
        c[2] += outs.count("fn") + outs.count("wrong")
    for doc, c in per_doc.items():
        annotations.append({
            "name": "doc_f1", "annotator_kind": "CODE", "span_id": traced[doc]["span_id"],
            "identifier": IDENTIFIER,
            "result": {"score": round(f1(tuple(c)), 4),
                       "label": "perfect" if c[1] == c[2] == 0 else "has_errors"},
        })  # fmt: skip
    Client().spans.log_span_annotations(span_annotations=annotations, sync=True)
    wrong = sum(a["result"].get("label") == "wrong" for a in annotations)
    print(f"{len(annotations)} annotations on {len(per_doc)} traces ({wrong} wrong fields)")


if __name__ == "__main__":
    main()
