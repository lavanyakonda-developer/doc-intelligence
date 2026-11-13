"""extract -> validate -> (retry failing fields once) -> validate -> final record + statuses."""

from dataclasses import dataclass, field

from docintel.extraction.extractor import ExtractionResult, Extractor
from docintel.extraction.llm_schema import LLMExtraction
from docintel.extraction.to_record import to_record
from docintel.schema.types import ContractRecord
from docintel.validation.validate import FieldCheck, failed_fields, validate


@dataclass
class DocResult:
    doc_id: str
    record: ContractRecord | None
    checks: dict[str, FieldCheck]
    first: ExtractionResult
    retry: ExtractionResult | None = None
    failed_before: dict[str, list[str]] = field(default_factory=dict)
    fixed_by_retry: list[str] = field(default_factory=list)  # failed before, not failed after

    @property
    def cost_usd(self) -> float:
        return self.first.cost_usd + (self.retry.cost_usd if self.retry else 0)


def process(ex: Extractor, doc_id: str, text: str, *, retry: bool = True) -> DocResult:
    first = ex.extract(doc_id, text)
    if first.status != "ok":
        return DocResult(doc_id, None, {}, first)
    record = ContractRecord.model_validate(first.record)
    checks = validate(record, text, first.conversion_errors)
    failed = failed_fields(checks)
    result = DocResult(doc_id, record, checks, first, failed_before=failed)
    if not (retry and failed):
        return result

    second = ex.retry(doc_id, text, first.raw, failed)
    result.retry = second
    if second.status != "ok":
        return result
    # Merge: take ONLY the previously-failing fields from the retry, so fields that already
    # passed can't regress. Then re-normalize and re-validate the merged output.
    merged = {**first.raw, **{k: second.raw[k] for k in failed}}
    record2, errors2 = to_record(doc_id, LLMExtraction.model_validate(merged))
    checks2 = validate(record2, text, errors2)
    result.record, result.checks = record2, checks2
    result.fixed_by_retry = [k for k in failed if checks2[k].status != "failed"]
    return result
