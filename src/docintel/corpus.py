"""One place that knows where CUAD files and our eval sets live (no hand-built paths elsewhere)."""

import csv
import json
from functools import cache
from pathlib import Path

from docintel.config import PROJECT_ROOT

CUAD = PROJECT_ROOT / "data" / "raw" / "CUAD_v1"
DEGRADED = PROJECT_ROOT / "data" / "degraded"
EVALSETS = PROJECT_ROOT / "evalsets"
CONDITIONS = ("clean", "light", "heavy")


@cache
def _pdf_index() -> dict[str, Path]:
    # CUAD mixes '.pdf' (199) and '.PDF' (311) extensions, so index by stem.
    return {
        p.stem: p for p in (CUAD / "full_contract_pdf").rglob("*") if p.suffix.lower() == ".pdf"
    }


def find_pdf(doc_id: str, condition: str = "clean") -> Path:
    if condition == "clean":
        return _pdf_index()[doc_id]
    path = DEGRADED / condition / f"{doc_id}.pdf"
    if not path.exists():
        raise FileNotFoundError(f"{path} (run `make degrade`)")
    return path


def reference_text(doc_id: str) -> str:
    return (CUAD / "full_contract_txt" / f"{doc_id}.txt").read_text(errors="ignore")


def golden_set() -> list[dict]:
    with open(EVALSETS / "golden_set.csv") as f:
        return list(csv.DictReader(f))


def ground_truth() -> dict[str, dict]:
    lines = (EVALSETS / "ground_truth.jsonl").read_text().splitlines()
    return {(item := json.loads(line))["doc_id"]: item for line in lines}
