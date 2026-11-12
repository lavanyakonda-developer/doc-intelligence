"""Evidence check: is a quoted span actually in the source document?

Used in Phase 5 as a cheap hallucination detector. Parsers and LLMs both mangle
whitespace, line breaks, hyphenation and quote styles, so we compare on a normalized form.
"""

import re
import unicodedata

SPAN_SEPARATOR = " … "  # multiple spans joined in one evidence string
_SPLIT = re.compile(re.escape(SPAN_SEPARATOR) + r"|<omitted>")

_TRANSLATE = str.maketrans(
    {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " ", "​": ""}
)


def normalize_for_match(text: str) -> str:
    s = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)  # 'termi-\nnation' -> 'termination'
    s = re.sub(r"\s+", " ", s)  # line breaks, tabs, double spaces -> one space
    return s.strip().lower()


def evidence_found(evidence: str, document: str, *, normalized_doc: str | None = None) -> bool:
    """True if every span in `evidence` appears in `document` after normalization.
    Pass `normalized_doc` when checking many quotes against one document (avoids re-normalizing).
    """
    doc = normalized_doc if normalized_doc is not None else normalize_for_match(document)
    # CUAD marks discontinuous highlights with "<omitted>"; each piece is checked separately.
    spans = [s for s in re.split(_SPLIT, evidence) if s.strip()]
    return bool(spans) and all(normalize_for_match(s) in doc for s in spans)
