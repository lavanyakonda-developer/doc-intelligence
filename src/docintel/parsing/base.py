"""Common parser interface + on-disk cache.

Every parser takes a PDF path and returns a ParseResult, so the comparison harness,
the extraction step and the API treat all parsers identically (strategy pattern).
"""

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from docintel.config import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "data" / "parsed"


@dataclass
class ParseResult:
    parser: str
    text: str
    pages: int
    seconds: float
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: list[str] = field(default_factory=list)  # per-page failures, kept not hidden
    cached: bool = False  # True when served from disk


class Parser(Protocol):
    name: str

    def parse(self, pdf: Path) -> ParseResult: ...


def parse_cached(
    parser: Parser, pdf: Path, condition: str, *, refresh: bool = False, key: str | None = None
) -> ParseResult:
    """Parse once, reuse forever. Paid parsers must never be re-billed for an eval re-run.
    Cache key = parser name + condition (clean/light/heavy/upload) + document key
    (the file stem for the corpus; a content hash for uploads, so names can't collide)."""
    path = CACHE_DIR / parser.name / condition / f"{key or pdf.stem}.json"
    if path.exists() and not refresh:
        return ParseResult(**{**json.loads(path.read_text()), "cached": True})
    t0 = time.perf_counter()
    result = parser.parse(pdf)
    result.seconds = round(time.perf_counter() - t0, 2)  # wall-clock, measured the same for all
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), ensure_ascii=False))
    return result
