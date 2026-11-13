"""Where processed contracts live, and the questions you can ask of them.

`ResultStore` is the interface the API depends on; `DuckDBStore` is the local
implementation. The hosted backend is decided in Phase 9 (Cloud Run's disk is ephemeral),
and only a new class implementing this interface should be needed then.

Tables:
  contracts  one row per document: typed, flattened columns for analytics
             (DATE, days, booleans) + the full ContractResult as JSON
  fields     one row per (document, field): validator status, reasons, evidence
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import duckdb

from docintel.pipeline import ContractResult
from docintel.schema.types import ContractRecord, Duration, PartialDate

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    doc_id VARCHAR PRIMARY KEY,
    filename VARCHAR, processed_at TIMESTAMPTZ, parser VARCHAR, run_id VARCHAR,
    pages INTEGER, cost_usd DOUBLE,
    document_name VARCHAR,
    parties VARCHAR[],
    agreement_date DATE, effective_date DATE,
    expiration_date DATE,            -- NULL when unknown, partial, or perpetual
    expiration_text VARCHAR,         -- as extracted: '2021-05-31', '2021-05', 'perpetual'
    perpetual BOOLEAN,
    renewal_days DOUBLE,             -- approximate calendar days (1 month = 30.44)
    renewal_text VARCHAR,
    notice_days DOUBLE,
    governing_country VARCHAR, governing_region VARCHAR,
    non_compete BOOLEAN, exclusivity BOOLEAN, uncapped_liability BOOLEAN,
    termination_for_convenience BOOLEAN, change_of_control BOOLEAN,
    has_liability_cap BOOLEAN,
    needs_review VARCHAR[],          -- fields with status failed / unverified
    result JSON
);
CREATE TABLE IF NOT EXISTS fields (
    doc_id VARCHAR, field VARCHAR, status VARCHAR, reasons VARCHAR[], evidence VARCHAR,
    value JSON,
    PRIMARY KEY (doc_id, field)
);
"""

# Named, parameterized analytics queries: the business reason to extract structured data.
QUERIES: dict[str, tuple[str, dict[str, Any]]] = {
    "expiring_soon": (
        """SELECT doc_id, document_name, parties, expiration_date,
                  expiration_date - CAST($as_of AS DATE) AS days_left, renewal_text
           FROM contracts
           WHERE expiration_date BETWEEN CAST($as_of AS DATE)
                 AND CAST($as_of AS DATE) + to_days(CAST($days AS INTEGER))
           ORDER BY expiration_date""",
        {"as_of": None, "days": 90},
    ),
    "renewal_notice_deadlines": (
        # Auto-renewing contracts and the last day to send a non-renewal notice.
        """SELECT doc_id, document_name, expiration_date, renewal_text, notice_days,
                  CAST(expiration_date - to_days(CAST(ceil(notice_days) AS INTEGER)) AS DATE)
                      AS notice_deadline
           FROM contracts
           WHERE renewal_days IS NOT NULL AND notice_days IS NOT NULL
                 AND expiration_date IS NOT NULL
           ORDER BY notice_deadline""",
        {},
    ),
    "uncapped_liability": (
        """SELECT c.doc_id, c.document_name, c.parties, f.evidence
           FROM contracts c JOIN fields f ON f.doc_id = c.doc_id
                AND f.field = 'uncapped_liability'
           WHERE c.uncapped_liability
           ORDER BY c.document_name""",
        {},
    ),
    "governing_law_mix": (
        """SELECT governing_country, coalesce(governing_region, '-') AS region,
                  count(*) AS contracts
           FROM contracts WHERE governing_country IS NOT NULL
           GROUP BY ALL ORDER BY contracts DESC, governing_country, region""",
        {},
    ),
    "needs_review": (
        """SELECT f.doc_id, c.document_name, f.field, f.status, f.reasons
           FROM fields f JOIN contracts c USING (doc_id)
           WHERE f.status IN ('failed', 'unverified')
           ORDER BY f.status, f.doc_id, f.field""",
        {},
    ),
    "risk_flags": (
        # One row per contract: how many risk clauses it carries.
        """SELECT doc_id, document_name,
                  exclusivity, non_compete, uncapped_liability, change_of_control,
                  NOT coalesce(has_liability_cap, false) AS no_liability_cap,
                  (exclusivity::INT + non_compete::INT + uncapped_liability::INT
                   + change_of_control::INT) AS risk_score
           FROM contracts ORDER BY risk_score DESC, document_name""",
        {},
    ),
}


