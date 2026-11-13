"""The product entry point: one PDF in, one validated ContractResult out.

    route parser (D6) -> parse (cached) -> extract (D7) -> validate -> retry once (D9)

The CLI, the API (Phase 8) and the UI all call `process_pdf`, so they cannot drift apart.
Every stage is cached on disk: re-processing the same file costs $0.
"""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from docintel.extraction.extractor import Extractor, RunConfig
from docintel.parsing.base import parse_cached
from docintel.parsing.pypdf_parser import PypdfParser
from docintel.parsing.router import choose_parser
from docintel.schema.types import ContractRecord
from docintel.validation.pipeline import process

# The shipped configuration, chosen in D6 (routing) and D7 (model + prompt).
MODEL = "gpt-6-luna"
EFFORT = "low"
PROMPT = "extract_v3"
VISION_MODEL = "gpt-6-luna"
MAX_PAGES = 60  # golden set tops out at 60 pages; bounds the cost of one request


class FieldResult(BaseModel):
    status: str  # absent | verified | unverified | failed
    reasons: list[str] = []
    spans: list[tuple[int, int]] = []  # char offsets of the evidence in `text` (UI highlight)


class StageCost(BaseModel):
    parse_usd: float = 0.0
    extract_usd: float = 0.0
    retry_usd: float = 0.0

    @property
    def total(self) -> float:
        return self.parse_usd + self.extract_usd + self.retry_usd


class ContractResult(BaseModel):
    doc_id: str
    filename: str
    status: str  # ok | error
    error: str | None = None
    parser: str | None = None
    pages: int = 0
    run_id: str | None = None
    record: ContractRecord | None = None
    fields: dict[str, FieldResult] = {}
    retried_fields: list[str] = []
    fixed_by_retry: list[str] = []
    cost: StageCost = Field(default_factory=StageCost)
    cost_usd: float = 0.0  # total, as charged when the document was first processed
    seconds: float = 0.0  # wall-clock of THIS call (≈0 when everything is cached)
    processed_at: datetime
    text: str | None = None  # parsed text the offsets refer to (omit to keep responses small)

    @property
    def needs_review(self) -> list[str]:
        return [k for k, f in self.fields.items() if f.status in ("failed", "unverified")]


def content_id(pdf: Path) -> str:
    return hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]


def _parser(name: str):
    if name == "pypdf":
        return PypdfParser()
    from docintel.parsing.vision_parser import VisionParser  # needs an API key: import lazily

    return VisionParser(VISION_MODEL)


def process_pdf(
    pdf: Path,
    *,
    doc_id: str | None = None,
    condition: str = "upload",
    include_text: bool = True,
    retry: bool = True,
) -> ContractResult:
    """`doc_id` defaults to a content hash. The corpus passes its file stem + condition
    'clean' so it reuses the caches the experiments already paid for."""
    t0 = time.perf_counter()
    doc_id = doc_id or content_id(pdf)
    out = ContractResult(
        doc_id=doc_id, filename=pdf.name, status="error", processed_at=datetime.now(UTC)
    )

    def done(error: str | None = None) -> ContractResult:
        out.error = error
        out.status = "error" if error else "ok"
        out.seconds = round(time.perf_counter() - t0, 2)
        out.cost_usd = round(out.cost.total, 6)
        return out

    try:
        name = choose_parser(pdf)
    except Exception as e:  # not a PDF / encrypted / corrupt
        return done(f"unreadable PDF: {type(e).__name__}: {e}")
    parser = _parser(name)
    out.parser = parser.name

    from pypdf import PdfReader

    out.pages = len(PdfReader(pdf).pages)
    if out.pages > MAX_PAGES:
        return done(f"{out.pages} pages exceeds the {MAX_PAGES}-page limit")

    parsed = parse_cached(parser, pdf, condition, key=doc_id)
    out.cost.parse_usd = parsed.cost_usd
    if not parsed.text.strip():
        return done("no text could be read from the document")

    cfg = RunConfig(MODEL, EFFORT, PROMPT, parser.name, condition)
    out.run_id = cfg.run_id
    res = process(Extractor(cfg), doc_id, parsed.text, retry=retry)
    out.cost.extract_usd = res.first.cost_usd
    out.cost.retry_usd = res.retry.cost_usd if res.retry else 0.0
    if res.record is None:
        return done(f"extraction {res.first.status}: {res.first.detail}")

    out.record = res.record
    out.fields = {
        k: FieldResult(status=c.status, reasons=c.reasons, spans=c.spans)
        for k, c in res.checks.items()
    }
    out.retried_fields = list(res.failed_before)
    out.fixed_by_retry = res.fixed_by_retry
    out.text = parsed.text if include_text else None
    return done()
