"""Normalizers: messy strings -> domain types.

Used for BOTH CUAD ground truth and LLM outputs. If a normalizer is wrong, every
metric is wrong, so each one is unit-tested (tests/test_normalize.py).

Contract: return the domain value, or None if the input means "absent".
Raise UnparseableError if the input is present but can't be interpreted. The
caller decides what to do (GT: exclude field from scoring; LLM: validation failure).
"""

import calendar
import re
import unicodedata
from datetime import date, timedelta

from docintel.schema.types import Duration, Jurisdiction, PartialDate, Perpetual


class UnparseableError(ValueError):
    pass


_ABSENT = {"", "none", "null", "n/a", "[]"}


def is_absent(raw: str | None) -> bool:
    return raw is None or raw.strip().lower() in _ABSENT


# ---------------------------------------------------------------- dates

_UNKNOWN = r"\[\]|\?\?|xx"  # CUAD marks unknown date parts with []


def _expand_year(y: str) -> int:
    n = int(y)
    if len(y) == 2:  # CUAD contracts span ~1995-2020; expirations can reach the 2030s-40s
        return 1900 + n if n >= 50 else 2000 + n
    return n


def parse_date(raw: str | None) -> PartialDate | Perpetual | None:
    """'11/12/19' -> 2019-11-12, '09/[]/2019' -> 2019-09, '2019-11-12' (ISO), 'perpetual'."""
    if is_absent(raw):
        return None
    s = raw.strip().lower()
    if s == "perpetual":
        return "perpetual"
    if m := re.fullmatch(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", s):  # ISO / partial ISO
        y, mo, d = m.groups()
        return PartialDate(year=int(y), month=mo and int(mo), day=d and int(d))
    if m := re.fullmatch(rf"(\d{{1,2}}|{_UNKNOWN})/(\d{{1,2}}|{_UNKNOWN})/(\d{{2}}|\d{{4}})", s):
        mo, d, y = m.groups()
        month = int(mo) if mo.isdigit() else None
        day = int(d) if d.isdigit() and month is not None else None
        try:
            return PartialDate(year=_expand_year(y), month=month, day=day)
        except ValueError as e:
            raise UnparseableError(f"date {raw!r}: {e}") from e
    raise UnparseableError(f"date {raw!r}")


# ---------------------------------------------------------------- durations

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1,
}  # fmt: skip
_UNITS = {
    "business day": "business_day", "working day": "business_day", "calendar day": "day",
    "day": "day", "week": "week", "month": "month", "year": "year", "yr": "year",
}  # fmt: skip


def parse_duration(raw: str | None) -> Duration | Perpetual | None:
    """'successive 1 year' -> 1 year; '2 successive 5 years' -> 5 years; '3 Months'; '90 days'.

    For '2 successive 5 years' the *term length* is 5 years (the 2 is the renewal count,
    which CUAD doesn't evaluate), so we take the number immediately before the unit.
    """
    if is_absent(raw):
        return None
    s = raw.strip().lower()
    if "perpetual" in s:
        return "perpetual"
    # Legal style "thirty (30) days": trust the digits, drop the spelled-out word.
    s = re.sub(r"[a-z-]+\s*\(\s*(\d+)\s*\)", r"\1", s)
    units = "|".join(sorted(_UNITS, key=len, reverse=True))  # 'business day' before 'day'
    pattern = r"\b(\d+|" + "|".join(_NUM_WORDS) + r")[\s-]*(" + units + r")s?\b"
    if m := re.search(pattern, s):
        n, unit = m.groups()
        value = int(n) if n.isdigit() else _NUM_WORDS[n]
        return Duration(value=value, unit=_UNITS[unit])
    raise UnparseableError(f"duration {raw!r}")


# ---------------------------------------------------------------- jurisdictions

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
    "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
    "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]  # fmt: skip
CA_PROVINCES = [
    "Alberta", "British Columbia", "Manitoba", "New Brunswick", "Newfoundland", "Nova Scotia",
    "Ontario", "Prince Edward Island", "Quebec", "Saskatchewan",
]  # fmt: skip
COUNTRY_ALIASES = {
    "england": "United Kingdom", "england and wales": "United Kingdom", "uk": "United Kingdom",
    "united kingdom": "United Kingdom", "japan": "Japan", "switzerland": "Switzerland",
    "germany": "Germany", "china": "China", "prc": "China",
    "people's republic of china": "China", "hong kong": "Hong Kong", "singapore": "Singapore",
    "israel": "Israel", "india": "India", "france": "France", "netherlands": "Netherlands",
    "ireland": "Ireland", "canada": "Canada", "australia": "Australia", "sweden": "Sweden",
    "united states": "United States", "usa": "United States", "u.s.": "United States",
}  # fmt: skip


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.' ]+", " ", s)).strip()


def _find_all(names: list[str], text: str) -> list[str]:
    # Longest names first so "West Virginia" isn't also counted as "Virginia".
    found, t = [], f" {text} "
    for n in sorted(names, key=len, reverse=True):
        pat = rf"(?<![a-z]){re.escape(n.lower())}(?![a-z])"
        if re.search(pat, t):
            found.append(n)
            t = re.sub(pat, " ", t)
    return found