class ResultStore(Protocol):
    def save(self, result: ContractResult) -> None: ...
    def get(self, doc_id: str) -> ContractResult | None: ...
    def query(self, name: str, **params: Any) -> list[dict]: ...


def _date(v) -> date | None:
    if isinstance(v, PartialDate) and v.month and v.day:
        return date(v.year, v.month, v.day)
    return None


def _days(v) -> float | None:
    if not isinstance(v, Duration):
        return None
    if v.unit == "business_day":
        return v.value * 7 / 5
    return v.approx_days()


def flatten(r: ContractResult) -> dict[str, Any]:
    rec: ContractRecord = r.record
    exp, ren = rec.expiration_date.value, rec.renewal_term.value
    law = rec.governing_law.value
    return {
        "doc_id": r.doc_id,
        "filename": r.filename,
        "processed_at": r.processed_at,
        "parser": r.parser,
        "run_id": r.run_id,
        "pages": r.pages,
        "cost_usd": r.cost_usd,
        "document_name": rec.document_name.value,
        "parties": rec.parties.value or [],
        "agreement_date": _date(rec.agreement_date.value),
        "effective_date": _date(rec.effective_date.value),
        "expiration_date": _date(exp),
        "expiration_text": None if exp is None else str(exp),
        "perpetual": exp == "perpetual" or ren == "perpetual",
        "renewal_days": _days(ren),
        "renewal_text": None if ren is None else (ren if isinstance(ren, str) else
                                                  f"{ren.value} {ren.unit}"),
        "notice_days": _days(rec.notice_period_to_terminate_renewal.value),
        "governing_country": law.country if law else None,
        "governing_region": law.region if law else None,
        "non_compete": bool(rec.non_compete.value),
        "exclusivity": bool(rec.exclusivity.value),
        "uncapped_liability": bool(rec.uncapped_liability.value),
        "termination_for_convenience": bool(rec.termination_for_convenience.value),
        "change_of_control": bool(rec.change_of_control.value),
        "has_liability_cap": bool(rec.cap_on_liability.value),
        "needs_review": r.needs_review,
        "result": r.model_dump_json(exclude={"text"}),
    }  # fmt: skip


class DuckDBStore:
    def __init__(self, path: Path | str = ":memory:"):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute(SCHEMA)

    def save(self, result: ContractResult) -> None:
        if result.status != "ok":
            raise ValueError(f"not storing a failed result: {result.error}")
        row = flatten(result)
        cols = ", ".join(row)
        self.con.execute("BEGIN")
        try:  # contract + its fields replace any earlier version atomically
            self.con.execute(
                f"INSERT OR REPLACE INTO contracts ({cols}) VALUES ({', '.join('?' * len(row))})",
                list(row.values()),
            )
            self.con.execute("DELETE FROM fields WHERE doc_id = ?", [result.doc_id])
            self.con.executemany(
                "INSERT INTO fields VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        result.doc_id, name, f.status, f.reasons,
                        getattr(result.record, name).evidence,
                        json.dumps(getattr(result.record, name).model_dump(mode="json")["value"]),
                    )
                    for name, f in result.fields.items()
                ],
            )  # fmt: skip
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise

    def get(self, doc_id: str) -> ContractResult | None:
        row = self.con.execute("SELECT result FROM contracts WHERE doc_id = ?", [doc_id]).fetchone()
        return ContractResult.model_validate_json(row[0]) if row else None

    def query(self, name: str, **params: Any) -> list[dict]:
        if name not in QUERIES:
            raise KeyError(f"unknown query {name!r}; available: {sorted(QUERIES)}")
        sql, defaults = QUERIES[name]
        unknown = set(params) - set(defaults)
        if unknown:
            raise KeyError(f"{name} takes {sorted(defaults)}, got {sorted(unknown)}")
        args = {**defaults, **params}
        if "as_of" in args and args["as_of"] is None:
            args["as_of"] = date.today()
        cur = self.con.execute(sql, args or None)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
