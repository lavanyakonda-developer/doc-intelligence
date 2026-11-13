from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from docintel import pipeline
from docintel.extraction.to_record import to_record
from docintel.parsing.base import ParseResult
from docintel.pipeline import ContractResult, FieldResult, process_pdf
from docintel.storage.store import DuckDBStore, flatten
from tests.test_extraction import _out


def _result(doc_id="d1", **overrides) -> ContractResult:
    rec, _ = to_record(doc_id, _out(**overrides))
    fields = {
        k: FieldResult(
            status="absent" if getattr(rec, k).value in (None, False, []) else "verified"
        )
        for k in type(rec).model_fields
        if k != "doc_id"
    }
    return ContractResult(
        doc_id=doc_id, filename=f"{doc_id}.pdf", status="ok", parser="pypdf", pages=3,
        record=rec, fields=fields, processed_at=datetime.now(UTC), cost_usd=0.002,
    )  # fmt: skip


# --- store --------------------------------------------------------------------------------


def test_flatten_types_for_analytics():
    row = flatten(_result())
    assert row["agreement_date"] == date(2019, 11, 12)
    assert row["expiration_date"] == date(2024, 11, 12)  # computed from 5-year term
    assert row["renewal_days"] == pytest.approx(365.25)
    assert (row["governing_country"], row["governing_region"]) == ("United States", "New York")
    assert row["termination_for_convenience"] is True and row["exclusivity"] is False


def test_save_is_idempotent_and_roundtrips():
    s = DuckDBStore()
    r = _result()
    s.save(r)
    s.save(r)
    assert s.con.execute("SELECT count(*) FROM contracts").fetchone()[0] == 1
    assert s.con.execute("SELECT count(*) FROM fields").fetchone()[0] == 14
    assert s.get("d1").record == r.record
    assert s.get("missing") is None


def test_failed_results_are_not_stored():
    r = _result()
    r.status, r.error = "error", "boom"
    with pytest.raises(ValueError):
        DuckDBStore().save(r)


def test_queries():
    s = DuckDBStore()
    s.save(_result("a"))
    notice = {"evidence": "90 days notice", "kind": "duration", "term": {"value": 90,
              "unit": "day"}}  # fmt: skip
    s.save(_result("b", notice_period_to_terminate_renewal=notice))
    soon = s.query("expiring_soon", as_of="2024-10-01", days=60)
    assert {r["doc_id"] for r in soon} == {"a", "b"} and soon[0]["days_left"] == 42
    assert s.query("expiring_soon", as_of="2020-01-01", days=60) == []
    (deadline,) = s.query("renewal_notice_deadlines")
    assert deadline["doc_id"] == "b" and deadline["notice_deadline"] == date(2024, 8, 14)
    assert s.query("governing_law_mix")[0]["contracts"] == 2
    with pytest.raises(KeyError):
        s.query("drop_tables")
    with pytest.raises(KeyError):
        s.query("expiring_soon", sql="1; DROP TABLE contracts")


# --- pipeline -----------------------------------------------------------------------------


def test_not_a_pdf_is_an_error_result(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_text("not a pdf")
    r = process_pdf(bad)
    assert r.status == "error" and "unreadable" in r.error


def _blank_pdf(path, pages):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(612, 792)
    w.write(path)
    return path


def test_page_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "choose_parser", lambda pdf: "pypdf")
    r = process_pdf(_blank_pdf(tmp_path / "long.pdf", pipeline.MAX_PAGES + 1))
    assert r.status == "error" and "page limit" in r.error


def test_happy_path_wires_stages(tmp_path, monkeypatch):
    pdf = _blank_pdf(tmp_path / "c.pdf", 2)
    expected = _result("ignored")
    monkeypatch.setattr(pipeline, "choose_parser", lambda pdf: "pypdf")
    monkeypatch.setattr(
        pipeline, "parse_cached",
        lambda parser, pdf, condition, key: ParseResult("pypdf", "contract text", 2, 0.0),
    )  # fmt: skip
    seen = {}

    def fake_process(ex, doc_id, text, retry):
        seen.update(doc_id=doc_id, text=text, run_id=ex.cfg.run_id)
        checks = {k: SimpleNamespace(status=f.status, reasons=[], spans=[(0, 8)])
                  for k, f in expected.fields.items()}  # fmt: skip
        return SimpleNamespace(
            record=expected.record, checks=checks, failed_before={}, fixed_by_retry=[],
            first=SimpleNamespace(cost_usd=0.002, status="ok"), retry=None,
        )  # fmt: skip

    monkeypatch.setattr(pipeline, "process", fake_process)
    r = process_pdf(pdf)
    assert r.status == "ok", r.error
    assert seen["doc_id"] == pipeline.content_id(pdf)  # content hash, not filename
    assert seen["text"] == "contract text"
    assert "extract_v3" in seen["run_id"] and "upload" in seen["run_id"]
    assert r.fields["governing_law"].spans == [(0, 8)]
    assert r.cost_usd == 0.002 and r.text == "contract text"
