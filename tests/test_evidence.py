import json
from pathlib import Path

import pytest

from docintel.schema.evidence import evidence_found, normalize_for_match

ROOT = Path(__file__).resolve().parents[1]
TXT = ROOT / "data" / "raw" / "CUAD_v1" / "full_contract_txt"


def test_whitespace_and_line_breaks():
    doc = "This Agreement shall\n   continue  for a period\tof five (5) years."
    assert evidence_found("shall continue for a period of five (5) years", doc)


def test_hyphenation_and_curly_quotes():
    doc = "the “Effective Date”; termi-\nnation for convenience"
    assert evidence_found('the "Effective Date"', doc)
    assert evidence_found("termination for convenience", doc)


def test_fabricated_quote_rejected():
    assert not evidence_found("liability is uncapped", "Liability is capped at fees paid.")


def test_multi_span_requires_all():
    doc = "Clause A text. Other stuff. Clause B text."
    assert evidence_found("clause a text … clause b text", doc)
    assert not evidence_found("clause a text … clause c text", doc)


def test_empty_evidence_is_not_found():
    assert not evidence_found("", "anything")


def test_normalize_idempotent():
    s = "A  “b”\n c"
    assert normalize_for_match(normalize_for_match(s)) == normalize_for_match(s)


@pytest.mark.skipif(not TXT.exists(), reason="CUAD not downloaded (make data)")
def test_cuad_spans_are_found_in_cuad_text():
    """Calibration: CUAD's own highlighted spans must pass our check against CUAD's text.
    If this rate drops, the normalizer is too strict and would flag correct LLM quotes."""
    total = found = 0
    for line in (ROOT / "evalsets" / "ground_truth.jsonl").read_text().splitlines():
        item = json.loads(line)
        doc = normalize_for_match((TXT / f"{item['doc_id']}.txt").read_text(errors="ignore"))
        for name, f in item["record"].items():
            if name != "doc_id" and f["evidence"]:
                total += 1
                found += evidence_found(f["evidence"], "", normalized_doc=doc)
    assert total > 200
    assert found / total >= 0.98, f"{found}/{total}"


def test_cuad_omitted_marker_splits_spans():
    doc = "Party may terminate as follows: (a) by notice; (b) upon a change of control."
    assert evidence_found("terminate as follows:<omitted>(b) upon a change of control", doc)
