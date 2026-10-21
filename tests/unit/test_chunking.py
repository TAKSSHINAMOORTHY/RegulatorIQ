"""Unit and property-based tests for chunking and token splitting."""

from hypothesis import given, settings
from hypothesis import strategies as st

from ingest.manifest import ManifestRecord
from ingest.parse.models import ParsedDocument, ParsedPage
from ingest.structure import SectionNode
from retrieval.chunking import (
    TokenCounter,
    build_contextual_header,
    chunk_document,
    chunk_section,
    split_sentences_safely,
)


def test_split_sentences_protected_patterns():
    text = (
        "The penalty is Rs. 5 crore under Circular No. 12. "
        "The applicant must submit KYC documents, i.e. passport or Aadhaar. "
        "The revised norms take effect on 11.11.2025 across all banks."
    )
    sentences = split_sentences_safely(text)
    assert len(sentences) == 3
    assert "Rs. 5 crore" in sentences[0]
    assert "No. 12" in sentences[0]
    assert "i.e." in sentences[1]
    assert "11.11.2025" in sentences[2]


def test_token_counter_approx_fallback():
    tc = TokenCounter(model_name="non_existent_fake_model")
    count = tc.count("This is a simple sentence with seven words.")
    assert count > 5
    assert tc.is_fallback is True
    assert tc.label == "approx"


def test_build_contextual_header():
    header = build_contextual_header(
        doc_type="Master Direction",
        title="KYC Directions 2025",
        circular_no="RBI/2025-26/90",
        issue_date="2025-11-11",
        section_path="Chapter II > Section 5",
    )
    assert "[Master Direction] KYC Directions 2025" in header
    assert "RBI/2025-26/90" in header
    assert "2025-11-11" in header
    assert "Chapter II > Section 5" in header


def test_chunk_section_token_cap():
    tc = TokenCounter()
    long_text = " ".join(["The Reserve Bank of India mandates minimum CRAR of 9% for banks."] * 40)
    sec = SectionNode(
        title="Capital",
        section_path="Chapter II > Capital",
        text=long_text,
    )
    chunks = chunk_section(sec, tc, target_tokens=200, max_tokens=250)
    assert len(chunks) > 1
    for chunk_text, tok_count, _ in chunks:
        assert tok_count <= 250


def test_chunk_document_deterministic():
    tc = TokenCounter()
    manifest = ManifestRecord(
        doc_id="doc_test_123",
        doc_type="Circular",
        title="Digital Lending Guidelines",
        circular_no="RBI/2025-26/10",
        source_page_url="https://rbi.org.in/test",
        file_url="https://rbi.org.in/test.pdf",
    )
    parsed = ParsedDocument(
        doc_id="doc_test_123",
        pages=[ParsedPage(page_no=1, text="Paragraph 1 text.\n\nParagraph 2 text.")],
        full_text="Paragraph 1 text.\n\nParagraph 2 text.",
    )
    sec1 = SectionNode(title="Intro", section_path="Intro", text="Paragraph 1 text.")
    sec2 = SectionNode(title="Rules", section_path="Rules", text="Paragraph 2 text.")

    chunks1 = chunk_document(
        parsed=parsed,
        manifest=manifest,
        sections=[sec1, sec2],
        validity_info={"is_current": True},
        topics=["digital_lending"],
        entities=["Commercial Banks"],
        token_counter=tc,
    )
    chunks2 = chunk_document(
        parsed=parsed,
        manifest=manifest,
        sections=[sec1, sec2],
        validity_info={"is_current": True},
        topics=["digital_lending"],
        entities=["Commercial Banks"],
        token_counter=tc,
    )

    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.chunk_id == c2.chunk_id
        assert c1.text == c2.text
        assert c1.token_count <= 512
        assert c1.source_url.startswith("https://rbi.org.in")


# Property-based hypothesis tests
@settings(max_examples=30, deadline=None)
@given(
    st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=50),
        min_size=1,
        max_size=20,
    )
)
def test_chunker_never_exceeds_max_tokens(words_list: list[str]):
    text = ". ".join(words_list) + "."
    sec = SectionNode(title="T", section_path="P", text=text)
    tc = TokenCounter()
    chunks = chunk_section(sec, tc, target_tokens=100, max_tokens=150)
    for _, tokens, _ in chunks:
        # hard token limit respected
        assert tokens <= 150
