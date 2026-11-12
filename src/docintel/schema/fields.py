"""Registry of the 14 evaluated fields: CUAD source columns + field type (drives match rules)."""

from dataclasses import dataclass
from typing import Literal

FieldType = Literal["text", "entity_list", "date", "duration", "enum", "boolean", "clause"]


@dataclass(frozen=True)
class FieldSpec:
    name: str  # attribute on ContractRecord
    cuad: str  # CUAD category (span column in master_clauses.csv)
    answer_col: str  # normalized-answer column
    type: FieldType


def _spec(name: str, cuad: str, type_: FieldType, answer_col: str | None = None) -> FieldSpec:
    return FieldSpec(name, cuad, answer_col or f"{cuad}-Answer", type_)


FIELDS: list[FieldSpec] = [
    _spec("document_name", "Document Name", "text"),
    _spec("parties", "Parties", "entity_list"),
    _spec("agreement_date", "Agreement Date", "date"),
    _spec("effective_date", "Effective Date", "date"),
    _spec("expiration_date", "Expiration Date", "date"),
    _spec("renewal_term", "Renewal Term", "duration"),
    # CUAD typo: this one column has a space before 'Answer'.
    _spec(
        "notice_period_to_terminate_renewal",
        "Notice Period To Terminate Renewal",
        "duration",
        answer_col="Notice Period To Terminate Renewal- Answer",
    ),
    _spec("governing_law", "Governing Law", "enum"),
    _spec("non_compete", "Non-Compete", "boolean"),
    _spec("exclusivity", "Exclusivity", "boolean"),
    _spec("uncapped_liability", "Uncapped Liability", "boolean"),
    _spec("termination_for_convenience", "Termination For Convenience", "boolean"),
    _spec("change_of_control", "Change Of Control", "boolean"),
    _spec("cap_on_liability", "Cap On Liability", "clause"),
]
FIELDS_BY_NAME = {f.name: f for f in FIELDS}
