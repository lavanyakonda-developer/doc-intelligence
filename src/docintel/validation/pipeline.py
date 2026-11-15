"""extract -> validate -> (retry failing fields once) -> validate -> final record + statuses."""

from dataclasses import dataclass, field

from docintel.extraction.extractor import ExtractionResult, Extractor
from docintel.extraction.llm_schema import LLMExtraction
from docintel.extraction.to_record import to_record
from docintel.schema.types import ContractRecord
from docintel.tracing import mark_error, set_attrs, stage
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


def _llm_attrs(span, r: ExtractionResult) -> None:
    set_attrs(
        span, status=r.status, cache_hit=r.cached, cost_usd=r.cost_usd,
        input_tokens=r.input_tokens, cached_input_tokens=r.cached_tokens,
        output_tokens=r.output_tokens, reasoning_tokens=r.reasoning_tokens,
        llm_seconds=r.seconds, detail=r.detail,
    )  # fmt: skip
    if r.status != "ok":
        mark_error(span, f"extraction {r.status}")


def _check_attrs(span, checks: dict[str, FieldCheck]) -> None:
    statuses = [c.status for c in checks.values()]
    failed = failed_fields(checks)
    set_attrs(
        span,
        **{f"fields.{s}": statuses.count(s) for s in ("verified", "unverified", "failed")},
        failed_fields=sorted(failed),
        failed_reasons=[f"{k}: {'; '.join(v)}" for k, v in failed.items()],
        unverified_fields=sorted(k for k, c in checks.items() if c.status == "unverified"),
    )


def process(ex: Extractor, doc_id: str, text: str, *, retry: bool = True) -> DocResult:
    with stage("extract", "CHAIN", run_id=ex.cfg.run_id, model=ex.cfg.model,
               prompt=ex.cfg.prompt, prompt_hash=ex.cfg.prompt_hash) as span:  # fmt: skip
        first = ex.extract(doc_id, text)
        _llm_attrs(span, first)
    if first.status != "ok":
        return DocResult(doc_id, None, {}, first)
    with stage("validate", "GUARDRAIL") as span:
        record = ContractRecord.model_validate(first.record)
        checks = validate(record, text, first.conversion_errors)
        failed = failed_fields(checks)
        _check_attrs(span, checks)
    result = DocResult(doc_id, record, checks, first, failed_before=failed)
    if not (retry and failed):
        return result

    with stage("retry", "CHAIN", fields=sorted(failed)) as span:
        second = ex.retry(doc_id, text, first.raw, failed)
        result.retry = second
        _llm_attrs(span, second)
        if second.status != "ok":
            return result
        # Merge: take ONLY the previously-failing fields from the retry, so fields that
        # already passed can't regress. Then re-normalize and re-validate the merged output.
        merged = {**first.raw, **{k: second.raw[k] for k in failed}}
        record2, errors2 = to_record(doc_id, LLMExtraction.model_validate(merged))
        checks2 = validate(record2, text, errors2)
        result.record, result.checks = record2, checks2
        result.fixed_by_retry = [k for k in failed if checks2[k].status != "failed"]
        set_attrs(span, fixed=result.fixed_by_retry)
    return result
