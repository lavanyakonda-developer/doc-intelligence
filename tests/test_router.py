import pytest

from docintel.corpus import DEGRADED, find_pdf, golden_set
from docintel.parsing.router import choose_parser

pytestmark = pytest.mark.skipif(not DEGRADED.exists(), reason="run `make data degrade` first")


def test_routes_clean_to_pypdf_and_scans_to_vision():
    docs = [d["file"] for d in golden_set() if d["degraded"] == "True"]
    assert {choose_parser(find_pdf(d, "clean")) for d in docs} == {"pypdf"}
    for cond in ("light", "heavy"):
        assert {choose_parser(find_pdf(d, cond)) for d in docs} == {"vision"}


def test_all_golden_clean_docs_have_text_layer():
    assert {choose_parser(find_pdf(d["file"])) for d in golden_set()} == {"pypdf"}
