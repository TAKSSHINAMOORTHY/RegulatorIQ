"""Unit tests for text cleaning rules, dehyphenation, boilerplate removal, and spacing."""

from hypothesis import given
from hypothesis import strategies as st

from ingest.clean import (
    clean_unicode,
    compute_quality_score,
    dehyphenate,
    normalise_spacing,
    remove_letterhead_boilerplate,
    remove_repeating_headers_footers,
)


def test_clean_unicode_ligatures():
    assert clean_unicode("speciﬁc beneﬁt") == "specific benefit"
    assert clean_unicode("ﬂow chart") == "flow chart"
    assert clean_unicode("soft\xadhyphen") == "softhyphen"


def test_dehyphenate():
    # Only dehyphenates when joined word is alphabetic
    assert dehyphenate("regula-\ntion") == "regulation"
    assert dehyphenate("circu-\nlar") == "circular"
    # Should not dehyphenate non-alphabetic
    assert dehyphenate("2025-\n26") == "2025-\n26"


def test_remove_repeating_headers_footers():
    pages = [
        "Header Line 123\nPage 1\nActual regulatory content about KYC policies in 2025",
        "Header Line 456\nPage 2\nDifferent content regarding capital adequacy norms",
        "Header Line 789\nPage 3\nThird page details on digital lending framework",
    ]
    cleaned = remove_repeating_headers_footers(pages)
    assert len(cleaned) == 3
    for p in cleaned:
        assert "content" in p or "details" in p
        assert "Header Line" not in p


def test_remove_letterhead_boilerplate():
    text = (
        "RESERVE BANK OF INDIA\n"
        "Central Office, Shahid Bhagat Singh Road, Mumbai - 400 001\n"
        "Department of Regulation\n\n"
        "To All Scheduled Commercial Banks\n"
        "Madam / Dear Sir,\n"
        "Master Direction on KYC."
    )
    body, boilerplate = remove_letterhead_boilerplate(text)
    assert len(boilerplate) >= 2
    assert "To All Scheduled Commercial Banks" in body
    assert "Master Direction on KYC" in body


def test_normalise_spacing_preserves_paragraphs():
    raw = "Paragraph   one   with   spaces.\n\nParagraph   two.\n\n\nParagraph   three."
    cleaned = normalise_spacing(raw)
    paras = cleaned.split("\n\n")
    assert len(paras) == 3
    assert paras[0] == "Paragraph one with spaces."
    assert paras[1] == "Paragraph two."
    assert paras[2] == "Paragraph three."


def test_compute_quality_score():
    clean_text = "The Reserve Bank of India hereby issues the Master Direction on Capital Adequacy Norms for All Commercial Banks."
    score = compute_quality_score(clean_text)
    assert score > 0.8

    assert compute_quality_score("") == 0.0


# Property-based tests
@given(st.text())
def test_clean_unicode_idempotent(text: str):
    c1 = clean_unicode(text)
    c2 = clean_unicode(c1)
    assert c1 == c2


@given(st.text())
def test_dehyphenate_never_crashes(text: str):
    assert isinstance(dehyphenate(text), str)
