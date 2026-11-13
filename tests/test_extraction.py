from types import SimpleNamespace

import pytest

from docintel.extraction import extractor as ex_mod
from docintel.extraction.extractor import Extractor, RunConfig
from docintel.extraction.llm_schema import LLMExtraction
from docintel.extraction.to_record import to_record
from docintel.schema.types import Duration, PartialDate


def _out(**overrides) -> LLMExtraction:
    absent_dur = {"evidence": None, "kind": "absent", "term": None}
    no = {"evidence": None, "present": False}
    base = {
        "document_name": {"evidence": "SUPPLY AGREEMENT", "value": "SUPPLY AGREEMENT"},
        "parties": {"evidence": "between A Inc. and B LLC", "value": ["A Inc.", "B LLC"]},
        "agreement_date": {"evidence": "as of Nov 12, 2019", "value": "2019-11-12"},
        "effective_date": {"evidence": None, "value": None},
        "expiration_date": {
            "evidence": "five (5) years from the date hereof",
            "kind": "relative",
            "date": None,
            "term": {"value": 5, "unit": "year"},
            "anchor": "agreement_date",
        },
        "renewal_term": {
            "evidence": "successive one-year periods",
            "kind": "duration",
            "term": {"value": 1, "unit": "year"},
        },
        "notice_period_to_terminate_renewal": absent_dur,
        "governing_law": {"evidence": "laws of the State of New York", "value": "New York"},
        "non_compete": no,
        "exclusivity": no,
        "uncapped_liability": no,
        "termination_for_convenience": {"evidence": "upon 30 days notice", "present": True},
        "change_of_control": no,
        "cap_on_liability": {"quotes": []},
    }
    base.update(overrides)
    return LLMExtraction.model_validate(base)


def test_relative_expiration_computed_by_code():
    rec, errors = to_record("d", _out())
    assert errors == []
    assert rec.expiration_date.value == PartialDate(year=2024, month=11, day=12)
    assert rec.renewal_term.value == Duration(value=1, unit="year")
    assert rec.governing_law.value.key() == ("United States", "New York")
    assert rec.effective_date.value is None and rec.cap_on_liability.value is None


def test_relative_expiration_without_anchor_is_an_error_not_a_guess():
    out = _out(agreement_date={"evidence": None, "value": None})
    rec, errors = to_record("d", out)
    assert rec.expiration_date.value is None
    assert any("expiration_date" in e for e in errors)
    assert rec.expiration_date.evidence  # evidence kept for review


def test_notice_period_cannot_be_perpetual():
    out = _out(
        notice_period_to_terminate_renewal={"evidence": "x", "kind": "perpetual", "term": None}
    )
    _, errors = to_record("d", out)
    assert any("notice_period" in e for e in errors)


def test_schema_rejects_bad_date_format():
    with pytest.raises(ValueError):
        _out(agreement_date={"evidence": None, "value": "Nov 12, 2019"})


def test_run_id_changes_with_prompt_and_replicate():
    a = RunConfig("gpt-6-luna", prompt="extract_v1")
    assert a.run_id != RunConfig("gpt-6-luna", prompt="extract_v3").run_id
    assert a.run_id != RunConfig("gpt-6-luna", prompt="extract_v1", replicate=1).run_id
    assert a.run_id == RunConfig("gpt-6-luna", prompt="extract_v1").run_id  # deterministic


def _usage():
    return SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )


@pytest.mark.parametrize(
    "response, status",
    [
        (
            SimpleNamespace(status="incomplete", incomplete_details="max_output_tokens"),
            "incomplete",
        ),
        (
            SimpleNamespace(
                status="completed",
                incomplete_details=None,
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="refusal", refusal="I can't help")],
                    )
                ],
            ),
            "refused",
        ),
    ],
)
def test_failed_calls_are_recorded_not_raised(tmp_path, monkeypatch, response, status):
    monkeypatch.setattr(ex_mod, "RUNS", tmp_path)
    response.usage = _usage()
    e = Extractor(RunConfig("gpt-6-luna", prompt="extract_v3"))
    e.__dict__["client"] = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kw: response))
    r = e.extract("doc", "text")
    assert r.status == status and r.record is None and r.input_tokens == 100
