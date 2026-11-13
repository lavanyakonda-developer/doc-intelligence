from types import SimpleNamespace

from docintel.extraction.extractor import ExtractionResult
from docintel.extraction.to_record import to_record
from docintel.schema.types import PartialDate
from docintel.validation.pipeline import process
from docintel.validation.text_values import dates_in_text, numbers_in_text
from docintel.validation.validate import failed_fields, validate
from tests.test_extraction import _out

DOC = """SUPPLY AGREEMENT
This Supply Agreement is made as of Nov 12, 2019 between A Inc. and B LLC.
1. Term. This Agreement expires five (5) years from the date hereof and renews for
successive one-year periods. Either party may terminate upon 30 days notice.
2. This Agreement is governed by the laws of the State of New York.
"""


def _checks(**overrides):
    rec, errors = to_record("d", _out(**overrides))
    return validate(rec, DOC, errors)


# --- text_values ------------------------------------------------------------------------


def test_dates_in_text_formats():
    found = dates_in_text("on the 25th day of May, 2018 or 6/1/21 or June 2020 or May 31 st 2021")
    assert PartialDate(year=2018, month=5, day=25) in found
    assert PartialDate(year=2021, month=6, day=1) in found
    assert PartialDate(year=2020, month=6) in found
    assert PartialDate(year=2021, month=5, day=31) in found


def test_numbers_in_text_words_and_digits():
    assert {5, 30, 1} <= numbers_in_text("five (5) years, thirty days, one year")


# --- validate ---------------------------------------------------------------------------


def test_clean_extraction_is_verified():
    checks = _checks()
    assert failed_fields(checks) == {}
    assert checks["governing_law"].status == "verified"
    assert checks["governing_law"].grounding == "exact"
    s, e = checks["governing_law"].spans[0]
    assert DOC[s:e].lower() == "laws of the state of new york"
    assert checks["non_compete"].status == "absent"


def test_fabricated_quote_fails_grounding():
    checks = _checks(
        governing_law={"evidence": "laws of the State of Delaware", "value": "Delaware"}
    )
    assert checks["governing_law"].status == "failed"


def test_value_contradicting_its_own_quote_fails():
    checks = _checks(agreement_date={"evidence": "as of Nov 12, 2019", "value": "2019-12-11"})
    assert checks["agreement_date"].status == "failed"
    assert "not among dates" in checks["agreement_date"].reasons[0]


def test_boolean_true_without_quote_fails():
    checks = _checks(exclusivity={"evidence": None, "present": True})
    assert checks["exclusivity"].status == "failed"


def test_party_not_in_document_fails():
    checks = _checks(parties={"evidence": None, "value": ["A Inc.", "Zeta Holdings"]})
    assert checks["parties"].status == "failed"


def test_single_party_is_unverified():
    checks = _checks(parties={"evidence": "between A Inc.", "value": ["A Inc."]})
    assert checks["parties"].status == "unverified"


def test_expiration_before_start_fails_cross_field():
    checks = _checks(
        expiration_date={
            "evidence": "as of Nov 12, 2019",
            "kind": "date",
            "date": "2019-11-12",
            "term": None,
            "anchor": None,
        },
        effective_date={"evidence": "as of Nov 12, 2019", "value": "2019-11-12"},
    )
    assert checks["expiration_date"].status != "failed"  # equal dates are fine
    rec, errors = to_record(
        "d",
        _out(
            effective_date={"evidence": "as of Nov 12, 2019", "value": "2019-11-12"},
            expiration_date={
                "evidence": "6/1/2018",
                "kind": "date",
                "date": "2018-06-01",
                "term": None,
                "anchor": None,
            },
        ),
    )
    checks = validate(rec, DOC + "\nExpires 6/1/2018.", errors)
    assert checks["expiration_date"].status == "failed"
    assert any("before" in r for r in checks["expiration_date"].reasons)


# --- pipeline: retry merges only failing fields --------------------------------------------


def _result(raw: dict) -> ExtractionResult:
    rec, errors = to_record("d", _out(**raw))
    full = _out(**raw).model_dump(mode="json")
    return ExtractionResult(
        "d", "run", "ok", full, rec.model_dump(mode="json"), errors, cost_usd=0.001
    )


def test_retry_fixes_failed_field_and_cannot_regress_passing_ones():
    bad = {"governing_law": {"evidence": "laws of the State of Delaware", "value": "Delaware"}}
    # The retry fixes governing_law but (wrongly) drops parties: the merge must ignore that.
    retry_raw = {
        "governing_law": {"evidence": "laws of the State of New York", "value": "New York"},
        "parties": {"evidence": None, "value": []},
    }
    calls = []
    fake = SimpleNamespace(
        extract=lambda doc_id, text: _result(bad),
        retry=lambda doc_id, text, prev, failures: calls.append(failures) or _result(retry_raw),
    )
    r = process(fake, "d", DOC)
    assert list(calls[0]) == ["governing_law"]  # feedback names only the failing field
    assert r.fixed_by_retry == ["governing_law"]
    assert r.record.governing_law.value.key() == ("United States", "New York")
    assert r.record.parties.value == ["A Inc.", "B LLC"]  # kept from the first pass
    assert r.cost_usd == 0.002


def test_no_retry_when_nothing_failed():
    fake = SimpleNamespace(extract=lambda doc_id, text: _result({}), retry=None)
    r = process(fake, "d", DOC)
    assert r.retry is None and r.failed_before == {}


def test_abbreviated_months():
    assert PartialDate(year=2019, month=11, day=12) in dates_in_text("as of Nov. 12, 2019")
    assert PartialDate(year=2020, month=9, day=1) in dates_in_text("Sept 1, 2020")
