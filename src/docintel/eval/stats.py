"""Dataset statistics that must be reported next to every metric."""

from collections import Counter

from docintel.schema.fields import FIELDS


def class_balance(items: list[dict], split: str | None = None) -> dict[str, dict[str, int]]:
    """Per field: positives (value present / True) vs negatives (absent / False).

    For booleans the positive class is True ("a clause of this type exists"). Precision and
    recall are computed on that class, so with 4 positives a single miss moves recall 25
    points. This table is printed beside every P/R figure so readers can judge that.
    """
    out: dict[str, Counter] = {f.name: Counter() for f in FIELDS}
    for item in items:
        if split and item["split"] != split:
            continue
        for f in FIELDS:
            if f.name in item["excluded_fields"]:
                out[f.name]["excluded"] += 1
                continue
            v = item["record"][f.name]["value"]
            out[f.name]["pos" if v not in (None, False, []) else "neg"] += 1
    return {k: dict(v) for k, v in out.items()}
