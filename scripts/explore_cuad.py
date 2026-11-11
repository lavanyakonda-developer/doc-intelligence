"""Profile CUAD: contract types, lengths, label prevalence, normalized answers, text layers.

Writes data/explore/*.csv and prints a summary. Run: uv run python scripts/explore_cuad.py
"""

import csv
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
CUAD = ROOT / "data" / "raw" / "CUAD_v1"
OUT = ROOT / "data" / "explore"


def pctl(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def profile_docs() -> list[dict]:
    """One row per PDF: part, contract type (= folder), pages, chars of text layer."""
    rows = []
    for pdf in sorted((CUAD / "full_contract_pdf").rglob("*")):
        if pdf.suffix.lower() != ".pdf":
            continue
        rel = pdf.relative_to(CUAD / "full_contract_pdf").parts  # (Part_I, Type, file)
        reader = PdfReader(pdf)
        # Text-layer check on the first 3 pages only: enough to spot scanned docs, fast.
        sample_chars = sum(len(p.extract_text() or "") for p in reader.pages[:3])
        txt = CUAD / "full_contract_txt" / (pdf.stem + ".txt")
        n_chars = len(txt.read_text(errors="ignore")) if txt.exists() else None
        rows.append(
            {
                "file": pdf.stem,
                "part": rel[0],
                "contract_type": rel[1] if len(rel) > 2 else "?",
                "pages": len(reader.pages),
                "txt_chars": n_chars,
                "first3_pdf_text_chars": sample_chars,
            }
        )
    return rows


def profile_labels() -> list[dict]:
    """Per CUAD category: how many contracts have >=1 span, spans per doc, span length."""
    data = json.loads((CUAD / "CUAD_v1.json").read_text())["data"]
    present = Counter()
    n_spans = defaultdict(list)
    span_len = defaultdict(list)
    for doc in data:
        for para in doc["paragraphs"]:
            for qa in para["qas"]:
                cat = qa["id"].split("__", 1)[1]
                if qa["answers"]:
                    present[cat] += 1
                    n_spans[cat].append(len(qa["answers"]))
                    span_len[cat].extend(len(a["text"]) for a in qa["answers"])
                else:
                    present[cat] += 0
    n_docs = len(data)
    return [
        {
            "category": c,
            "docs_with_label": present[c],
            "prevalence": round(present[c] / n_docs, 3),
            "mean_spans_per_doc": round(st.mean(n_spans[c]), 2) if n_spans[c] else 0,
            "median_span_chars": int(st.median(span_len[c])) if span_len[c] else 0,
        }
        for c in sorted(present, key=lambda c: -present[c])
    ]


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    docs = profile_docs()
    labels = profile_labels()
    write_csv(docs, OUT / "docs.csv")
    write_csv(labels, OUT / "categories.csv")

    pages = [d["pages"] for d in docs]
    chars = [d["txt_chars"] for d in docs if d["txt_chars"]]
    print(f"\n== {len(docs)} contracts ==")
    print("by part:", dict(Counter(d["part"] for d in docs)))
    print(
        f"pages  min/med/p90/max: {min(pages)}/{pctl(pages, 0.5)}/{pctl(pages, 0.9)}/{max(pages)}"
    )
    print(
        f"chars  min/med/p90/max: {min(chars)}/{pctl(chars, 0.5)}/{pctl(chars, 0.9)}/{max(chars)}"
        f"  (~tokens = chars/4 -> median ~{pctl(chars, 0.5) // 4})"
    )
    no_text = [d["file"] for d in docs if d["first3_pdf_text_chars"] < 100]
    print(f"PDFs with ~no text layer in first 3 pages (likely scanned): {len(no_text)}")

    print("\n== contract types ==")
    for t, n in Counter(d["contract_type"] for d in docs).most_common():
        print(f"  {n:3d}  {t}")

    print("\n== categories (by prevalence) ==")
    for r in labels:
        print(
            f"  {r['prevalence']:.2f}  spans/doc={r['mean_spans_per_doc']:<5} "
            f"span_chars~{r['median_span_chars']:<5} {r['category']}"
        )

    # master_clauses.csv: which '-Answer' columns hold normalized values vs Yes/No?
    con = duckdb.connect()
    cols = [
        c[0]
        for c in con.execute(
            f"DESCRIBE SELECT * FROM read_csv_auto('{CUAD / 'master_clauses.csv'}')"
        ).fetchall()
    ]
    print("\n== master_clauses.csv '-Answer' columns: distinct values / top examples ==")
    for c in cols:
        if "Answer" not in c:
            continue
        top = con.execute(
            f"""SELECT "{c}", count(*) n FROM read_csv_auto('{CUAD / "master_clauses.csv"}')
                GROUP BY 1 ORDER BY n DESC LIMIT 4"""
        ).fetchall()
        n_distinct = con.execute(
            f"""SELECT count(DISTINCT "{c}") FROM read_csv_auto('{CUAD / "master_clauses.csv"}')"""
        ).fetchone()[0]
        ex = "; ".join(f"{str(v)[:30]!r}×{n}" for v, n in top)
        print(f"  [{n_distinct:3d}] {c[:45]:45s} {ex}")


if __name__ == "__main__":
    main()
