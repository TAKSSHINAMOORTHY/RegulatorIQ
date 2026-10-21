"""Live test against official RBI servers (marked with @pytest.mark.live)."""

import httpx
import pytest

from ingest.discover import RbiRobotGuard, parse_rss_feed
from ingest.normalise import is_rbi_host


@pytest.mark.live
def test_live_robots_and_rss_smoke():
    guard = RbiRobotGuard()
    with httpx.Client(
        timeout=15.0, headers={"User-Agent": "RegulatorIQ-research-bot/1.0"}
    ) as client:
        # Check robots.txt
        try:
            resp = client.get("https://www.rbi.org.in/robots.txt")
            if resp.status_code == 200:
                guard.load_robots("rbi.org.in", resp.text)
                assert guard.is_allowed(
                    "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx"
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            pytest.skip("Offline or cannot connect to official RBI server")

        # Check RSS feed
        try:
            rss_resp = client.get("https://rbi.org.in/notifications_rss.xml")
            if rss_resp.status_code == 200:
                candidates = parse_rss_feed(rss_resp.text, "Notification")
                assert len(candidates) > 0
                for c in candidates[:3]:
                    assert is_rbi_host(c.file_url)
        except (httpx.ConnectError, httpx.TimeoutException):
            pytest.skip("Offline or cannot reach RBI RSS feed")
