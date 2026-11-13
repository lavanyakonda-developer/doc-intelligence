"""Field-level validation of an extracted ContractRecord against the parsed document.

Four layers, all deterministic (no LLM calls):
  1. format       - conversion errors from to_record (unparseable values)
  2. grounding    - the evidence quote exists in the parsed text (exact, else fuzzy >= 90)
  3. consistency  - the value follows from its own quote (date / number / jurisdiction in it)
  4. cross-field  - expiration after start dates, notice period implies renewal, >= 2 parties

Per field status:
  absent      nothing extracted (nothing to validate)
  verified    grounded and consistent
  unverified  can't be checked (e.g. a date defined by an event, no quote given)
  failed      a check failed -> retry with feedback, then abstain
Limitation: a correctly quoted *wrong* clause passes every check. Evals catch that, not this.
"""

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from docintel.eval.match import dates_equal
from docintel.schema.evidence import NormalizedDoc, normalize_for_match
from docintel.schema.fields import FIELDS
from docintel.schema.normalize import parse_jurisdiction
from docintel.schema.types import ContractRecord, Duration, Jurisdiction, PartialDate
from docintel.validation.text_values import dates_in_text, numbers_in_text

Status = str  # "absent" | "verified" | "unverified" | "failed"


@dataclass
class FieldCheck:
    status: Status
    reasons: list[str] = field(default_factory=list)
    spans: list[tuple[int, int]] = field(default_factory=list)  # evidence offsets in parsed text
    grounding: str | None = None  # "exact" | "fuzzy" | None


def _present(v) -> bool:
    return v not in (None, False, [], "")


def _consistent(name: str, ftype: str, value, evidence: str) -> tuple[bool | None, str]:
    """True = value follows from quote; False = contradicts it; None = can't tell."""
    if ftype == "date" and isinstance(value, PartialDate):
        found = dates_in_text(evidence)
        if not found:
            # Relative expirations are computed by our code from a term, so the quote holds
            # the term, not the date: check the term's number instead (handled by caller).
            return None, "no explicit date in quote"
        if any(dates_equal(value, d) or dates_equal(d, value) for d in found):
            return True, ""
        return False, f"value {value} not among dates in its quote {sorted(map(str, found))}"
    if ftype == "duration" and isinstance(value, Duration):
        if value.value in numbers_in_text(evidence):
            return True, ""
        unit_word = {"business_day": "business day", "day": "day", "week": "week",
                     "month": "month", "year": "year"}[value.unit]  # fmt: skip
        if value.value == 1 and (unit_word in evidence.lower() or "annual" in evidence.lower()):
            return True, ""  # "renew for another year", "annually"
        return False, f"term {value.value} {value.unit} not stated in its quote"
    if ftype == "enum" and isinstance(value, Jurisdiction):
        j = parse_jurisdiction(evidence)
        if value.country == "OTHER" or j is None or j.country == "OTHER":
            return None, "non-standard jurisdiction"
        if j.key() == value.key():
            return True, ""
        return False, f"quote names {j.key()}, value is {value.key()}"
    return None, ""


def validate(record: ContractRecord, text: str, conversion_errors: list[str] = ()) -> dict:
    doc = NormalizedDoc(text)
    checks: dict[str, FieldCheck] = {}
    conv = {e.split(":", 1)[0]: e.split(":", 1)[1].strip() for e in conversion_errors}

    for spec in FIELDS:
        f = getattr(record, spec.name)
        v, ev = f.value, f.evidence
        if spec.name in conv:  # layer 1: present in model output but not normalizable
            checks[spec.name] = FieldCheck("failed", [f"unparseable: {conv[spec.name]}"])
            continue
        if not _present(v):
            checks[spec.name] = FieldCheck("absent")
            continue
        c = FieldCheck("verified")

        # layer 2: grounding of the quote. Parties are checked name by name below; their
        # quote is usually stitched from the preamble and signature block, so it isn't required.
        if ev and spec.type == "entity_list":
            located = doc.locate_all(ev)
            if located:
                c.spans = [(x.start, x.end) for x in located]
        elif ev:
            located = doc.locate_all(ev)
            if located is None:
                c.status = "failed"
                c.reasons.append("evidence quote not found in document")
            else:
                c.spans = [(x.start, x.end) for x in located]
                methods = {x.method for x in located}
                c.grounding = "exact" if methods == {"exact"} else "fuzzy"
        elif spec.type == "boolean":
            c.status = "failed"
            c.reasons.append("present=true without a supporting quote")
        else:
            c.status = "unverified"
            c.reasons.append("no evidence quote")

        # layer 3: value <-> its own quote
        if ev and c.status != "failed" and spec.type != "entity_list":
            if spec.name == "expiration_date" and isinstance(v, PartialDate):
                ok, why = _consistent(spec.name, "date", v, ev)
                if ok is None and numbers_in_text(ev):  # relative term: our code did the math
                    ok, why = True, ""
            else:
                ok, why = _consistent(spec.name, spec.type, v, ev)
            if ok is False:
                c.status = "failed"
                c.reasons.append(why)
            elif ok is None and why and c.status == "verified":
                c.status = "unverified"
                c.reasons.append(why)

        # values that must themselves appear in the document
        if spec.type == "entity_list":
            missing = [p for p in v if fuzz.partial_ratio(normalize_for_match(p), doc.norm) < 90]
            if missing:
                c.status = "failed"
                c.reasons.append(f"parties not found in document: {missing}")
        if spec.type == "text" and fuzz.partial_ratio(normalize_for_match(v), doc.norm) < 90:
            c.status = "failed"
            c.reasons.append("document name not found in document")
        checks[spec.name] = c

    # layer 4: cross-field
    exp = record.expiration_date.value
    for start in ("effective_date", "agreement_date"):
        s = getattr(record, start).value
        if isinstance(exp, PartialDate) and isinstance(s, PartialDate):
            if (exp.year, exp.month or 0, exp.day or 0) < (s.year, s.month or 0, s.day or 0):
                checks["expiration_date"].status = "failed"
                checks["expiration_date"].reasons.append(f"expires {exp} before {start} {s}")
    if _present(record.notice_period_to_terminate_renewal.value) and not _present(
        record.renewal_term.value
    ):
        c = checks["notice_period_to_terminate_renewal"]
        if c.status == "verified":
            c.status = "unverified"
        c.reasons.append("notice period to terminate renewal, but no renewal term extracted")
    parties = record.parties.value or []
    if 0 < len(parties) < 2 and checks["parties"].status == "verified":
        checks["parties"].status = "unverified"
        checks["parties"].reasons.append("fewer than 2 parties")
    return checks


def failed_fields(checks: dict[str, FieldCheck]) -> dict[str, list[str]]:
    return {k: c.reasons for k, c in checks.items() if c.status == "failed"}
