"""Find values written in a piece of text: dates and numbers.

Shared by the ground-truth audit (D8) and the value<->evidence validator, so both use
one implementation.
"""

import re

from docintel.schema.types import PartialDate

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        "january february march april may june july "
        "august september october november december".split()
    )
}
# abbreviations too ("Nov. 12, 2019", "Sept 1"); longest first so the regex prefers "november"
MONTHS |= {m[:3]: i for m, i in list(MONTHS.items())} | {"sept": 9}
_M = "|".join(sorted(MONTHS, key=len, reverse=True))

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "eighteen": 18, "twenty": 20, "twenty-four": 24,
    "thirty": 30, "forty-five": 45, "sixty": 60, "ninety": 90, "a": 1, "an": 1,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "tenth": 10,
}  # fmt: skip


def _clean(text: str) -> str:
    t = re.sub(r"\s+", " ", text.lower())
    t = t.replace("1s t", "1st")  # CUAD text-layer glitches: '1s t', '20t h'
    return re.sub(r"(\d)\s?(st|nd|rd|th)\b", r"\1\2", t.replace("t h ", "th "))


def dates_in_text(text: str) -> set[PartialDate]:
    """'May 31st 2021', '25th day of May, 2018', '6/1/2020', 'June 2020', '2020-06-01'."""
    t = _clean(text)
    out: set[PartialDate] = set()

    def add(y, m=None, d=None):
        try:
            out.add(PartialDate(year=int(y), month=m and int(m), day=d and int(d)))
        except ValueError:
            pass

    for m in re.finditer(rf"\b({_M})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", t):
        add(m[3], MONTHS[m[1]], m[2])
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+day\s+of\s+({_M})\.?,?\s+(\d{{4}})", t):
        add(m[3], MONTHS[m[2]], m[1])
    for m in re.finditer(rf"\b({_M})\.?,?\s+(\d{{4}})\b", t):
        add(m[2], MONTHS[m[1]])
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b", t):
        y = m[3] if len(m[3]) == 4 else ("19" if int(m[3]) >= 50 else "20") + m[3]
        add(y, m[1], m[2])
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", t):
        add(m[1], m[2], m[3])
    return out


def numbers_in_text(text: str) -> set[int]:
    t = _clean(text)
    nums = {int(n) for n in re.findall(r"\b\d+\b", t)}
    nums |= {v for w, v in NUMBER_WORDS.items() if re.search(rf"\b{re.escape(w)}\b", t)}
    return nums
