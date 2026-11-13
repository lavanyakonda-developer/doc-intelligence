"""Evidence matching: is a quoted span in the source document, and where?

Parsers and LLMs both mangle whitespace, line breaks, hyphenation and quote styles, so we
compare on a normalized form. `normalize_with_map` also keeps, for every normalized
character, the index of the original character it came from. That lets us report where a
quote sits in the ORIGINAL text (offsets for UI highlighting), not just whether it's there.
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

SPAN_SEPARATOR = " … "  # multiple spans joined in one evidence string
_SPLIT = re.compile(re.escape(SPAN_SEPARATOR) + r"|<omitted>")

_TRANSLATE = str.maketrans(
    {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " ", "​": ""}
)

FUZZY_THRESHOLD = 90  # same threshold as the Phase 3 parser metric


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalize (NFKC, quote/dash folding, line-break de-hyphenation, whitespace collapse,
    lowercase) and return (normalized, idx) where idx[k] = original index of normalized char k."""
    out: list[str] = []
    idx: list[int] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        # 'termi-\n  nation' -> 'termination': hyphen between word chars across a line break
        if c == "-" and out and (out[-1].isalnum() or out[-1] == "_"):
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            if j < n and "\n" in text[i + 1 : j] and (text[j].isalnum() or text[j] == "_"):
                i = j
                continue
        for ch in unicodedata.normalize("NFKC", c).translate(_TRANSLATE).lower():
            if ch.isspace():
                if out and out[-1] != " ":
                    out.append(" ")
                    idx.append(i)
            else:
                out.append(ch)
                idx.append(i)
        i += 1
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize_for_match(text: str) -> str:
    return normalize_with_map(text)[0]


# Model quotes stitched from several places use '...' or '…' even when told not to.
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.+|…)\s*")
_SENTENCE = re.compile(r"(?<=[.;:])\s+")


def split_spans(evidence: str) -> list[str]:
    # CUAD marks discontinuous highlights with "<omitted>"; we join multiple quotes with " … ".
    return [s for s in re.split(_SPLIT, evidence) if s.strip()]


def split_quote_pieces(evidence: str) -> list[str]:
    """For model quotes: also split on ellipses (each piece must be in the document)."""
    pieces = [p for s in split_spans(evidence) for p in _ELLIPSIS.split(s)]
    return [p for p in pieces if len(p.strip()) >= 3]


def evidence_found(evidence: str, document: str, *, normalized_doc: str | None = None) -> bool:
    """True if every span in `evidence` appears exactly (after normalization) in `document`."""
    doc = normalized_doc if normalized_doc is not None else normalize_for_match(document)
    spans = split_spans(evidence)
    return bool(spans) and all(normalize_for_match(s) in doc for s in spans)


@dataclass(frozen=True)
class Located:
    start: int  # offsets into the ORIGINAL text, end exclusive
    end: int
    score: float  # 100 for exact
    method: str  # "exact" | "fuzzy"


class NormalizedDoc:
    """Normalize a document once, then locate many quotes in it."""

    def __init__(self, text: str):
        self.text = text
        self.norm, self.idx = normalize_with_map(text)

    def _orig(self, a: int, b: int) -> tuple[int, int]:
        return self.idx[a], self.idx[b - 1] + 1

    def locate(self, quote: str, threshold: float = FUZZY_THRESHOLD) -> Located | None:
        q = normalize_for_match(quote)
        if not q or not self.norm:
            return None
        k = self.norm.find(q)
        if k >= 0:
            return Located(*self._orig(k, k + len(q)), 100.0, "exact")
        al = fuzz.partial_ratio_alignment(q, self.norm, score_cutoff=threshold)
        if al is None or al.dest_end <= al.dest_start:
            return None
        return Located(*self._orig(al.dest_start, al.dest_end), al.score, "fuzzy")

    def locate_long(self, piece: str, threshold: float = FUZZY_THRESHOLD) -> Located | None:
        """Long quotes often cross a page break (page number / header inside the clause in the
        parsed text), which drags whole-quote fuzzy scores below threshold. If the whole piece
        fails, accept it when every sentence (>= 30 chars) locates individually."""
        loc = self.locate(piece, threshold)
        if loc or len(piece) < 150:
            return loc
        sents = [x for x in _SENTENCE.split(piece) if len(x) >= 30]
        locs = [self.locate(x, threshold) for x in sents]
        if len(sents) >= 2 and all(locs):
            score = min(x.score for x in locs)
            return Located(min(x.start for x in locs), max(x.end for x in locs), score, "pieces")
        return None

    def locate_all(self, evidence: str, threshold: float = FUZZY_THRESHOLD) -> list[Located] | None:
        """All pieces of a (possibly multi-span / ellipsis-stitched) quote; None if any missing."""
        found = [self.locate_long(s, threshold) for s in split_quote_pieces(evidence)]
        return found if found and all(found) else None
