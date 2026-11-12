"""The committed ground truth must always validate against the current schema."""

import json
from pathlib import Path

from docintel.schema.fields import FIELDS_BY_NAME
from docintel.schema.types import ContractRecord

GT = Path(__file__).resolve().parents[1] / "evalsets" / "ground_truth.jsonl"


def _load() -> list[dict]:
    return [json.loads(line) for line in GT.read_text().splitlines()]


def test_every_record_validates():
    items = _load()
    assert len(items) == 30
    for item in items:
        ContractRecord.model_validate(item["record"])


def test_split_sizes():
    splits = [i["split"] for i in _load()]
    assert splits.count("dev") == 8 and splits.count("test") == 22


def test_excluded_and_derived_reference_real_fields():
    for item in _load():
        for f in item["excluded_fields"] + item["derived_fields"]:
            assert f in FIELDS_BY_NAME
