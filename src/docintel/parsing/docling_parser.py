"""Docling: layout model + RapidOCR, run locally. Outputs Markdown.

RapidOCR (onnxruntime) rather than ocrmac: ocrmac uses Apple's Vision framework, which
only exists on macOS. Results measured with it couldn't be reproduced on Cloud Run (Linux).
"""

from functools import cached_property
from pathlib import Path

from docintel.parsing.base import ParseResult


class DoclingParser:
    name = "docling"

    @cached_property
    def _converter(self):
        # Imported lazily: docling pulls in torch (~seconds to import, GBs on disk). Code paths
        # that never use Docling (tests, the pypdf route) shouldn't pay that cost.
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions(
            do_ocr=True,  # OCR runs on bitmap regions; digital text layers are used as-is
            ocr_options=RapidOcrOptions(lang=["en"]),  # default is ['ch']
            do_table_structure=True,
            # CPU, not 'auto': (1) device=auto picks Apple MPS, whose current torch build calls a
            # Metal API missing on macOS 14.0 -> native NSException crash; (2) Cloud Run has no
            # GPU, so CPU timings are the ones that predict production.
            accelerator_options=AcceleratorOptions(device="cpu", num_threads=8),
        )
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )

    def parse(self, pdf: Path) -> ParseResult:
        result = self._converter.convert(pdf)
        doc = result.document
        errors = [str(e) for e in (result.errors or [])]
        return ParseResult(
            parser=self.name,
            text=doc.export_to_markdown(),
            pages=len(result.pages),
            seconds=0,
            errors=errors,
        )