def parse_jurisdiction(raw: str | None) -> Jurisdiction | None:
    """'New York' / 'the State of New York' -> (United States, New York);
    'Ontario, Canada' -> (Canada, Ontario); 'Japan' -> (Japan, None);
    anything ambiguous or non-standard -> (OTHER, None, raw)."""
    if is_absent(raw):
        return None
    t = _norm(raw)
    states = _find_all(US_STATES, t)
    provinces = _find_all(CA_PROVINCES, t)
    # Only scan for countries in what's left after removing state names
    # ("New Mexico" must not trigger a country lookup for "Mexico", etc.).
    rest = t
    for n in states + provinces:
        rest = re.sub(re.escape(n.lower()), " ", rest)
    countries = {
        v
        for k, v in COUNTRY_ALIASES.items()
        if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z.])", rest)
    }  # noqa: E501

    if len(states) == 1 and not provinces and countries <= {"United States"}:
        return Jurisdiction(country="United States", region=states[0], raw=raw)
    if len(provinces) == 1 and not states and countries <= {"Canada"}:
        return Jurisdiction(country="Canada", region=provinces[0], raw=raw)
    if not states and not provinces and len(countries) == 1:
        return Jurisdiction(country=countries.pop(), raw=raw)
    return Jurisdiction(country="OTHER", raw=raw)


# ---------------------------------------------------------------- text / entities

_DOC_PREFIX = re.compile(r"^(form of|execution version|confidential)\s+")


def normalize_doc_name(raw: str | None) -> str | None:
    """'FORM OF Trademark License Agreement.' -> 'TRADEMARK LICENSE AGREEMENT'."""
    if is_absent(raw):
        return None
    s = _norm(raw).replace(".", " ").replace("'", "")
    s = _DOC_PREFIX.sub("", re.sub(r"\s+", " ", s).strip())
    return s.upper() or None


_COLLECTIVE = re.compile(r"\b(collectively|each a)\b", re.IGNORECASE)


def _mentions(text: str, parties: list[str]) -> int:
    """How many already-found parties does `text` refer to (by their first name token)?"""
    t = f" {normalize_party(text)} "
    return sum(1 for p in parties if (tok := normalize_party(p).split()[:1]) and f" {tok[0]} " in t)


def split_parties(raw: str | None) -> list[str] | None:
    """CUAD Parties-Answer: 'Calm.com, Inc. ("Calm"); XpresSpa Group, Inc. ("XPSA")'
    -> ['Calm.com, Inc.', 'XpresSpa Group, Inc.']  (aliases in parens/quotes removed)."""
    if is_absent(raw):
        return None
    out = []
    for part in raw.split(";"):
        p = re.sub(r"\([^)]*\)?", " ", part)  # (aliases), including a truncated '(... '
        p = re.sub(r"[\"“”][^\"“”]*[\"“”]", " ", p)  # "quoted aliases"
        p = re.sub(r"\s+", " ", p).strip(" ,;:-")
        if _COLLECTIVE.search(part) and _mentions(p, out) >= 2:
            continue  # 'GWG and Trust Advisors (each a "Party", collectively ...)': not a new party
        if p and p.lower() not in out:
            out.append(p)
    return out or None


_ENTITY_SUFFIX = re.compile(
    r"\b(inc|incorporated|llc|l\.?l\.?c|ltd|limited|corp|corporation|co|company|plc|"
    r"l\.?p|lp|gmbh|ag|s\.?a|n\.?v|b\.?v|pty|holdings?)\b\.?"
)


_AKA = re.compile(r"\b(f/k/a|d/b/a|formerly known as|doing business as)\b.*$")


def normalize_party(name: str) -> str:
    """For fuzzy matching only: 'Glu Mobile, Inc. f/k/a Sorrent, Inc.' -> 'glu mobile'."""
    s = _AKA.sub(" ", unicodedata.normalize("NFKC", name).lower())
    s = _ENTITY_SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


# ---------------------------------------------------------------- booleans

_TRUE, _FALSE = {"yes", "true", "y", "1"}, {"no", "false", "n", "0"}


def parse_bool(raw: str | bool | None) -> bool:
    """Strict: CUAD uses 'Yes'/'No'; anything unrecognized raises instead of silently -> False."""
    if isinstance(raw, bool):
        return raw
    s = (raw or "").strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise UnparseableError(f"boolean {raw!r}")


# ---------------------------------------------------------------- relative dates


def resolve_relative_date(anchor: PartialDate, term: Duration) -> PartialDate:
    """'N years after the Effective Date' -> concrete date. Deterministic code, never the LLM.

    Convention (verified against CUAD's annotator-computed expirations): same calendar day,
    no minus-one -> 2019-11-12 + 5 years = 2024-11-12. Month-end is clamped (Jan 31 + 1 month
    -> Feb 28/29). Partial anchors stay partial; raises if the result can't be determined.
    """
    if (months := term.in_months()) is not None:
        if anchor.month is None:
            if months % 12:
                raise UnparseableError(f"can't add {term} to year-only anchor {anchor}")
            return PartialDate(year=anchor.year + months // 12)
        total = anchor.month - 1 + months
        year, month = anchor.year + total // 12, total % 12 + 1
        day = anchor.day and min(anchor.day, calendar.monthrange(year, month)[1])
        return PartialDate(year=year, month=month, day=day)
    if (days := term.in_days()) is not None:
        if anchor.day is None:
            raise UnparseableError(f"can't add {term} to partial anchor {anchor}")
        d = date(anchor.year, anchor.month, anchor.day) + timedelta(days=days)
        return PartialDate(year=d.year, month=d.month, day=d.day)
    raise UnparseableError(f"unsupported term unit for date arithmetic: {term}")
