"""Phase 6 eval report: rebuild DuckDB from cached runs, then write every table to RESULTS.md.

uv run python scripts/eval_report.py            # $0, everything is cached
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

from docintel.eval.db import build
from docintel.eval.match import CLAUSE_F1_THRESHOLD, PARTY_THRESHOLD, match
from docintel.eval.metrics import (
    bootstrap_f1,
    counts_by,
    doc_counts,
    list_field_macro,
    paired_bootstrap,
    prf,
    total,
)
from docintel.schema.fields import FIELDS
from docintel.schema.normalize import normalize_doc_name

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "RESULTS.md"
PRODUCTION = "6-luna-low-extract_v3-pypdf-clean-r0"  # the shipped config (D6, D7)


def pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}"


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def run_id(con, prefix: str) -> str:
    hits = [r for (r,) in con.execute("SELECT run_id FROM runs").fetchall() if r.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return hits[0]


def headline(con) -> str:
    rows = []
    runs = con.execute(
        """SELECT r.run_id, model, prompt, replicate, cost_usd / n_docs
           FROM runs r WHERE parser = 'pypdf' AND n_docs = 30 ORDER BY run_id"""
    ).fetchall()
    for rid, model, prompt, rep, cost in runs:
        c = doc_counts(con, rid, split="test")
        p, r, _ = prf(*total(c))
        e = bootstrap_f1(c)
        macro = list_field_macro(con, rid, "parties", split="test")
        rows.append([model, prompt, f"r{rep}", pct(p), pct(r), e.fmt(), pct(macro), f"${cost:.4f}"])
    return table(
        ["model", "prompt", "replicate", "P", "R", "micro F1 [95% CI]", "parties doc-macro F1",
         "$/doc"],
        rows,
    )  # fmt: skip


def paired(con) -> str:
    base = doc_counts(con, run_id(con, PRODUCTION), split="test")
    rows = []
    for label, prefix in [
        ("luna r1 vs r0 (noise)", "6-luna-low-extract_v3-pypdf-clean-r1"),
        ("luna r2 vs r0 (noise)", "6-luna-low-extract_v3-pypdf-clean-r2"),
        ("terra (10x cost) vs luna", "6.1-terra-low-extract_v3-pypdf-clean-r0"),
    ]:
        pb = paired_bootstrap(base, doc_counts(con, run_id(con, prefix), split="test"))
        rows.append(
            [label, f"{100 * pb.diff:+.1f}", f"[{100 * pb.lo:+.1f}, {100 * pb.hi:+.1f}]",
             f"{pb.p_not_better:.2f}"]
        )  # fmt: skip
    return table(["comparison", "ΔF1", "95% CI", "P(not better)"], rows)


def per_field(con) -> str:
    rid = run_id(con, PRODUCTION)
    groups = counts_by(con, rid, "field", split="test")
    rows = []
    for f in FIELDS:
        c = groups.get(f.name, {})
        p, r, f1 = prf(*total(c))
        macro = (
            list_field_macro(con, rid, f.name, split="test") if f.type == "entity_list" else None
        )
        tp, fp, fn = total(c)
        rows.append([f.name, f.type, pct(p), pct(r), pct(f1), pct(macro), tp, fp, fn])
    return table(["field", "type", "P", "R", "micro F1", "doc-macro F1", "tp", "fp", "fn"], rows)


def breakdown(con, column: str, label: str, *, where_split: str | None = "test") -> str:
    rid = run_id(con, PRODUCTION)
    rows = []
    for g, c in sorted(counts_by(con, rid, column, split=where_split).items()):
        tp, fp, fn = total(c)
        if tp + fp + fn == 0:
            continue
        e = bootstrap_f1(c)
        ci = e.fmt() if e.n_docs >= 5 else f"{100 * e.value:.1f} (too few docs for a CI)"
        rows.append([g, e.n_docs, tp + fp + fn, pct(prf(tp, fp, fn)[0]), pct(prf(tp, fp, fn)[1]),
                     ci])  # fmt: skip
    return table([label, "docs", "scored items", "P", "R", "F1 [95% CI]"], rows)


def by_parser(con) -> str:
    docs = [d for (d,) in con.execute("SELECT doc_id FROM docs WHERE degraded").fetchall()]
    base = {d: c for d, c in doc_counts(con, run_id(con, PRODUCTION)).items() if d in docs}
    rows = []
    for rid, parser, cond in con.execute(
        """SELECT run_id, parser, condition FROM runs
           WHERE prompt = 'extract_v3' AND model = 'gpt-6-luna' AND replicate = 0
           ORDER BY condition, parser"""
    ).fetchall():
        c = {d: x for d, x in doc_counts(con, rid).items() if d in docs}
        e = bootstrap_f1(c)
        pb = paired_bootstrap(base, c)
        delta = (
            "-"
            if rid.startswith(PRODUCTION)
            else f"{100 * pb.diff:+.1f} [{100 * pb.lo:+.1f}, {100 * pb.hi:+.1f}]"
        )  # noqa: E501
        rows.append([parser, cond, e.fmt(), delta])
    return table(["parser", "condition", "F1 [95% CI]", "Δ vs pypdf clean [95% CI]"], rows)


def threshold_sweep(con) -> str:
    """How much do the headline numbers depend on OUR match thresholds?"""
    rid = run_id(con, PRODUCTION)
    rows = con.execute(
        """SELECT DISTINCT o.doc_id, d.split, field, pred, gold FROM outcomes o
           JOIN docs d USING (doc_id)
           WHERE run_id = ? AND field IN ('parties', 'cap_on_liability')""",
        [rid],
    ).fetchall()
    out = []
    party_ts = [75, 80, PARTY_THRESHOLD, 90, 95]
    clause_ts = [0.3, 0.4, CLAUSE_F1_THRESHOLD, 0.6, 0.7]
    for name, ftype, ts, kw in [
        ("parties", "entity_list", party_ts, "party_threshold"),
        ("cap_on_liability", "clause", clause_ts, "clause_threshold"),
    ]:
        for t in ts:
            cells = []
            for split in ("dev", "test"):
                cnt = {"tp": 0, "fp": 0, "fn": 0, "wrong": 0}
                for _d, s, f, pred, gold in rows:
                    if f == name and s == split:
                        for o in match(ftype, json.loads(pred), json.loads(gold), **{kw: t}):
                            cnt[o] = cnt.get(o, 0) + 1
                tp, fp, fn = cnt["tp"], cnt["fp"] + cnt["wrong"], cnt["fn"] + cnt["wrong"]
                cells.append(pct(prf(tp, fp, fn)[2]))
            mark = " (current)" if t in (PARTY_THRESHOLD, CLAUSE_F1_THRESHOLD) else ""
            out.append([name, f"{t}{mark}", *cells])
    return table(["field", "threshold", "dev F1", "test F1"], out)


def doc_name_containment(con) -> str:
    rid = run_id(con, PRODUCTION)
    rows = con.execute(
        "SELECT doc_id, pred, gold FROM outcomes WHERE run_id = ? AND field = 'document_name' "
        "AND outcome = 'wrong'",
        [rid],
    ).fetchall()
    out = []
    for d, pred, gold in rows:
        p, g = normalize_doc_name(json.loads(pred)), normalize_doc_name(json.loads(gold))
        out.append(
            [
                d[:40],
                *(" ".join(json.loads(x).split()) for x in (pred, gold)),
                "yes" if p in g or g in p else "no",
            ]
        )
    return table(["doc", "predicted", "gold", "one contains the other"], out)


def taxonomy() -> str:
    path = ROOT / "evalsets" / "error_review.csv"
    if not path.exists():
        return "(run scripts/error_review.py)\n"
    with open(path) as f:
        rows = list(csv.DictReader(f))
    n_final = sum(bool(r["final_category"]) for r in rows)
    cat = Counter(r["final_category"] or r["draft_category"] or r["auto_category"] for r in rows)
    src = (
        "human-reviewed"
        if n_final == len(rows)
        else f"draft labels, {n_final}/{len(rows)} reviewed"
    )
    out = table(["category", "error rows"], [[c, n] for c, n in cat.most_common()])
    return (
        f"{len(rows)} (doc, field) error rows, {src}. A list field's items are one row.\n\n" + out
    )


def main() -> None:
    con = build()
    parts = {
        "Headline: all 30-doc runs, 22 test docs": headline(con),
        "Paired comparisons (same resampled docs; luna v3 r0 is the baseline)": paired(con),
        "Per field (production config, test)": per_field(con),
        "By field type": breakdown(con, "type", "field type"),
        "By document length": breakdown(con, "d.bucket", "length bucket"),
        "Stated vs derived ground truth (derived = GT computed by us from a term)": breakdown(
            con, "CASE WHEN derived THEN 'derived' ELSE 'stated' END", "GT"
        ),
        "By validator status (Phase 5; absent = nothing predicted, so FNs only)": breakdown(
            con, "coalesce(status, 'n/a')", "status"
        ),
        "Parser × scan condition (6 degraded test docs, paired vs pypdf on clean)": by_parser(con),
        "Match-threshold sensitivity (thresholds are fixed by judgment, not tuned to F1)": (
            threshold_sweep(con)
        ),
        "Document name: wrong predictions, containment check": doc_name_containment(con),
        "Error taxonomy (production config, test; see evalsets/error_review.csv)": taxonomy(),
    }
    body = "".join(f"### {k}\n\n{v}\n" for k, v in parts.items())
    print(body)
    section = (
        "<!-- eval:start -->\n## Evaluation harness (Phase 6)\n\n"
        "Generated by `make eval` from `data/eval.duckdb` (rebuilt from cached runs, $0). "
        "Micro F1 counts every outcome (list items individually); doc-macro F1 averages "
        "per-document F1 so one 30-party contract counts once. CIs: 2,000 bootstrap "
        "resamples of documents.\n\n" + body + "<!-- eval:end -->\n"
    )
    text = RESULTS.read_text()
    if "<!-- eval:start -->" in text:
        text = re.sub(r"<!-- eval:start -->.*<!-- eval:end -->\n", section, text, flags=re.S)
    else:
        text += "\n" + section
    RESULTS.write_text(text)


if __name__ == "__main__":
    main()
