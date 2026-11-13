"""Model-independent ground-truth audit: does each label agree with CUAD's own evidence span?

Flags (never auto-fixes) cases where the highlighted span explicitly contradicts the
normalized answer, or a span exists but the answer is empty. Uses ONLY ground truth and
CUAD text, never model outputs, so corrections can't be biased toward the model.

Policy (D8): a flag becomes an override in evalsets/gt_overrides.json only if the span
states the value explicitly and unambiguously. Interpretation calls stay as labelled.

Run: uv run python scripts/audit_ground_truth.py
"""

from docintel.corpus import ground_truth
from docintel.schema.normalize import parse_jurisdiction
from docintel.schema.types import PartialDate
from docintel.validation.text_values import dates_in_text


def main() -> None:
    flags = 0
    for doc_id, item in ground_truth().items():
        r = item["record"]
        for name, f in r.items():
            if name == "doc_id" or name in item["excluded_fields"]:
                continue
            v, ev = f["value"], f["evidence"] or ""
            msg = None
            if ev and v is None and name not in ("cap_on_liability",):
                msg = "span highlighted but answer is empty"
            elif name.endswith("_date") and isinstance(v, dict) and ev:
                label = PartialDate(**v)
                stated = {d for d in dates_in_text(ev) if d.day is not None}
                if name == "expiration_date":  # span often also states the start date
                    starts = {
                        PartialDate(**r[k]["value"])
                        for k in ("effective_date", "agreement_date")
                        if isinstance(r[k]["value"], dict)
                    }
                    stated -= starts
                if stated and label not in stated and len(stated) == 1:
                    msg = f"span states {stated.pop()} but label is {label}"
            elif name == "governing_law" and isinstance(v, dict) and ev:
                j = parse_jurisdiction(ev)
                if j.country != "OTHER" and (j.country, j.region) != (v["country"], v["region"]):
                    msg = f"span parses as {j.key()} but label is {(v['country'], v['region'])}"
            if msg:
                flags += 1
                print(f"[{item['split']}] {name:24s} {doc_id[:40]:40s} {msg}")
                print(f"      span: {ev[:200]!r}")
    print(f"\n{flags} flags")


if __name__ == "__main__":
    main()
