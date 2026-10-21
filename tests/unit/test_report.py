"""Unit tests for corpus report generation."""

from ingest.manifest import ManifestRecord, append_manifest_record
from ingest.report import generate_corpus_report


def test_generate_corpus_report(tmp_path, monkeypatch):
    jsonl_path = tmp_path / "manifest.jsonl"
    md_path = tmp_path / "corpus_report.md"
    json_path = tmp_path / "corpus_report.json"

    monkeypatch.setattr("ingest.manifest.MANIFEST_JSONL_PATH", jsonl_path)
    monkeypatch.setattr("ingest.report.MANIFEST_JSONL_PATH", jsonl_path)
    monkeypatch.setattr("ingest.report.CORPUS_REPORT_MD", md_path)
    monkeypatch.setattr("ingest.report.CORPUS_REPORT_JSON", json_path)

    r1 = ManifestRecord(
        doc_id="0123456789abcdef",
        doc_type="Master Direction",
        title="KYC Norms",
        source_page_url="https://rbi.org.in/page",
        file_url="https://rbi.org.in/file.pdf",
        bytes=1024,
        year=2025,
        status="ok",
    )
    r2 = ManifestRecord(
        doc_id="abcdef0123456789",
        doc_type="Circular",
        title="Priority Sector Lending",
        source_page_url="https://rbi.org.in/page2",
        file_url="https://rbi.org.in/file2.pdf",
        bytes=2048,
        year=2024,
        status="ok",
    )
    append_manifest_record(r1)
    append_manifest_record(r2)

    report = generate_corpus_report(target_count=2)
    assert report["successful_documents"] == 2
    assert report["target_met"] is True
    assert md_path.exists()
    assert json_path.exists()
