"""Error taxonomy: why is each error an error?

Auto rules give a first-pass category from mechanical signals. They can't tell a model
misreading from a debatable label; a human review pass (evalsets/error_review.csv) does.

  missed           GT has a value, model returned nothing
  format           model returned something our normalizer couldn't parse
  ungrounded       model's quote isn't in the document (fabricated / garbled)
  misread          model quoted the same clause as GT but derived a different value
  wrong_clause     model quoted a different passage than GT
  extra            model returned a value, GT has none (over-inclusive OR missing label)
  extra_items      list field: predicted items that match no GT item
  missed_items     list field: GT items not predicted
Review-only categories: label_issue (GT debatable / inconsistent), match_rule (our matcher
judged a correct answer wrong), copy_error (model altered text while copying it).
"""

import json
import re

from docintel.eval.match import token_f1
from docintel.schema.evidence import normalize_for_match

CATEGORIES = [
    "missed", "format", "ungrounded", "misread", "wrong_clause", "extra",
    "extra_items", "missed_items", "label_issue", "match_rule", "copy_error",
]  # fmt: skip


def same_passage(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    na, nb = normalize_for_match(a), normalize_for_match(b)
    if na in nb or nb in na:
        return True
    # Short quotes share boilerplate ("as of June 1999" vs "1st day of June, 1999"), so
    # token overlap alone over-matches: also require a few shared tokens in absolute terms.
    shared = len(set(re.findall(r"[a-z0-9]+", na)) & set(re.findall(r"[a-z0-9]+", nb)))
    return token_f1(na, nb) >= 0.5 and shared >= 5


def auto_category(
    field_type: str,
    outcomes: list[str],
    pred: str,
    pred_evidence: str | None,
    gold_evidence: str | None,
    status: str | None,
    reasons: str | None,
    conversion_error: str | None,
) -> str:
    if field_type == "entity_list":
        return "extra_items" if "fp" in outcomes else "missed_items"
    o = outcomes[0]
    if conversion_error:
        return "format"
    if o == "fn":
        return "missed"
    if status == "failed" and reasons and "not found" in reasons:
        return "ungrounded"
    if o == "fp":
        return "extra"
    # wrong: both present, values differ
    if json.loads(pred) is not None and same_passage(pred_evidence, gold_evidence):
        return "misread"
    return "wrong_clause"


def error_rows(con, run_id: str, split: str = "test") -> list[dict]:
    """One row per (doc, field) with at least one error; list items are grouped."""
    rows = con.execute(
        """
        SELECT o.doc_id, field, type, list(outcome ORDER BY item), any_value(pred),
               any_value(gold), any_value(pred_evidence), any_value(gold_evidence),
               any_value(status), any_value(reasons), any_value(conversion_error)
        FROM outcomes o JOIN docs d USING (doc_id)
        WHERE run_id = ? AND d.split = ?
        GROUP BY 1, 2, 3
        HAVING count(*) FILTER (outcome IN ('fp', 'fn', 'wrong')) > 0
        ORDER BY 2, 1
        """,
        [run_id, split],
    ).fetchall()
    out = []
    for doc, field, ftype, outs, pred, gold, pev, gev, status, reasons, conv in rows:
        out.append(
            {
                "doc_id": doc,
                "field": field,
                "outcomes": " ".join(o for o in outs if o != "tp"),
                "pred": pred,
                "gold": gold,
                "pred_evidence": pev,
                "gold_evidence": gev,
                "status": status,
                "auto_category": auto_category(ftype, outs, pred, pev, gev, status, reasons, conv),
            }
        )
    return out
