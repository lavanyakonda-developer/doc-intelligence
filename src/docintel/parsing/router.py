"""Route each PDF to the cheapest parser that can read it (D6).

Usable text layer -> pypdf (free, most faithful). Otherwise -> vision LLM.
"""

from pathlib import Path

from pypdf import PdfReader

MIN_CHARS_PER_PAGE = 200  # a real contract page has ~2-4k chars; scans have ~0


def has_text_layer(pdf: Path, sample_pages: int = 3) -> bool:
    """Check the first few pages: cheap (~ms) and enough to tell digital from scanned.
    Mixed PDFs (digital body + scanned signature pages) pass; handling them per page is a
    possible later improvement."""
    pages = PdfReader(pdf).pages[:sample_pages]
    chars = sum(len((p.extract_text() or "").strip()) for p in pages)
    return bool(pages) and chars / len(pages) >= MIN_CHARS_PER_PAGE


def choose_parser(pdf: Path) -> str:
    return "pypdf" if has_text_layer(pdf) else "vision"
