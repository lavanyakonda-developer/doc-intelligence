"""Aggregate data/results/parsers.csv -> comparison table (printed + docs/RESULTS.md section).

Only the 6-doc degraded subset is compared, so every parser x condition cell covers the
same documents and pages. Evidence recall is micro-averaged (total found / total spans):
long docs with many spans weigh more, which matches "share of clauses we can still read".
"""

import re

import duckdb

from docintel.config import PROJECT_ROOT

CSV = PROJECT_ROOT / "data" / "results" / "parsers.csv"
RESULTS = PROJECT_ROOT / "docs" / "RESULTS.md"

QUERY = f"""
SELECT
  parser,
  condition,
  count(*)                                        AS docs,
  sum(pages)                                      AS pages,
  round(100.0 * sum(exact) / sum(spans), 1)       AS evidence_exact_pct,
  round(100.0 * sum(fuzzy) / sum(spans), 1)       AS evidence_fuzzy_pct,
  round(100 * avg(wer), 1)                        AS wer_pct,
  round(sum(seconds) / sum(pages), 2)             AS sec_per_page,
  round(1000 * sum(cost_usd) / sum(pages), 3)     AS usd_per_1k_pages,
  sum(errors)                                     AS page_errors
FROM read_csv_auto('{CSV}')
WHERE in_subset
GROUP BY parser, condition
ORDER BY parser, CASE condition WHEN 'clean' THEN 0 WHEN 'light' THEN 1 ELSE 2 END
"""


def main() -> None:
    rel = duckdb.sql(QUERY)
    df = rel.fetchall()
    cols = rel.columns
    header = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = "".join("| " + " | ".join(str(v) for v in row) + " |\n" for row in df)
    table = header + body
    print(table)

    section = (
        "<!-- parsers:start -->\n## Parser comparison (Phase 3)\n\n"
        "Same 6 contracts / 57 pages per row. `evidence_*` = share of CUAD's lawyer-highlighted "
        "spans recoverable from the parsed text (exact after whitespace normalization; fuzzy = "
        "best alignment ≥ 90). WER is against CUAD's own .txt, itself a machine extraction, so "
        "it favours text-layer parsers. Seconds measured on an M2 Pro, CPU only.\n\n"
        + table
        + "<!-- parsers:end -->\n"
    )
    text = RESULTS.read_text() if RESULTS.exists() else "# Results\n\n"
    if "<!-- parsers:start -->" in text:  # idempotent: replace the section, keep the rest
        text = re.sub(r"<!-- parsers:start -->.*<!-- parsers:end -->\n", section, text, flags=re.S)
    else:
        text += section
    RESULTS.write_text(text)
    print(f"updated {RESULTS.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
