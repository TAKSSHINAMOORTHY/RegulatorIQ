"""Unit tests for MetadataStore, boolean allow-mask pre-filtering, and TextBlobStore."""

import numpy as np

from retrieval.store import (
    Filters,
    MetadataStore,
    build_metadata_store_from_chunks,
    parse_date_to_days,
)


def test_parse_date_to_days():
    days = parse_date_to_days("1970-01-01")
    assert days == 0
    days2 = parse_date_to_days("2025-01-01")
    assert days2 > 19000
    assert parse_date_to_days(None) == -1
    assert parse_date_to_days("invalid") == -1


def test_metadata_store_and_filters(tmp_path):
    chunks = [
        {
            "chunk_id": "c1",
            "doc_id": "doc1",
            "ordinal": 1,
            "text": "First chunk text about KYC rules for commercial banks",
            "doc_type": "Circular",
            "title": "KYC Circular",
            "circular_no": "RBI/2024-25/10",
            "issue_date": "2024-05-10",
            "valid_from": "2024-05-10",
            "valid_to": None,
            "is_current": True,
            "validity_confidence": "high",
            "topics": ["kyc_aml"],
            "applicability_entities": ["commercial_banks"],
            "source_url": "https://rbi.org.in/circ1.pdf",
            "token_count": 120,
        },
        {
            "chunk_id": "c2",
            "doc_id": "doc2",
            "ordinal": 1,
            "text": "Second chunk text about superseded lending directions",
            "doc_type": "Master Direction",
            "title": "Old Lending Directions",
            "circular_no": "RBI/2021-22/05",
            "issue_date": "2021-02-15",
            "valid_from": "2021-02-15",
            "valid_to": "2024-01-01",
            "is_current": False,
            "validity_confidence": "high",
            "topics": ["digital_lending"],
            "applicability_entities": ["nbfcs"],
            "source_url": "https://rbi.org.in/circ2.pdf",
            "token_count": 200,
        },
        {
            "chunk_id": "c3",
            "doc_id": "doc1",
            "ordinal": 2,
            "text": "Third chunk text continued from doc1",
            "doc_type": "Circular",
            "title": "KYC Circular",
            "circular_no": "RBI/2024-25/10",
            "issue_date": "2024-05-10",
            "valid_from": "2024-05-10",
            "valid_to": None,
            "is_current": True,
            "validity_confidence": "high",
            "topics": ["kyc_aml"],
            "applicability_entities": ["commercial_banks"],
            "source_url": "https://rbi.org.in/circ1.pdf",
            "token_count": 80,
        },
    ]

    meta_dir = tmp_path / "meta"
    store = build_metadata_store_from_chunks(chunks, meta_dir)
    assert len(store) == 3

    # Test chunk retrieval by ID and text decompression
    c1 = store.get_chunk("c1")
    assert c1 is not None
    assert c1.doc_id == "doc1"
    assert "KYC rules" in c1.text
    assert c1.is_current is True

    # Test Filter 1: is_current
    mask_curr = store.build_allow_mask(Filters(is_current=True))
    assert list(mask_curr) == [True, False, True]

    mask_old = store.build_allow_mask(Filters(is_current=False))
    assert list(mask_old) == [False, True, False]

    # Test Filter 2: doc_type
    mask_md = store.build_allow_mask(Filters(doc_type=["Master Direction"]))
    assert list(mask_md) == [False, True, False]

    # Test Filter 3: issue_date range
    mask_date = store.build_allow_mask(Filters(issue_date_after="2023-01-01"))
    assert list(mask_date) == [True, False, True]

    # Test Filter 4: circular_no exact match
    mask_cno = store.build_allow_mask(Filters(circular_no="RBI/2024-25/10"))
    assert list(mask_cno) == [True, False, True]

    # Test Filter 5: conflicting filters -> empty result
    mask_conflict = store.build_allow_mask(Filters(doc_type=["Notification"]))
    assert not np.any(mask_conflict)

    # Persistence reload check
    loaded_store = MetadataStore.load(meta_dir)
    assert len(loaded_store) == 3
    loaded_c3 = loaded_store.get_chunk("c3")
    assert loaded_c3 is not None
    assert "Third chunk" in loaded_c3.text
