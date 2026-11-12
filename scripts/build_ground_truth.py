"""CUAD labels -> evalsets/ground_truth.jsonl (one validated ContractRecord per golden-set doc).

- Values come from master_clauses.csv '-Answer' columns (lawyer-normalized), run through the
  SAME normalizers we'll apply to LLM output.
- Evidence comes from the span columns (verbatim highlighted text).
- A label that is present but unparseable (e.g. '[]/[]/19[]') is NOT guessed: the field is
  listed in `excluded_fields` and skipped at scoring time for that doc.

Run: uv run python scripts/build_ground_truth.py
"""

import ast
import csv
import json
from pathlib import Path

import duckdb

from docintel.eval.stats import class_balance
from docintel.schema.fields import FIELDS
from docintel.schema.normalize import (
    UnparseableError,
    is_absent,
    normalize_doc_name,
    parse_bool,
    parse_date,
    parse_duration,
    parse_jurisdiction,
    split_parties,
)
from docintel.schema.types import ContractRecord, Extracted, PartialDate

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "raw" / "CUAD_v1" / "master_clauses.csv"
GOLDEN = ROOT / "evalsets" / "golden_set.csv"
OUT = ROOT / "evalsets" / "ground_truth.jsonl"
OVERRIDES = ROOT / "evalsets" / "gt_overrides.json"  # documented CUAD label corrections

PARSERS = {
    "text": lambda raw, spans: raw if normalize_doc_name(raw) else None,
    "entity_list": lambda raw, spans: split_parties(raw),
    "date": lambda raw, spans: parse_date(raw),
    "duration": lambda raw, spans: parse_duration(raw),
    "enum": lambda raw, spans: parse_jurisdiction(raw),
    "boolean": lambda raw, spans: parse_bool(raw),
    "clause": lambda raw, spans: spans or None,  # value = the highlighted clause texts
}


def parse_spans(cell: str | None) -> list[str]:
    """Span columns hold a Python-list literal: "['text one', 'text two']"."""
    if is_absent(cell):
        return []
    return [s.strip() for s in ast.literal_eval(cell) if s.strip()]


def is_derived(value, spans: list[str]) -> bool:
    """A date whose year isn't written in the evidence was computed by the annotator
    (e.g. 'five (5) years from the Effective Date' -> 11/12/24)."""
    if not isinstance(value, PartialDate):
        return False
    text = " ".join(spans)
    return str(value.year) not in text and f"/{str(value.year)[2:]}" not in text


def main() -> None:
    with open(GOLDEN) as f:
        golden = {r["label_filename"]: r for r in csv.DictReader(f)}
    overrides = {(o["doc_id"], o["field"]): o for o in json.loads(OVERRIDES.read_text())}
    unknown = {d for d, _ in overrides} - {g["file"] for g in golden.values()}
    if unknown:  # fail loudly: a typo'd override would otherwise silently do nothing
        raise SystemExit(f"overrides reference unknown docs: {unknown}")
    rows = duckdb.sql(f"SELECT * FROM read_csv_auto('{MASTER}', all_varchar=true)").fetchall()
    cols = [
        c[0] for c in duckdb.sql(f"DESCRIBE SELECT * FROM read_csv_auto('{MASTER}')").fetchall()
    ]

    out = []
    for row in rows:
        r = dict(zip(cols, row, strict=True))
        g = golden.get(r["Filename"])
        if g is None:
            continue
        fields, excluded, derived = {}, [], []
        for spec in FIELDS:
            spans = parse_spans(r[spec.cuad])
            raw = r[spec.answer_col]
            if o := overrides.get((g["file"], spec.name)):
                assert raw == o["cuad_value"], f"override stale for {spec.name}: {raw!r}"
                print(
                    f"  override {spec.name} for {g['file'][:40]}: {raw} -> {o['corrected_value']}"
                )
                raw = o["corrected_value"]
            try:
                value = PARSERS[spec.type](raw, spans)
            except UnparseableError as e:
                print(f"  excluded {spec.name} for {g['file'][:40]}: {e}")
                excluded.append(spec.name)
                value = None
            if spec.type == "date" and is_derived(value, spans):
                derived.append(spec.name)
            fields[spec.name] = Extracted(value=value, evidence=" … ".join(spans) or None)
        record = ContractRecord(doc_id=g["file"], **fields)  # validates every type
        out.append(
            {
                "doc_id": g["file"],
                "split": g["split"],
                "excluded_fields": excluded,
                "derived_fields": derived,
                "record": record.model_dump(mode="json"),
            }
        )

    assert len(out) == len(golden), f"matched {len(out)}/{len(golden)} golden docs"
    out.sort(key=lambda x: (x["split"], x["doc_id"]))
    with open(OUT, "w") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(out)} records")
    dev, test = class_balance(out, "dev"), class_balance(out, "test")
    print(f"{'field':38s} {'type':12s} dev pos/neg   test pos/neg   excluded")
    for spec in FIELDS:
        d, t = dev[spec.name], test[spec.name]
        exc = d.get("excluded", 0) + t.get("excluded", 0)
        print(
            f"{spec.name:38s} {spec.type:12s} {d.get('pos', 0):3d}/{d.get('neg', 0):<3d}"
            f"        {t.get('pos', 0):3d}/{t.get('neg', 0):<3d}         {exc}"
        )


if __name__ == "__main__":
    main()
