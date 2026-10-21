"""Unit tests for the ingest CLI."""

import respx
from typer.testing import CliRunner

from ingest.cli import app

runner = CliRunner()


def test_cli_acquire_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.download.RAW_RBI_DIR", tmp_path / "raw" / "rbi")
    monkeypatch.setattr("ingest.manifest.MANIFEST_JSONL_PATH", tmp_path / "manifest.jsonl")
    monkeypatch.setattr("ingest.manifest.MANIFEST_PARQUET_PATH", tmp_path / "manifest.parquet")
    monkeypatch.setattr("ingest.report.MANIFEST_JSONL_PATH", tmp_path / "manifest.jsonl")
    monkeypatch.setattr("ingest.report.CORPUS_REPORT_MD", tmp_path / "report.md")
    monkeypatch.setattr("ingest.report.CORPUS_REPORT_JSON", tmp_path / "report.json")

    with respx.mock(base_url="https://www.rbi.org.in", assert_all_called=False) as respx_mock:
        respx_mock.get("/robots.txt").respond(200, text="User-agent: *\nAllow: /\n")
        respx_mock.get("/Scripts/Disclaimer.aspx").respond(200, text="Official RBI Disclaimer")

        # Run dry run with max-docs 0
        result = runner.invoke(app, ["acquire", "--max-docs", "0", "--dry-run"])
        assert result.exit_code == 0
        assert "Corpus Acquisition" in result.output
