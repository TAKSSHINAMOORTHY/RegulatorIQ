"""Integration test verifying crawler against simulated RBI endpoints without network."""

import httpx
import pytest
import respx

from ingest.discover import DocumentCandidate, RbiRobotGuard
from ingest.download import CircuitBreaker, PoliteDownloader


@pytest.fixture
def mock_rbi_env():
    with respx.mock(base_url="https://www.rbi.org.in", assert_all_called=False) as respx_mock:
        # 1. Robots.txt
        respx_mock.get("/robots.txt").respond(
            200,
            text="User-agent: *\nDisallow: /admin/\nCrawl-delay: 0.1\n",
        )

        # 2. Listing page with valid and truncated PDF links
        listing_html = """
        <html>
            <body>
                <table class="tablebg">
                    <tr>
                        <td><a href="/Scripts/valid.pdf">Master Direction - KYC 2025</a></td>
                    </tr>
                    <tr>
                        <td><a href="/Scripts/truncated.pdf">Circular on NPAs</a></td>
                    </tr>
                    <tr>
                        <td><a href="https://external-domain.com/evil.pdf">Off Domain</a></td>
                    </tr>
                </table>
            </body>
        </html>
        """
        respx_mock.get("/Scripts/BS_ViewMasterDirections.aspx?did=336").respond(
            200,
            text=listing_html,
        )

        # 3. Valid PDF (>100 bytes, starts with %PDF)
        valid_pdf_content = b"%PDF-1.4\n" + b"A" * 200 + b"\n%%EOF"
        respx_mock.get("/Scripts/valid.pdf").respond(
            200,
            content=valid_pdf_content,
        )

        # 4. Truncated PDF (doesn't start with %PDF)
        respx_mock.get("/Scripts/truncated.pdf").respond(
            200,
            content=b"CORRUPT DATA",
        )

        # 5. Rate limited endpoint
        respx_mock.get("/Scripts/blocked.pdf").respond(429)

        yield respx_mock


def test_crawl_integration(mock_rbi_env, tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.download.RAW_RBI_DIR", tmp_path / "raw" / "rbi")
    monkeypatch.setattr("ingest.manifest.MANIFEST_JSONL_PATH", tmp_path / "manifest.jsonl")

    guard = RbiRobotGuard()
    breaker = CircuitBreaker(block_threshold=2, max_trips=1, pause_seconds=0.01)

    with httpx.Client(base_url="https://www.rbi.org.in") as client:
        guard.fetch_and_save(client, "www.rbi.org.in", "https://www.rbi.org.in/robots.txt")
        downloader = PoliteDownloader(
            robot_guard=guard,
            circuit_breaker=breaker,
            client=client,
            sleep_enabled=False,
        )

        # Test valid candidate download
        cand_valid = DocumentCandidate(
            doc_type="Master Direction",
            title="Master Direction - KYC 2025",
            source_page_url="https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336",
            file_url="https://www.rbi.org.in/Scripts/valid.pdf",
            year=2025,
            file_ext="pdf",
        )
        rec_valid = downloader.download_candidate(cand_valid)
        assert rec_valid.status == "ok"
        assert rec_valid.bytes > 100

        # Test truncated candidate download
        cand_trunc = DocumentCandidate(
            doc_type="Circular",
            title="Circular on NPAs",
            source_page_url="https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336",
            file_url="https://www.rbi.org.in/Scripts/truncated.pdf",
            year=2025,
            file_ext="pdf",
        )
        rec_trunc = downloader.download_candidate(cand_trunc)
        assert rec_trunc.status == "failed"

        # Test rate limit & circuit breaker
        cand_block = DocumentCandidate(
            doc_type="Circular",
            title="Rate Limited Doc",
            source_page_url="https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336",
            file_url="https://www.rbi.org.in/Scripts/blocked.pdf",
            year=2025,
            file_ext="pdf",
        )
        downloader.download_candidate(cand_block)
        rec_blocked2 = downloader.download_candidate(cand_block)
        assert rec_blocked2.status in ("blocked", "skipped")
