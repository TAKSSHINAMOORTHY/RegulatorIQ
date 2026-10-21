"""Unit tests for section hierarchy, metadata enrichment, and deduplication."""

from ingest.parse.models import ParsedDocument, ParsedPage
from ingest.structure import (
    Deduplicator,
    detect_section_tree,
    extract_applicability_entities,
    extract_effective_date,
    match_topics,
)


def test_detect_section_tree():
    sample_text = (
        "CHAPTER I\nPreliminary\n\n"
        "1. Short title and commencement\n"
        "These directions shall be called RBI Directions, 2025.\n\n"
        "2. Definitions\n"
        "(a) 'Bank' means a banking company.\n"
        "(b) 'Borrower' means an entity receiving credit.\n\n"
        "CHAPTER II\nCapital Requirements\n\n"
        "5. Capital Adequacy\n"
        "5.2 Minimum CRAR\n"
        "(a) The minimum CRAR shall be 9%.\n\n"
        "ANNEX I\nCalculation Table"
    )
    parsed = ParsedDocument(
        doc_id="doc123",
        pages=[ParsedPage(page_no=1, text=sample_text, blocks=[])],
        full_text=sample_text,
    )
    sections, confidence = detect_section_tree(parsed)
    assert len(sections) >= 4
    assert confidence in ("high", "medium")

    paths = [s.section_path for s in sections]
    assert any("CHAPTER I" in p for p in paths)
    assert any("CHAPTER II" in p for p in paths)
    assert any("Capital Requirements" in p for p in paths)


def test_extract_effective_date():
    text = "These directions shall come into effect from 01-04-2025 across all banks."
    eff = extract_effective_date(text)
    assert eff == "2025-04-01"

    text2 = "with effect from November 11, 2025."
    eff2 = extract_effective_date(text2)
    assert eff2 == "2025-11-11"


def test_extract_applicability_entities():
    text = "These directions apply to all Scheduled Commercial Banks and Non-Banking Financial Companies (NBFCs)."
    entities = extract_applicability_entities(text)
    assert "Commercial Banks" in entities
    assert "NBFCs" in entities


def test_match_topics():
    text = "The borrower must complete KYC verification before digital lending disbursement and maintain CRAR 9%."
    topics = match_topics(text)
    assert "kyc_aml" in topics
    assert "digital_lending" in topics
    assert "capital_adequacy" in topics


def test_deduplicator():
    dedup = Deduplicator(threshold=0.9)
    doc1 = "The Reserve Bank of India issues Master Direction on KYC norms."
    doc2 = "The Reserve Bank of India issues Master Direction on KYC norms."
    doc3 = "Different directions on Foreign Exchange Management and LRS scheme."

    assert dedup.check_duplicate("id1", doc1) is None
    # doc2 is exact duplicate of id1
    assert dedup.check_duplicate("id2", doc2) == "id1"
    assert dedup.check_duplicate("id3", doc3) is None
