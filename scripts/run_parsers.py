"""Parser comparison: parsers x conditions on the degraded subset (+ pypdf on all 30 clean docs).

Results are cached in data/parsed/, so re-runs are free. Metrics -> data/results/parsers.csv.
  uv run python scripts/run_parsers.py                         # everything
  uv run python scripts/run_parsers.py --parsers pypdf docling # skip the paid parser
"""

import argparse
import csv
from pathlib import Path

from docintel.config import PROJECT_ROOT
from docintel.corpus import CONDITIONS, find_pdf, golden_set, ground_truth, reference_text
from docintel.parsing.base import parse_cached
from docintel.parsing.metrics import evidence_recall, word_error_rate

OUT = PROJECT_ROOT / "data" / "results" / "parsers.csv"


def make_parser(name: str):
    if name == "pypdf":
        from docintel.parsing.pypdf_parser import PypdfParser

        return PypdfParser()
    if name == "docling":
        from docintel.parsing.docling_parser import DoclingParser

        return DoclingParser()
    if name == "vision":
        from docintel.parsing.vision_parser import VisionParser

        return VisionParser("gpt-6-luna")
    raise ValueError(name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsers", nargs="+", default=["pypdf", "docling", "vision"])
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    args = ap.parse_args()

    golden, gt = golden_set(), ground_truth()
    subset = [d["file"] for d in golden if d["degraded"] == "True"]
    rows = []
    for pname in args.parsers:
        parser = make_parser(pname)
        for cond in args.conditions:
            # pypdf on clean = the default Phase 4 input, so parse all 30 docs there.
            docs = [d["file"] for d in golden] if (pname, cond) == ("pypdf", "clean") else subset
            for doc_id in docs:
                r = parse_cached(parser, find_pdf(doc_id, cond), cond)
                ev = evidence_recall(r.text, gt[doc_id])
                rows.append(
                    {
                        "parser": r.parser,
                        "condition": cond,
                        "doc_id": doc_id,
                        "in_subset": doc_id in subset,
                        "pages": r.pages,
                        "seconds": r.seconds,
                        "cost_usd": r.cost_usd,
                        "input_tokens": r.input_tokens,
                        "output_tokens": r.output_tokens,
                        "chars": len(r.text),
                        "errors": len(r.errors),
                        "spans": ev["spans"],
                        "exact": ev["exact"],
                        "fuzzy": ev["fuzzy"],
                        "wer": round(word_error_rate(r.text, reference_text(doc_id)), 4),
                    }
                )
                print(
                    f"{r.parser:18s} {cond:6s} {r.pages:3d}p {r.seconds:6.1f}s ${r.cost_usd:.4f} "
                    f"ev {ev['exact']}/{ev['fuzzy']}/{ev['spans']} wer {rows[-1]['wer']:.3f} "
                    f"err {len(r.errors)}  {doc_id[:35]}"
                )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if OUT.exists():  # merge: keep rows for parsers/conditions not re-run this time
        with open(OUT) as f:
            done = {(r["parser"], r["condition"]) for r in rows}
            existing = [r for r in csv.DictReader(f) if (r["parser"], r["condition"]) not in done]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(existing + rows)
    print(f"\nwrote {Path(OUT).relative_to(PROJECT_ROOT)} ({len(existing) + len(rows)} rows)")


if __name__ == "__main__":
    main()
