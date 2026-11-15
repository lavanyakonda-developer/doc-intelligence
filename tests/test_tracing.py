"""Spans are emitted with the right tree and attributes, and tracing off costs nothing.

The global tracer provider can only be set once per process, so one in-memory exporter is
installed for this module and cleared between tests.
"""

from types import SimpleNamespace

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from docintel import pipeline
from docintel.parsing.base import ParseResult
from tests.test_pipeline_store import _blank_pdf
from tests.test_validation import DOC, _result

EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def provider():
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(EXPORTER))
    trace.set_tracer_provider(tp)  # docintel.tracing's proxy tracer picks this up
    yield


@pytest.fixture(autouse=True)
def clear():
    EXPORTER.clear()


def _run(tmp_path, monkeypatch, bad_first=False):
    pdf = _blank_pdf(tmp_path / "c.pdf", 2)
    monkeypatch.setattr(pipeline, "choose_parser", lambda pdf: "pypdf")
    monkeypatch.setattr(
        pipeline, "parse_cached",
        lambda parser, pdf, condition, key: ParseResult("pypdf", DOC, 2, 0.0, cached=True),
    )  # fmt: skip
    first = (
        {"governing_law": {"evidence": "laws of the State of Delaware", "value": "Delaware"}}
        if bad_first
        else {}
    )

    class FakeExtractor:
        def __init__(self, cfg):
            self.cfg = cfg

        def extract(self, doc_id, text):
            return _result(first)

        def retry(self, doc_id, text, prev, failures):
            return _result({})

    monkeypatch.setattr(pipeline, "Extractor", FakeExtractor)
    return pipeline.process_pdf(pdf)


def spans():
    return {s.name: s for s in EXPORTER.get_finished_spans()}


def test_span_tree_and_ids(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch)
    s = spans()
    assert set(s) == {"process_pdf", "parse", "extract", "validate"}  # no retry needed
    root = s["process_pdf"]
    assert all(
        s[n].parent.span_id == root.context.span_id for n in ("parse", "extract", "validate")
    )
    # the result points at its own trace: this is what eval annotations attach to
    assert r.trace_id == format(root.context.trace_id, "032x")
    assert r.span_id == format(root.context.span_id, "016x")


def test_attributes(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    s = spans()
    a = s["process_pdf"].attributes
    assert a["openinference.span.kind"] == "CHAIN" and a["docintel.status"] == "ok"
    assert a["docintel.parser"] == "pypdf" and a["docintel.cost_usd"] == pytest.approx(0.001)
    assert s["parse"].attributes["docintel.cache_hit"] is True
    e = s["extract"].attributes
    assert e["docintel.prompt"] == "extract_v3" and len(e["docintel.prompt_hash"]) == 10
    assert s["validate"].attributes["openinference.span.kind"] == "GUARDRAIL"
    assert s["validate"].attributes["docintel.fields.failed"] == 0


def test_failed_validation_shows_reasons_and_retry(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, bad_first=True)
    s = spans()
    v = s["validate"].attributes
    assert v["docintel.failed_fields"] == ("governing_law",)
    assert "not found" in v["docintel.failed_reasons"][0]
    assert s["retry"].attributes["docintel.fixed"] == ("governing_law",)
    assert r.fixed_by_retry == ["governing_law"]


def test_error_status_on_failure(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_text("not a pdf")
    r = pipeline.process_pdf(bad)
    root = spans()["process_pdf"]
    assert r.status == "error" and root.status.status_code.name == "ERROR"


def test_set_attrs_drops_none_and_stringifies():
    from docintel.tracing import set_attrs

    span = SimpleNamespace(attrs={})
    span.set_attribute = lambda k, v: span.attrs.__setitem__(k, v)
    set_attrs(span, a=None, b={"x": 1}, c=[1, {"y": 2}], d=1.5)
    assert span.attrs == {
        "docintel.b": "{'x': 1}",
        "docintel.c": [1, "{'y': 2}"],
        "docintel.d": 1.5,
    }
