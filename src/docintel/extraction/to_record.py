"""LLM output -> ContractRecord, through the same normalizers used for ground truth.

A field that can't be normalized becomes value=None and is reported in `errors`
(Phase 5 turns these into retry-with-feedback; Phase 6 counts them).
"""

from docintel.extraction.llm_schema import LLMExtraction
from docintel.schema.normalize import (
    UnparseableError,
    parse_date,
    parse_jurisdiction,
    resolve_relative_date,
)
from docintel.schema.types import ContractRecord, Duration, Extracted, PartialDate


def _term(t) -> Duration:
    return Duration(value=t.value, unit=t.unit)


def to_record(doc_id: str, out: LLMExtraction) -> tuple[ContractRecord, list[str]]:
    errors: list[str] = []
    f: dict[str, Extracted] = {}

    def put(name: str, evidence: str | None, compute):
        try:
            f[name] = Extracted(value=compute(), evidence=evidence)
        except (UnparseableError, ValueError) as e:
            errors.append(f"{name}: {e}")
            f[name] = Extracted(value=None, evidence=evidence)

    put("document_name", out.document_name.evidence, lambda: out.document_name.value or None)
    put("parties", out.parties.evidence, lambda: out.parties.value or None)
    put("agreement_date", out.agreement_date.evidence, lambda: parse_date(out.agreement_date.value))
    put("effective_date", out.effective_date.evidence, lambda: parse_date(out.effective_date.value))

    def expiration():
        e = out.expiration_date
        if e.kind == "absent":
            return None
        if e.kind == "perpetual":
            return "perpetual"
        if e.kind == "date":
            return parse_date(e.date)
        # relative: our code does the arithmetic (D5.2), never the model
        anchor = f[e.anchor or "effective_date"].value or f["agreement_date"].value
        if e.term is None or not isinstance(anchor, PartialDate):
            raise UnparseableError(f"relative expiration without term/anchor: {e}")
        return resolve_relative_date(anchor, _term(e.term))

    put("expiration_date", out.expiration_date.evidence, expiration)

    for name in ("renewal_term", "notice_period_to_terminate_renewal"):
        d = getattr(out, name)

        def duration(d=d, name=name):
            if d.kind == "absent":
                return None
            if d.kind == "perpetual":
                if name == "notice_period_to_terminate_renewal":
                    raise UnparseableError("notice period cannot be perpetual")
                return "perpetual"
            if d.term is None:
                raise UnparseableError(f"kind=duration without term: {d}")
            return _term(d.term)

        put(name, d.evidence, duration)

    put(
        "governing_law",
        out.governing_law.evidence,
        lambda: parse_jurisdiction(out.governing_law.value),
    )
    for name in (
        "non_compete",
        "exclusivity",
        "uncapped_liability",
        "termination_for_convenience",
        "change_of_control",
    ):
        b = getattr(out, name)
        put(name, b.evidence, lambda b=b: b.present)

    quotes = [q for q in out.cap_on_liability.quotes if q.strip()]
    put("cap_on_liability", " … ".join(quotes) or None, lambda: quotes or None)

    return ContractRecord(doc_id=doc_id, **f), errors
