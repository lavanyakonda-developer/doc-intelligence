"""Score a run against ground truth: per-field counts -> precision / recall / F1.

Minimal Phase 4 version (enough to iterate on dev). Phase 6 adds DuckDB storage, breakdowns
by field type / doc length / parser, and the error taxonomy.
"""

import json
from collections import Counter
from dataclasses import dataclass, field

from docintel.eval.match import NearMiss, match
from docintel.schema.fields import FIELDS
from docintel.schema.types import ContractRecord


@dataclass
class FieldScore:
    field: str
    type: str
    counts: Counter = field(default_factory=Counter)

    @property
    def tp(self) -> int:
        return self.counts["tp"]

    @property
    def fp(self) -> int:  # 'wrong' = confidently wrong value -> counts as FP and FN (D4)
        return self.counts["fp"] + self.counts["wrong"]

    @property
    def fn(self) -> int:
        return self.counts["fn"] + self.counts["wrong"]

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else (0.0 if p is not None or r is not None else None)


def _empty_record(doc_id: str) -> ContractRecord:
    empty = {"value": None, "evidence": None}
    return ContractRecord(doc_id=doc_id, **{f.name: empty for f in FIELDS})


def score(
    results: dict[str, dict],  # doc_id -> ExtractionResult as dict
    gt: dict[str, dict],  # doc_id -> ground-truth item
    *,
    near_misses: list[NearMiss] | None = None,
    per_doc: list[dict] | None = None,
) -> list[FieldScore]:
    scores = {f.name: FieldScore(f.name, f.type) for f in FIELDS}
    for doc_id, item in gt.items():
        res = results.get(doc_id)
        ok = res is not None and res["status"] == "ok"
        # A failed call (refusal/error/truncation) predicts nothing: GT positives become FNs.
        pred = ContractRecord.model_validate(res["record"]) if ok else _empty_record(doc_id)
        truth = ContractRecord.model_validate(item["record"])
        for f in FIELDS:
            if f.name in item["excluded_fields"]:
                continue
            p, g = getattr(pred, f.name).value, getattr(truth, f.name).value
            outcomes = match(f.type, p, g, near_misses=near_misses)
            scores[f.name].counts.update(outcomes)
            if per_doc is not None:
                per_doc.append(
                    {
                        "doc_id": doc_id,
                        "field": f.name,
                        "type": f.type,
                        "outcomes": outcomes,
                        "pred": json.dumps(p, default=str),
                        "gt": json.dumps(g, default=str),
                        "derived": f.name in item.get("derived_fields", []),
                    }
                )
    return list(scores.values())


def micro(scores: list[FieldScore]) -> FieldScore:
    total = FieldScore("ALL", "all")
    for s in scores:
        total.counts.update(s.counts)
    return total


def format_table(scores: list[FieldScore]) -> str:
    def pct(x):
        return "  -  " if x is None else f"{100 * x:5.1f}"

    lines = [f"{'field':36s} {'type':12s}   P      R      F1    tp  fp  fn  tn  wrong"]
    for s in [*scores, micro(scores)]:
        c = s.counts
        lines.append(
            f"{s.field:36s} {s.type:12s} {pct(s.precision)}  {pct(s.recall)}  {pct(s.f1)}"
            f"  {s.tp:3d} {s.fp:3d} {s.fn:3d} {c['tn']:3d} {c['wrong']:4d}"
        )
    return "\n".join(lines)
