"""Normalizer tests. Cases are real values from CUAD's master_clauses.csv."""

import pytest

from docintel.schema.normalize import (
    UnparseableError,
    normalize_doc_name,
    normalize_party,
    parse_date,
    parse_duration,
    parse_jurisdiction,
    split_parties,
)
from docintel.schema.types import Duration, Jurisdiction, PartialDate


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("11/12/19", PartialDate(year=2019, month=11, day=12)),
        ("6/30/99", PartialDate(year=1999, month=6, day=30)),
        ("6/30/29", PartialDate(year=2029, month=6, day=30)),  # future expiration
        ("09/[]/2019", PartialDate(year=2019, month=9)),
        ("[]/[]/2020", PartialDate(year=2020)),
        ("07/[]/2033", PartialDate(year=2033, month=7)),
        ("2019-11-12", PartialDate(year=2019, month=11, day=12)),  # ISO, what the LLM emits
        ("2019-09", PartialDate(year=2019, month=9)),
        ("perpetual", "perpetual"),
        ("Perpetual", "perpetual"),
        ("None", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["[]/[]/19[]", "sometime in spring", "13/45/2019"])
def test_parse_date_unparseable(raw):
    with pytest.raises(UnparseableError):
        parse_date(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("successive 5 year", Duration(value=5, unit="year")),
        ("succesive 1 year", Duration(value=1, unit="year")),  # CUAD typo
        ("2 successive 5 years", Duration(value=5, unit="year")),  # term length, not count
        ("12 Months", Duration(value=12, unit="month")),
        ("3 Months", Duration(value=3, unit="month")),
        ("120 days", Duration(value=120, unit="day")),
        ("thirty (30) days", Duration(value=30, unit="day")),
        ("one year", Duration(value=1, unit="year")),
        ("perpetual", "perpetual"),
        ("None", None),
    ],
)
def test_parse_duration(raw, expected):
    assert parse_duration(raw) == expected


def test_duration_unit_families():
    assert (
        Duration(value=12, unit="month").in_months() == Duration(value=1, unit="year").in_months()
    )
    assert Duration(value=2, unit="week").in_days() == 14
    assert Duration(value=3, unit="day").in_months() is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("thirty (30) business days", Duration(value=30, unit="business_day")),
        ("10 working days", Duration(value=10, unit="business_day")),
        ("sixty (60) calendar days", Duration(value=60, unit="day")),
        ("two weeks", Duration(value=2, unit="week")),
    ],
)
def test_parse_duration_business_and_calendar(raw, expected):
    assert parse_duration(raw) == expected


@pytest.mark.parametrize(
    "raw, key",
    [
        ("New York", ("United States", "New York")),
        ("the laws of the State of New York", ("United States", "New York")),
        ("Ontario, Canada", ("Canada", "Ontario")),
        ("Japan", ("Japan", None)),
        ("England and Wales", ("United Kingdom", None)),
        ("West Virginia", ("United States", "West Virginia")),  # not also 'Virginia'
        ("New Mexico", ("United States", "New Mexico")),
        ("Delaware, United States", ("United States", "Delaware")),
        ("New York; Delaware", ("OTHER", None)),  # two states -> ambiguous
        ("THE STATE IN WHICH THE FRANCHISED RESTAURANT IS LOCATED", ("OTHER", None)),
    ],
)
def test_parse_jurisdiction(raw, key):
    j = parse_jurisdiction(raw)
    assert isinstance(j, Jurisdiction) and j.key() == key


def test_jurisdiction_absent():
    assert parse_jurisdiction("None") is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("FORM OF TRADEMARK LICENSE AGREEMENT", "TRADEMARK LICENSE AGREEMENT"),
        ("Online Hosting Agreement", "ONLINE HOSTING AGREEMENT"),
        ("Master Service Agreement.", "MASTER SERVICE AGREEMENT"),
        ("CO-BRANDING CONTENT AGREEMENT", "CO BRANDING CONTENT AGREEMENT"),
    ],
)
def test_normalize_doc_name(raw, expected):
    assert normalize_doc_name(raw) == expected


def test_split_parties():
    raw = 'Calm.com, Inc. ("Calm"); XpresSpa Group, Inc. ("XPSA")("Party" and collectively'
    assert split_parties(raw) == ["Calm.com, Inc.", "XpresSpa Group, Inc."]


def test_split_parties_drops_alias_only_items():
    raw = 'WATER NOW, INC.; ("Water Now"); Hydraspin USA, Inc. ("Subsidiary")'
    assert split_parties(raw) == ["WATER NOW, INC.", "Hydraspin USA, Inc."]


def test_split_parties_curly_quotes():
    raw = "AizuFujitsu Semiconductor Limited (“AFSL”); Fujitsu Semiconductor Limited (“FSL”)"
    assert split_parties(raw) == [
        "AizuFujitsu Semiconductor Limited",
        "Fujitsu Semiconductor Limited",
    ]


def test_normalize_party():
    assert normalize_party("Calm.com, Inc.") == "calm com"
    assert normalize_party("PACTIV LLC") == "pactiv"


@pytest.mark.parametrize(
    "raw, expected", [("Yes", True), ("No", False), ("True", True), (False, False)]
)
def test_parse_bool(raw, expected):
    from docintel.schema.normalize import parse_bool

    assert parse_bool(raw) is expected


def test_parse_bool_rejects_garbage():
    from docintel.schema.normalize import parse_bool

    with pytest.raises(UnparseableError):
        parse_bool("maybe")


def test_split_parties_drops_collective_definition():
    raw = (
        'GWG Holdings, Inc. ("GWG"); Trust Advisors ("Trust Advisors"); '
        "GWG and Trust Advisors (each a “Party” and collectively as the “Parties”)"
    )
    assert split_parties(raw) == ["GWG Holdings, Inc.", "Trust Advisors"]


@pytest.mark.parametrize(
    "anchor, term, expected",
    [
        (PartialDate(year=2019, month=11, day=12), Duration(value=5, unit="year"),
         PartialDate(year=2024, month=11, day=12)),
        (PartialDate(year=2020, month=1, day=31), Duration(value=1, unit="month"),
         PartialDate(year=2020, month=2, day=29)),  # month-end clamp, leap year
        (PartialDate(year=2019, month=11, day=1), Duration(value=18, unit="month"),
         PartialDate(year=2021, month=5, day=1)),
        (PartialDate(year=2019, month=9), Duration(value=2, unit="year"),
         PartialDate(year=2021, month=9)),  # partial anchor stays partial
        (PartialDate(year=2020), Duration(value=3, unit="year"), PartialDate(year=2023)),
        (PartialDate(year=1999, month=12, day=20), Duration(value=30, unit="day"),
         PartialDate(year=2000, month=1, day=19)),
    ],
)  # fmt: skip
def test_resolve_relative_date(anchor, term, expected):
    from docintel.schema.normalize import resolve_relative_date

    assert resolve_relative_date(anchor, term) == expected


@pytest.mark.parametrize(
    "anchor, term",
    [
        (PartialDate(year=2020), Duration(value=6, unit="month")),  # month unknown
        (PartialDate(year=2020, month=3), Duration(value=90, unit="day")),  # day unknown
        (PartialDate(year=2020, month=3, day=1), Duration(value=10, unit="business_day")),
    ],
)
def test_resolve_relative_date_refuses_to_guess(anchor, term):
    from docintel.schema.normalize import resolve_relative_date

    with pytest.raises(UnparseableError):
        resolve_relative_date(anchor, term)
