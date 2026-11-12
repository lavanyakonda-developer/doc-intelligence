"""Match rules per field type: this module DEFINES what precision and recall mean.

Each comparison returns one Outcome for a (prediction, ground truth) pair:
  tp     both present and match
  wrong  both present, don't match      -> counts as 1 FP + 1 FN (standard IE convention)
  fp     predicted, but GT absent
  fn     GT present, but not predicted
  tn     both absent                    -> reported separately (credit for abstaining)
For list fields (parties) we count at item level, so one doc can yield several outcomes.
For booleans, "present" means True (the positive class).
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from rapidfuzz import fuzz

from docintel.schema.fields import FieldType
from docintel.schema.normalize import normalize_doc_name, normalize_party
from docintel.schema.types import Duration, Jurisdiction, PartialDate

Outcome = Literal["tp", "wrong", "fp", "fn", "tn"]

# PROVISIONAL defaults. Tuned on dev-set predictions (Phase 6), never on test.
# token_sort, not token_set: token_set scores 'Bank' vs 'Bank of America' as 100 (subset).
PARTY_THRESHOLD = 85  # rapidfuzz token_sort_ratio, 0-100
CLAUSE_F1_THRESHOLD = 0.5
# Scores within this distance of a threshold are logged as near-misses for human review.
PARTY_BAND = 10
CLAUSE_BAND = 0.15


@dataclass
class NearMiss:
    field_type: str
    pred: str
    gt: str
    score: float
    threshold: float
    accepted: bool  # did it count as a match?


def _present(v: Any) -> bool:
    return v not in (None, [], False, "")


def _presence(pred: Any, gt: Any, equal) -> Outcome:
    p, g = _present(pred), _present(gt)
    if p and g:
        return "tp" if equal(pred, gt) else "wrong"
    return "fp" if p else "fn" if g else "tn"


# --- per-type equality -------------------------------------------------------------


def dates_equal(pred: PartialDate | str, gt: PartialDate | str) -> bool:
    """Compare only the parts the ground truth knows ('2019-09' matches '2019-09-15')."""
    if isinstance(gt, str) or isinstance(pred, str):  # 'perpetual'
        return pred == gt
    return all(
        g is None or p == g
        for p, g in ((pred.year, gt.year), (pred.month, gt.month), (pred.day, gt.day))
    )


def durations_equal(pred: Duration | str, gt: Duration | str) -> bool:
    if isinstance(gt, str) or isinstance(pred, str):
        return pred == gt
    if pred.unit == "business_day" or gt.unit == "business_day":
        return pred == gt  # only equal to itself
    # Same unit family -> exact: 12 months == 1 year, 2 weeks == 14 days.
    if pred.in_months() is not None and gt.in_months() is not None:
        return pred.in_months() == gt.in_months()
    if pred.in_days() is not None and gt.in_days() is not None:
        return pred.in_days() == gt.in_days()
    # Across families -> 3% tolerance: "90 days" == "3 months" (91.3d), "60 days" != "1 month".
    a, b = pred.approx_days(), gt.approx_days()
    return abs(a - b) <= 0.03 * max(a, b)


def jurisdictions_equal(pred: Jurisdiction, gt: Jurisdiction) -> bool:
    # OTHER == OTHER: the model correctly recognized a non-standard clause. Lenient by design;
    # these cases are few and reviewed manually in error analysis.
    return pred.key() == gt.key()


def doc_names_equal(pred: str, gt: str) -> bool:
    return normalize_doc_name(pred) == normalize_doc_name(gt)


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def token_f1(pred: str, gt: str) -> float:
    """SQuAD-style bag-of-tokens F1."""
    p, g = Counter(_tokens(pred)), Counter(_tokens(gt))
    overlap = sum((p & g).values())
    if not overlap:
        return 0.0
    prec, rec = overlap / sum(p.values()), overlap / sum(g.values())
    return 2 * prec * rec / (prec + rec)


def clause_score(pred: list[str], gt: list[str]) -> float:
    """Doc-level: concatenate all spans on each side, so different segmentation
    (one long quote vs three short ones) isn't punished."""
    return token_f1(" ".join(pred), " ".join(gt))


def match_parties(
    pred: list[str] | None,
    gt: list[str] | None,
    threshold: float = PARTY_THRESHOLD,
    near_misses: list[NearMiss] | None = None,
) -> list[Outcome]:
    """Greedy one-to-one matching by best fuzzy score. Unmatched pred -> fp, unmatched gt -> fn."""
    pred, gt = pred or [], gt or []
    if not pred and not gt:
        return ["tn"]
    pairs = sorted(
        (
            (fuzz.token_sort_ratio(normalize_party(p), normalize_party(g)), i, j)
            for i, p in enumerate(pred)
            for j, g in enumerate(gt)
        ),
        reverse=True,
    )
    used_p, used_g, out = set(), set(), []
    for score, i, j in pairs:
        if i in used_p or j in used_g:
            continue
        accepted = score >= threshold
        if near_misses is not None and abs(score - threshold) < PARTY_BAND:
            near_misses.append(NearMiss("entity_list", pred[i], gt[j], score, threshold, accepted))
        if accepted:
            used_p.add(i)
            used_g.add(j)
            out.append("tp")
    out += ["fp"] * (len(pred) - len(used_p)) + ["fn"] * (len(gt) - len(used_g))
    return out


# --- dispatch ----------------------------------------------------------------------

_EQUAL = {
    "text": doc_names_equal,
    "date": dates_equal,
    "duration": durations_equal,
    "enum": jurisdictions_equal,
    "boolean": lambda p, g: p == g,
}


def match(
    field_type: FieldType,
    pred: Any,
    gt: Any,
    *,
    party_threshold: float = PARTY_THRESHOLD,
    clause_threshold: float = CLAUSE_F1_THRESHOLD,
    near_misses: list[NearMiss] | None = None,
) -> list[Outcome]:
    """Thresholds are parameters so a tuning sweep can re-score without editing code;
    pass a list as `near_misses` to collect borderline decisions for review."""
    if field_type == "entity_list":
        return match_parties(pred, gt, party_threshold, near_misses)
    if field_type == "clause":

        def equal(p, g):
            score = clause_score(p, g)
            accepted = score >= clause_threshold
            if near_misses is not None and abs(score - clause_threshold) < CLAUSE_BAND:
                near_misses.append(
                    NearMiss(
                        "clause", " … ".join(p), " … ".join(g), score, clause_threshold, accepted
                    )
                )
            return accepted

        return [_presence(pred, gt, equal)]
    return [_presence(pred, gt, _EQUAL[field_type])]
