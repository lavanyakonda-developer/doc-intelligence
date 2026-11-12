from docintel.eval.match import match, token_f1
from docintel.schema.types import Duration, Jurisdiction, PartialDate

D = PartialDate


def test_presence_outcomes():
    assert match("boolean", True, True) == ["tp"]
    assert match("boolean", True, False) == ["fp"]
    assert match("boolean", False, True) == ["fn"]
    assert match("boolean", False, False) == ["tn"]
    assert match("date", None, None) == ["tn"]


def test_wrong_value_is_its_own_outcome():
    # Both present, different -> 'wrong' (scored as FP + FN), not silently a TP or FN.
    assert match("date", D(year=2020, month=1, day=1), D(year=2021, month=1, day=1)) == ["wrong"]


def test_partial_gt_date_matches_more_specific_prediction():
    assert match("date", D(year=2019, month=9, day=15), D(year=2019, month=9)) == ["tp"]
    assert match("date", D(year=2019, month=8, day=15), D(year=2019, month=9)) == ["wrong"]


def test_perpetual():
    assert match("date", "perpetual", "perpetual") == ["tp"]
    assert match("date", D(year=2030), "perpetual") == ["wrong"]


def test_duration_compared_in_days():
    assert match("duration", Duration(value=30, unit="day"), Duration(value=1, unit="month")) == [
        "tp"
    ]
    assert match("duration", Duration(value=60, unit="day"), Duration(value=1, unit="month")) == [
        "wrong"
    ]


def test_duration_unit_equivalence():
    assert match("duration", Duration(value=90, unit="day"), Duration(value=3, unit="month")) == [
        "tp"
    ]
    assert match("duration", Duration(value=1, unit="year"), Duration(value=12, unit="month")) == [
        "tp"
    ]


def test_duration_business_days_never_equal_calendar():
    bd = Duration(value=30, unit="business_day")
    assert match("duration", bd, Duration(value=30, unit="day")) == ["wrong"]
    assert match("duration", bd, Duration(value=30, unit="business_day")) == ["tp"]


def test_duration_same_family_is_exact():
    assert match("duration", Duration(value=2, unit="week"), Duration(value=14, unit="day")) == [
        "tp"
    ]
    assert match("duration", Duration(value=13, unit="month"), Duration(value=1, unit="year")) == [
        "wrong"
    ]


def test_jurisdiction():
    ny = Jurisdiction(country="United States", region="New York")
    ca = Jurisdiction(country="United States", region="California")
    assert match("enum", ny, ny) == ["tp"]
    assert match("enum", ca, ny) == ["wrong"]


def test_doc_name_normalized():
    assert match("text", "Form of Franchise Agreement", "FRANCHISE AGREEMENT") == ["tp"]


def test_parties_item_level():
    gt = ["Calm.com, Inc.", "XpresSpa Group, Inc."]
    pred = ["Calm.com Inc", "XpresSpa Group", "Some Bank N.A."]
    assert sorted(match("entity_list", pred, gt)) == ["fp", "tp", "tp"]


def test_parties_missing_one():
    assert sorted(match("entity_list", ["PACTIV LLC"], ["PACTIV LLC", "Reynolds LLC"])) == [
        "fn",
        "tp",
    ]


def test_clause_segmentation_insensitive():
    gt = ["IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY INDIRECT OR CONSEQUENTIAL DAMAGES."]
    pred = ["In no event shall either party be liable", "for any indirect or consequential damages"]
    assert match("clause", pred, gt) == ["tp"]


def test_clause_unrelated_text_is_wrong():
    assert match(
        "clause",
        ["This Agreement is governed by Delaware law."],
        ["Liability capped at fees paid."],
    ) == ["wrong"]  # noqa: E501


def test_token_f1():
    assert token_f1("a b c", "a b c") == 1.0
    assert token_f1("a b", "c d") == 0.0


def test_near_misses_logged_for_borderline_parties():
    from docintel.eval.match import NearMiss

    log: list[NearMiss] = []
    # Real CUAD pairs. Typo'd label (89) -> accepted near-miss.
    assert match("entity_list", ["Ultraline Limited"], ["Ultrallne Limited"], near_misses=log) == [
        "tp"
    ]
    # Two DIFFERENT companies from the same contract score 91 -> must be visible for review.
    match(
        "entity_list",
        ["Fujitsu Semiconductor Limited"],
        ["AizuFujitsu Semiconductor Limited"],
        near_misses=log,
    )
    # Far miss -> not logged.
    match("entity_list", ["Totally Different Co"], ["Calm.com, Inc."], near_misses=log)
    assert [(n.pred, n.accepted) for n in log] == [
        ("Ultraline Limited", True),
        ("Fujitsu Semiconductor Limited", True),
    ]


def test_subset_name_is_not_a_match():
    assert sorted(match("entity_list", ["Bank"], ["Bank of America, N.A."])) == ["fn", "fp"]


def test_aka_aliases_stripped():
    assert match("entity_list", ["Glu Mobile Inc"], ["Glu Mobile, Inc. f/k/a Sorrent, Inc."]) == [
        "tp"
    ]


def test_thresholds_are_parameters():
    gt = ["IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR INDIRECT DAMAGES"]
    pred = ["either party liable for damages exceeding fees paid"]
    assert match("clause", pred, gt, clause_threshold=0.9) == ["wrong"]
    assert match("clause", pred, gt, clause_threshold=0.1) == ["tp"]
