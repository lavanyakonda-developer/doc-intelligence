"""Shapes of the static demo files (web/public/data/). The TypeScript types the UI uses are
generated from these models (scripts/export_schema.py), so UI and pipeline can't drift."""

from typing import Literal

from pydantic import BaseModel

from docintel.pipeline import ContractResult


class FieldTruth(BaseModel):
    gold: object | None  # CUAD label, normalized like the prediction
    outcome: Literal["correct", "partial", "wrong", "excluded"]


class DemoContract(BaseModel):
    """contracts/<key>.json"""

    result: ContractResult
    truth: dict[str, FieldTruth]


class IndexItem(BaseModel):
    """One entry of index.json"""

    key: str
    doc_id: str
    document_name: str | None
    parties: list[str]
    contract_type: str
    pages: int
    split: Literal["dev", "test"]
    parser: str
    cost_usd: float
    verified: int
    unverified: int
    failed: int
    correct: int
    scored: int


class DemoIndex(BaseModel):
    contracts: list[IndexItem]
