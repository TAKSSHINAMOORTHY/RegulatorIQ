"""Unit tests for relation classification, supersession links, and validity computation."""

from ingest.links import (
    LinkEdge,
    classify_relation_in_window,
    compute_document_validity,
    extract_references_from_text,
)
from ingest.manifest import ManifestRecord


def test_classify_relation_verified_fixtures():
    # Verified fixture 1: "This Master Direction has been superseded"
    assert (
        classify_relation_in_window("This Master Direction has been superseded by new directions")
        == "supersedes"
    )

    # Verified fixture 2: "Master Circulars issued on various subjects will stand withdrawn"
    assert (
        classify_relation_in_window(
            "Master Circulars issued on various subjects will stand withdrawn with the issue of the Master Direction"
        )
        == "withdraws"
    )

    # Amendment fixture
    assert (
        classify_relation_in_window("This notification is an amendment to circular RBI/2024-25/10")
        == "amends"
    )

    # Reference fixture
    assert (
        classify_relation_in_window("Please refer to circular DOR.MCS.REC.59/01.01.003/2025-26")
        == "refers"
    )


def test_classify_relation_negation_window():
    # Negation: "no circular has been superseded" must NOT classify as supersedes
    assert (
        classify_relation_in_window(
            "It is clarified that no circular has been superseded by this letter"
        )
        is None
    )

    # "not amended"
    assert (
        classify_relation_in_window(
            "The provisions of paragraph 5 remain unchanged and not amended"
        )
        is None
    )


def test_extract_references():
    text = (
        "In supersession of circular RBI/2024-25/12, the new norms are issued. "
        "Also reference is invited to DOR.MCS.REC.59/01.01.003/2025-26."
    )
    known = {
        "RBI/2024-25/12": "doc_old_1",
        "DOR.MCS.REC.59/01.01.003/2025-26": "doc_ref_2",
    }
    edges = extract_references_from_text(
        text=text,
        doc_id="doc_new_main",
        known_circulars=known,
        known_titles={},
    )
    assert len(edges) == 2
    e1 = next(e for e in edges if e.dst_ref_text == "RBI/2024-25/12")
    assert e1.relation == "supersedes"
    assert e1.resolved is True
    assert e1.dst_doc_id == "doc_old_1"

    e2 = next(e for e in edges if "DOR.MCS.REC.59" in e.dst_ref_text)
    assert e2.relation == "refers"
    assert e2.resolved is True


def test_validity_computation_and_cycles():
    r_old = ManifestRecord(
        doc_id="doc_old",
        doc_type="Circular",
        title="Old KYC Circular",
        circular_no="RBI/2024-25/10",
        circular_no_normalised="RBI/2024-25/10",
        issue_date="2024-01-01",
        source_page_url="https://rbi.org.in/old",
        file_url="https://rbi.org.in/old.pdf",
    )
    r_new = ManifestRecord(
        doc_id="doc_new",
        doc_type="Master Direction",
        title="New KYC Direction",
        circular_no="RBI/2025-26/01",
        circular_no_normalised="RBI/2025-26/01",
        issue_date="2025-01-01",
        source_page_url="https://rbi.org.in/new",
        file_url="https://rbi.org.in/new.pdf",
    )

    edge_supersedes = LinkEdge(
        src_doc_id="doc_new",
        relation="supersedes",
        dst_ref_text="RBI/2024-25/10",
        dst_doc_id="doc_old",
        evidence_text="In supersession of RBI/2024-25/10",
        resolved=True,
    )

    validity_info, anomalies = compute_document_validity([r_old, r_new], [edge_supersedes])

    assert validity_info["doc_old"]["is_current"] is False
    assert validity_info["doc_old"]["valid_to"] == "2025-01-01"
    assert validity_info["doc_new"]["is_current"] is True
    assert len(anomalies) == 0

    # Test cycle detection: add mutual edge
    edge_cycle = LinkEdge(
        src_doc_id="doc_old",
        relation="supersedes",
        dst_ref_text="RBI/2025-26/01",
        dst_doc_id="doc_new",
        evidence_text="Contradictory claim",
        resolved=True,
    )
    _, anomalies_detected = compute_document_validity([r_old, r_new], [edge_supersedes, edge_cycle])
    assert len(anomalies_detected) > 0
