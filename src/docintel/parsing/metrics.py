"""Parser quality metrics.

1. Evidence recall (primary): share of CUAD's lawyer-highlighted spans recoverable from the
   parsed text. If a clause isn't in the parse, no extractor can find it.
     - exact: after whitespace/quote normalization (schema.evidence)
     - fuzzy: best local alignment >= FUZZY_THRESHOLD, which tolerates OCR character noise
2. Word error rate vs CUAD's reference .txt (secondary). The reference is itself a machine
   extraction (not a human transcription), so WER is biased toward text-layer parsers.
"""

import re

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from docintel.schema.evidence import _SPLIT, normalize_for_match

FUZZY_THRESHOLD = 90


def _strip_markdown(text: str) -> str:
    # Docling emits Markdown (#, |, **, -); compare words, not formatting.
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    return re.sub(r"[|*_`]+", " ", text)


def _spans(gt_item: dict) -> list[str]:
    out = []
    for name, f in gt_item["record"].items():
        if name != "doc_id" and f["evidence"]:
            out += [s for s in re.split(_SPLIT, f["evidence"]) if len(s.strip()) >= 10]
    return out


def evidence_recall(parsed: str, gt_item: dict) -> dict:
    # Same normalization on BOTH sides: stripping '_'/'*' only from the parse once made blank
    # form lines ('____________') and redactions ('[*]') unmatchable for every parser.
    doc = normalize_for_match(_strip_markdown(parsed))
    spans = [normalize_for_match(_strip_markdown(s)) for s in _spans(gt_item)]
    spans = [s for s in spans if s]  # a span that was only formatting characters carries no text
    exact = sum(s in doc for s in spans)
    # partial_ratio = best alignment of the span against any same-length window of the doc
    fuzzy = sum(s in doc or fuzz.partial_ratio(s, doc) >= FUZZY_THRESHOLD for s in spans)
    return {"spans": len(spans), "exact": exact, "fuzzy": fuzzy}


def word_error_rate(parsed: str, reference: str) -> float:
    hyp = normalize_for_match(_strip_markdown(parsed)).split()
    ref = normalize_for_match(reference).split()
    # Levenshtein over word sequences (substitutions + insertions + deletions) / reference words
    return Levenshtein.distance(ref, hyp) / max(1, len(ref))
