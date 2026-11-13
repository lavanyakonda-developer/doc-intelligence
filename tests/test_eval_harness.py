import json

import pytest

from docintel.eval.db import run_rows
from docintel.eval.metrics import bootstrap_f1, f1, paired_bootstrap, prf, total
from docintel.eval.taxonomy import auto_category
from docintel.extraction.to_record import to_record
from tests.test_extraction import _out

# --- metrics ------------------------------------------------------------------------------


def test_prf_counts_wrong_once_on_each_side():
    assert prf(8, 2, 2) == pytest.approx((0.8, 0.8, 0.8))
    assert prf(0, 0, 0) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_contains_point_and_is_deterministic():
    counts = {f"d{i}": (8 + i % 3, i % 2, 1) for i in range(20)}
    a, b = bootstrap_f1(counts, seed=1), bootstrap_f1(counts, seed=1)
    assert a == b
    assert a.lo <= a.value <= a.hi
    assert a.value == pytest.approx(f1(total(counts)))


def test_paired_bootstrap_identical_runs_is_zero():
    counts = {f"d{i}": (5, i % 3, 1) for i in range(15)}
    pb = paired_bootstrap(counts, counts)
    assert pb.diff == 0 and pb.lo == 0 and pb.hi == 0


def test_paired_bootstrap_detects_consistent_drop():
    """The regression gate must fire when every doc gets worse, even with few docs."""
    a = {f"d{i}": (10, 1, 1) for i in range(10)}
    b = {f"d{i}": (8, 3, 3) for i in range(10)}
    pb = paired_bootstrap(a, b)
    assert pb.hi < 0 and pb.p_not_better == 1.0


# --- taxonomy -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ftype, outcomes, pred, pev, gev, status, reasons, conv, expected",
    [
        ("entity_list", ["tp", "fp"], "[]", None, None, None, None, None, "extra_items"),
        ("entity_list", ["tp", "fn"], "[]", None, None, None, None, None, "missed_items"),
        ("date", ["wrong"], '"x"', None, None, None, None, "bad date", "format"),
        ("date", ["fn"], "null", None, "May 1, 2020", "absent", None, None, "missed"),
        ("boolean", ["fp"], "true", "q", None, "failed", "evidence quote not found", None,
         "ungrounded"),
        ("boolean", ["fp"], "true", "some clause", None, "verified", "", None, "extra"),
        ("date", ["wrong"], '"2019"', "as of September ___, 2019", "September ___, 2019",
         "unverified", "", None, "misread"),
        ("date", ["wrong"], '"1999-06-30"', "executed as of June 30, 1999",
         "1st day of June, 1999", "verified", "", None, "wrong_clause"),
    ],
)  # fmt: skip
def test_auto_category(ftype, outcomes, pred, pev, gev, status, reasons, conv, expected):
    assert auto_category(ftype, outcomes, pred, pev, gev, status, reasons, conv) == expected


# --- db rows ------------------------------------------------------------------------------


def test_run_rows_one_row_per_outcome_and_list_items():
    gold, _ = to_record("d", _out(parties={"evidence": None, "value": ["A Inc.", "B LLC"]}))
    pred, errors = to_record(
        "d", _out(parties={"evidence": None, "value": ["A Inc.", "B LLC", "C Corp"]})
    )
    gt = {
        "d": {
            "record": json.loads(gold.model_dump_json()),
            "excluded_fields": ["exclusivity"],
            "derived_fields": ["expiration_date"],
        }
    }
    results = {
        "d": {"status": "ok", "record": json.loads(pred.model_dump_json()),
              "conversion_errors": errors}
    }  # fmt: skip
    cfg = {"run_id": "r", "parser": "no-such-parser", "condition": "clean"}  # no text -> no status
    rows = run_rows(cfg, results, gt)
    by_field = {}
    for r in rows:
        by_field.setdefault(r[2], []).append(r)
    assert "exclusivity" not in by_field  # excluded fields are not scored
    assert sorted(r[5] for r in by_field["parties"]) == ["fp", "tp", "tp"]
    assert [r[4] for r in by_field["parties"]] == [0, 1, 2]  # item index
    assert by_field["expiration_date"][0][10] is True  # derived flag carried through
    assert all(r[11] is None for r in rows)  # validator status needs parsed text
