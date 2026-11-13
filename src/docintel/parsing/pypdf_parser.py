"""Baseline: read the embedded text layer. Free and fast; returns ~nothing for scans."""

from pathlib import Path

from pypdf import PdfReader

from docintel.parsing.base import ParseResult


class PypdfParser:
    name = "pypdf"

    def parse(self, pdf: Path) -> ParseResult:
        reader = PdfReader(pdf)
        pages = [p.extract_text() or "" for p in reader.pages]
        return ParseResult(parser=self.name, text="\n\n".join(pages), pages=len(pages), seconds=0)
