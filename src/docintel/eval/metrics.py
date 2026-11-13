"""Metrics over the outcomes table: micro F1, per-doc macro for list fields, bootstrap CIs.

Why bootstrap over DOCS: fields of one document are correlated (a bad parse hurts all of
them), so the document is the independent unit. Resampling fields would treat 14 correlated
outcomes as 14 independent ones and give intervals that are too narrow.
"""

import random
from collections import defaultdict
from dataclasses import dataclass

import duckdb

Counts = tuple[int, int, int]  # tp, fp, fn   ('wrong' adds 1 to fp and 1 to fn)


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def f1(c: Counts) -> float:
    return prf(*c)[2]


def doc_counts(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    split: str | None = None,
    where: str = "TRUE",
) -> dict[str, Counts]:
    """Per-doc (tp, fp, fn) for one run. `where` filters outcomes (e.g. "type = 'date'")."""
    rows = con.execute(
        f"""
        SELECT o.doc_id,
               count(*) FILTER (outcome = 'tp'),
               count(*) FILTER (outcome IN ('fp', 'wrong')),
               count(*) FILTER (outcome IN ('fn', 'wrong'))
        FROM outcomes o JOIN docs d USING (doc_id)
        WHERE run_id = ? AND (? IS NULL OR d.split = ?) AND ({where})
        GROUP BY 1
        """,
        [run_id, split, split],
    ).fetchall()
    return {d: (tp, fp, fn) for d, tp, fp, fn in rows}


def total(counts: dict[str, Counts]) -> Counts:
    return tuple(sum(c[i] for c in counts.values()) for i in range(3))  # type: ignore[return-value]


@dataclass
class Estimate:
    value: float
    lo: float
    hi: float
    n_docs: int

    def fmt(self) -> str:
        return f"{100 * self.value:.1f} [{100 * self.lo:.1f}, {100 * self.hi:.1f}]"


def _ci(samples: list[float], alpha: float) -> tuple[float, float]:
    s = sorted(samples)
    return s[int(alpha / 2 * len(s))], s[int((1 - alpha / 2) * len(s)) - 1]


def bootstrap_f1(
    counts: dict[str, Counts], *, n: int = 2000, seed: int = 0, alpha: float = 0.05
) -> Estimate:
    """Micro F1 with a percentile CI from resampling documents with replacement."""
    docs = sorted(counts)
    rng = random.Random(seed)
    samples = [
        f1(total({i: counts[d] for i, d in enumerate(rng.choices(docs, k=len(docs)))}))
        for _ in range(n)
    ]
    return Estimate(f1(total(counts)), *_ci(samples, alpha), len(docs))


@dataclass
class Paired:
    diff: float  # F1(b) - F1(a)
    lo: float
    hi: float
    p_not_better: float  # share of resamples where b <= a (one-sided bootstrap "p-value")
    n_docs: int


def paired_bootstrap(
    a: dict[str, Counts],
    b: dict[str, Counts],
    *,
    n: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> Paired:
    """Compare two configs on the SAME resampled docs each time. The doc-to-doc variation
    (hard vs easy contracts) cancels out, so this is far tighter than comparing two CIs."""
    docs = sorted(set(a) & set(b))
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        pick = rng.choices(docs, k=len(docs))
        diffs.append(
            f1(total({i: b[d] for i, d in enumerate(pick)}))
            - f1(total({i: a[d] for i, d in enumerate(pick)}))
        )
    point = f1(total({d: b[d] for d in docs})) - f1(total({d: a[d] for d in docs}))
    lo, hi = _ci(diffs, alpha)
    return Paired(point, lo, hi, sum(x <= 0 for x in diffs) / n, len(docs))


def list_field_macro(con, run_id: str, field: str, *, split: str | None = None) -> float | None:
    """Per-doc F1 averaged over docs that have anything (gold or predicted) for this field.
    One contract with 30 parties counts once, not 30 times."""
    counts = doc_counts(con, run_id, split=split, where=f"field = '{field}'")
    scored = [f1(c) for c in counts.values() if sum(c)]
    return sum(scored) / len(scored) if scored else None


def counts_by(
    con, run_id: str, column: str, *, split: str | None = None
) -> dict[str, dict[str, Counts]]:
    """{group value: per-doc counts} for a breakdown column of outcomes/docs."""
    rows = con.execute(
        f"""
        SELECT {column} AS g, o.doc_id,
               count(*) FILTER (outcome = 'tp'),
               count(*) FILTER (outcome IN ('fp', 'wrong')),
               count(*) FILTER (outcome IN ('fn', 'wrong'))
        FROM outcomes o JOIN docs d USING (doc_id)
        WHERE run_id = ? AND (? IS NULL OR d.split = ?)
        GROUP BY 1, 2
        """,
        [run_id, split, split],
    ).fetchall()
    out: dict[str, dict[str, Counts]] = defaultdict(dict)
    for g, d, tp, fp, fn in rows:
        out[str(g)][d] = (tp, fp, fn)
    return dict(out)
