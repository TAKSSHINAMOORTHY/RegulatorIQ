"""Unit tests for normalisation functions and URL verification."""

from hypothesis import given
from hypothesis import strategies as st

from ingest.normalise import (
    canonicalise_url,
    compute_doc_id,
    extract_updated_as_on,
    is_rbi_host,
    normalise_circular_no,
    parse_issue_date,
)


def test_circular_number_fixtures():
    # RBI prefix variations
    assert normalise_circular_no("RBI/2025-2026/95") == "RBI/2025-26/95"
    assert normalise_circular_no("RBI/2025-26/90") == "RBI/2025-26/90"
    assert normalise_circular_no("RBI/FMRD/2025-26/142") == "RBI/FMRD/2025-26/142"

    # Department circular variations
    assert (
        normalise_circular_no("DOR.MCS.REC.59/01.01.003/2025-26")
        == "DOR.MCS.REC.59/01.01.003/2025-26"
    )
    assert (
        normalise_circular_no("DoR.GOV.REC.No.414/18.10.008/2025-26")
        == "DOR.GOV.REC.NO.414/18.10.008/2025-26"
    )
    assert (
        normalise_circular_no("FIDD.CO.LBS.BC.No.13/02.08.001/2025-26")
        == "FIDD.CO.LBS.BC.NO.13/02.08.001/2025-26"
    )

    # A.P. (DIR Series) variation
    assert (
        normalise_circular_no("A.P. (DIR Series) Circular No. 23")
        == "A.P. (DIR Series) Circular No. 23"
    )


def test_parse_issue_date():
    iso, year = parse_issue_date("11.11.2025")
    assert iso == "2025-11-11"
    assert year == 2025

    iso2, year2 = parse_issue_date("March 10, 2026")
    assert iso2 == "2026-03-10"
    assert year2 == 2026

    assert parse_issue_date(None) == (None, None)
    assert parse_issue_date("invalid gibberish text") == (None, None)


def test_extract_updated_as_on():
    raw_title = "Reserve Bank of India (Asset Reconstruction Companies) Directions, 2025 (Updated as on March 10, 2026)"
    clean_title, updated_date = extract_updated_as_on(raw_title)

    assert "Directions, 2025" in clean_title
    assert updated_date == "2026-03-10"


def test_rbi_host_allowlist():
    assert is_rbi_host("https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336")
    assert is_rbi_host("https://rbi.org.in/notifications_rss.xml")
    assert is_rbi_host("https://website.rbi.org.in/web/rbi/notifications/rbi-circulars")
    assert is_rbi_host("http://rbi.org.in")

    # Reject lookalikes and attacks
    assert not is_rbi_host("https://rbi.org.in.evil.com/fake")
    assert not is_rbi_host("https://notrbi.org.in/page")
    assert not is_rbi_host("https://google.com")
    assert not is_rbi_host("")
    assert not is_rbi_host(None)


def test_canonicalise_url_and_doc_id():
    url1 = "https://www.rbi.org.in/Scripts/BS_Circulars.aspx?Id=12345#frag"
    url2 = "https://www.rbi.org.in/Scripts/BS_Circulars.aspx?Id=12345"
    assert canonicalise_url(url1) == canonicalise_url(url2)

    doc_id1 = compute_doc_id(canonicalise_url(url1))
    doc_id2 = compute_doc_id(canonicalise_url(url2))
    assert doc_id1 == doc_id2
    assert len(doc_id1) == 16


# Property-based tests
@given(st.text())
def test_normalise_circular_no_never_crashes(text: str):
    res = normalise_circular_no(text)
    assert res is None or isinstance(res, str)


@given(st.text())
def test_parse_issue_date_never_crashes(text: str):
    iso, yr = parse_issue_date(text)
    assert (iso is None and yr is None) or (isinstance(iso, str) and isinstance(yr, int))


@given(st.text())
def test_canonicalise_url_idempotent(text: str):
    c1 = canonicalise_url(text)
    c2 = canonicalise_url(c1)
    assert c1 == c2
