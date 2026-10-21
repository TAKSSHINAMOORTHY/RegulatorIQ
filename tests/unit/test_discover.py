"""Unit tests for discovery logic and parsing helpers."""

from ingest.discover import (
    RbiRobotGuard,
    parse_listing_html,
    parse_rss_feed,
)


def test_parse_listing_html():
    html = """
    <html>
        <body>
            <table>
                <tr>
                    <td><a href="/Scripts/BS_ViewMasterDirections.aspx?id=10">Master Direction - KYC Directions, 2025 (Updated as on March 10, 2026)</a></td>
                    <td>DOR.AML.REC.12/2025-26</td>
                </tr>
                <tr>
                    <td><a href="/Scripts/superseded_circular.pdf">Master Circular on Housing Finance (superseded)</a></td>
                    <td>DBOD.No.Dir.BC.13/2024-25</td>
                </tr>
            </table>
        </body>
    </html>
    """
    candidates = parse_listing_html(html, "https://www.rbi.org.in/listing", "Master Direction")
    assert len(candidates) == 2
    c1, c2 = candidates[0], candidates[1]

    assert "Master Direction - KYC Directions, 2025" in c1.title
    assert c1.updated_as_on == "2026-03-10"
    assert c1.doc_type == "Master Direction"

    assert c2.superseded_hint is not None
    assert c2.file_ext == "pdf"


def test_parse_rss_feed():
    rss = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
        <channel>
            <title>RBI Notifications</title>
            <item>
                <title>RBI/2025-26/90 - Special Liquidity Facility</title>
                <link>https://www.rbi.org.in/Scripts/Notification.pdf</link>
                <pubDate>11 Nov 2025 10:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>
    """
    candidates = parse_rss_feed(rss, "Notification")
    assert len(candidates) == 1
    c = candidates[0]
    assert c.circular_no_normalised == "RBI/2025-26/90"
    assert c.file_ext == "pdf"
    assert c.doc_type == "Notification"


def test_robot_guard_policy():
    guard = RbiRobotGuard(user_agent="RegulatorIQ-research-bot/1.0")
    robots_txt = """
    User-agent: *
    Disallow: /private/
    Crawl-delay: 3.0
    """
    guard.load_robots("rbi.org.in", robots_txt)

    assert guard.is_allowed("https://rbi.org.in/public/circular.pdf")
    assert not guard.is_allowed("https://rbi.org.in/private/secret.pdf")
    assert guard.get_crawl_delay("https://rbi.org.in/public/circular.pdf") == 3.0
