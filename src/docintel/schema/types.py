"""Domain types: the normalized, validated shape of a contract record.

Both ground truth (from CUAD) and model predictions are converted into ContractRecord,
so evaluation always compares like with like.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Perpetual = Literal["perpetual"]


class PartialDate(BaseModel):
    """A date where month/day may be unknown, e.g. CUAD's '09/[]/2019' -> year=2019, month=9."""

    model_config = ConfigDict(frozen=True)  # immutable + hashable, like a value object

    year: int
    month: int | None = None
    day: int | None = None

    @model_validator(mode="after")
    def _check_ranges(self) -> "PartialDate":
        if not 1900 <= self.year <= 2100:
            raise ValueError(f"implausible year {self.year}")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError(f"bad month {self.month}")
        if self.day is not None and not 1 <= self.day <= 31:
            raise ValueError(f"bad day {self.day}")
        if self.day is not None and self.month is None:
            raise ValueError("day without month")
        return self

    def __str__(self) -> str:
        return "-".join(
            f"{v:02d}" if i else str(v)
            for i, v in enumerate((self.year, self.month, self.day))
            if v is not None
        )


class Duration(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: int
    # business_day is kept distinct: "30 business days" (~6 weeks) is legally different from
    # "30 days", so it never equals a calendar unit.
    unit: Literal["day", "business_day", "week", "month", "year"]

    def in_months(self) -> int | None:
        """Exact for month/year units; None otherwise."""
        return {"month": 1, "year": 12}.get(self.unit, 0) * self.value or None

    def in_days(self) -> int | None:
        """Exact for day/week units; None otherwise."""
        return {"day": 1, "week": 7}.get(self.unit, 0) * self.value or None

    def approx_days(self) -> float | None:
        """Calendar-average days, only for comparing across unit families."""
        if (m := self.in_months()) is not None:
            return m * 365.25 / 12
        return self.in_days()


class Jurisdiction(BaseModel):
    """Canonical governing law. country='OTHER' for non-standard answers; raw keeps the text."""

    model_config = ConfigDict(frozen=True)

    country: str
    region: str | None = None  # US state / Canadian province
    raw: str | None = None

    def key(self) -> tuple[str, str | None]:
        return (self.country, self.region)


class Extracted[T](BaseModel):
    """Every extracted value travels with its evidence (verbatim quote from the contract).

    value=None means "not present in the contract" (CUAD's definition of absent).
    """

    value: T | None = None
    evidence: str | None = None


class ContractRecord(BaseModel):
    doc_id: str

    document_name: Extracted[str]
    parties: Extracted[list[str]]
    agreement_date: Extracted[PartialDate]
    effective_date: Extracted[PartialDate]
    expiration_date: Extracted[PartialDate | Perpetual]
    renewal_term: Extracted[Duration | Perpetual]
    notice_period_to_terminate_renewal: Extracted[Duration]
    governing_law: Extracted[Jurisdiction]
    non_compete: Extracted[bool]
    exclusivity: Extracted[bool]
    uncapped_liability: Extracted[bool]
    termination_for_convenience: Extracted[bool]
    change_of_control: Extracted[bool]
    cap_on_liability: Extracted[list[str]]  # clause texts; None/[] = no cap clause
