from pathlib import Path
from types import SimpleNamespace

import pytest

from docintel.llm.pricing import cost_usd
from docintel.parsing import base
from docintel.parsing.base import ParseResult, parse_cached
from docintel.parsing.metrics import evidence_recall, word_error_rate


def _gt(*evidence: str) -> dict:
    fields = {f"f{i}": {"value": True, "evidence": e} for i, e in enumerate(evidence)}
    return {"record": {"doc_id": "x", **fields}}


def test_evidence_recall_exact_and_fuzzy():
    gt = _gt("This Agreement shall be governed by the laws of New York.", "Term is five years.")
    ocr = "This Agreernent shall be govemed by the laws of New Y0rk.\nTerm is five years."
    r = evidence_recall(ocr, gt)
    assert r == {"spans": 2, "exact": 1, "fuzzy": 2}  # OCR noise: missed exactly, found fuzzily


def test_evidence_recall_ignores_markdown():
    gt = _gt("Section 1. Services provided by Tadeo")
    assert evidence_recall("## Section 1. **Services** provided by Tadeo", gt)["exact"] == 1


def test_evidence_recall_symmetric_normalization():
    # Regression: blank form lines and redaction marks in CUAD spans must still match.
    gt = _gt("Effective Date: ____________ and fee of [*] dollars")
    assert evidence_recall("Effective Date: ____________ and fee of [*] dollars", gt)["exact"] == 1


def test_evidence_recall_missing_text():
    assert evidence_recall("", _gt("A clause that is nowhere to be found."))["fuzzy"] == 0


def test_wer():
    assert word_error_rate("a b c d", "a b c d") == 0
    assert word_error_rate("a x c d", "a b c d") == 0.25
    assert word_error_rate("", "a b c d") == 1.0


def test_cost_usd():
    # gpt-6-luna: $0.10/M in, $0.50/M out
    assert cost_usd("gpt-6-luna", 1_000_000, 1_000_000) == pytest.approx(0.60)


class _CountingParser:
    name = "counting"

    def __init__(self):
        self.calls = 0

    def parse(self, pdf: Path) -> ParseResult:
        self.calls += 1
        return ParseResult(parser=self.name, text="hello", pages=1, seconds=0, cost_usd=0.01)


def test_parse_cached_never_reparses(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "CACHE_DIR", tmp_path)
    p = _CountingParser()
    a = parse_cached(p, Path("doc.pdf"), "clean")
    b = parse_cached(p, Path("doc.pdf"), "clean")
    assert p.calls == 1 and a.text == b.text == "hello" and b.cost_usd == 0.01
    parse_cached(p, Path("doc.pdf"), "heavy")  # different condition = different cache key
    assert p.calls == 2


def test_vision_parser_flags_truncated_pages(monkeypatch):
    """A page cut off at max_output_tokens must surface as an error, not as short text."""
    from docintel.parsing import vision_parser

    monkeypatch.setattr(
        vision_parser, "get_settings", lambda: SimpleNamespace(openai_api_key=_Secret())
    )
    vp = vision_parser.VisionParser()
    fake = SimpleNamespace(
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        output_text="partial",
        usage=SimpleNamespace(input_tokens=10, output_tokens=4000),
    )
    vp.client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: fake))
    text, _, _, err = vp._page(b"png")
    assert text == "partial" and "incomplete" in err


class _Secret:
    def get_secret_value(self):
        return "sk-test"
