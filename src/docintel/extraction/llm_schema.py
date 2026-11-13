"""LLM-facing output schema (layer 1 of D4). Converted to ContractRecord by to_record.py.

Design rules:
- Strict-mode compatible: every field required; "optional" = `X | None` (union with null).
- `evidence` is declared BEFORE the value in every field. Structured Outputs emits keys in
  schema order, so the model commits to a quote, then answers from it.
- Simple types the model handles well (date strings, raw jurisdiction text); all
  canonicalization happens in our tested normalizers, never in the model.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "llm-v1"

DateStr = Annotated[str, Field(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")]
Unit = Literal["day", "business_day", "week", "month", "year"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # -> additionalProperties: false


class Term(_Strict):
    value: int
    unit: Unit


class TextOut(_Strict):
    evidence: str | None
    value: str | None


class PartiesOut(_Strict):
    evidence: str | None
    value: list[str]


class DateOut(_Strict):
    evidence: str | None
    value: DateStr | None


class ExpirationOut(_Strict):
    evidence: str | None
    kind: Literal["date", "relative", "perpetual", "absent"]
    date: DateStr | None
    term: Term | None
    anchor: Literal["effective_date", "agreement_date"] | None


class DurationOut(_Strict):
    evidence: str | None
    kind: Literal["duration", "perpetual", "absent"]
    term: Term | None


class BoolOut(_Strict):
    evidence: str | None
    present: bool


class ClauseOut(_Strict):
    quotes: list[str]  # the quotes ARE the value for clause fields


class LLMExtraction(_Strict):
    document_name: TextOut
    parties: PartiesOut
    agreement_date: DateOut
    effective_date: DateOut
    expiration_date: ExpirationOut
    renewal_term: DurationOut
    notice_period_to_terminate_renewal: DurationOut
    governing_law: TextOut
    non_compete: BoolOut
    exclusivity: BoolOut
    uncapped_liability: BoolOut
    termination_for_convenience: BoolOut
    change_of_control: BoolOut
    cap_on_liability: ClauseOut
