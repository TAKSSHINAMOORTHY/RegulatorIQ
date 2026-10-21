"""Unit test for process pipeline execution."""

from ingest.process import run_full_processing


def test_run_full_processing_smoke(tmp_path, monkeypatch):
    # Tests that run_full_processing completes and writes parquet outputs
    monkeypatch.setattr("ingest.process.DOCUMENTS_PATH", tmp_path / "documents.parquet")
    monkeypatch.setattr("ingest.process.LINKS_PATH", tmp_path / "links.parquet")
    monkeypatch.setattr("ingest.process.CHUNKS_PATH", tmp_path / "chunks.parquet")
    monkeypatch.setattr("ingest.process.PARSE_REPORT_JSON", tmp_path / "parse_report.json")
    monkeypatch.setattr("ingest.process.PARSE_REPORT_MD", tmp_path / "parse_report.md")

    report = run_full_processing()
    assert report["doc_count"] > 0
    assert report["chunk_count"] > 0
    assert (tmp_path / "documents.parquet").exists()
    assert (tmp_path / "chunks.parquet").exists()
