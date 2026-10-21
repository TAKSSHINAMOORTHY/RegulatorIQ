"""Discovery algorithm for Official RBI documents and metadata."""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from bs4 import BeautifulSoup

from config.paths import LEGAL_DOCS_DIR
from config.settings import settings
from ingest.normalise import (
    canonicalise_url,
    compute_doc_id,
    extract_updated_as_on,
    is_rbi_host,
    normalise_circular_no,
    parse_issue_date,
)

logger = logging.getLogger(__name__)

# Primary seed listings and categories
SEED_LISTINGS = {
    "Master Direction": [
        "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336",
        "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=335",
        "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=343",
        "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=344",
        "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=412",
    ],
    "Master Circular": [
        "https://rbi.org.in/scripts/BS_ViewMasterCirculardetails.aspx?did=342",
    ],
    "Circular": [
        "https://website.rbi.org.in/web/rbi/notifications/rbi-circulars",
        "https://rbi.org.in/SCRIPTS/BS_CircularIndexDisplay.aspx?Id=13545",
    ],
    "Notification": [
        "https://rbi.org.in/scripts/BS_CircularIndexDisplay.aspx",
    ],
    "Press Release": [
        "https://rbi.org.in/scripts/BS_PressReleaseDisplay.aspx",
    ],
}

RSS_FEEDS = {
    "Press Release": "https://rbi.org.in/pressreleases_rss.xml",
    "Notification": "https://rbi.org.in/notifications_rss.xml",
    "Speech": "https://www.rbi.org.in/speeches_rss.xml",
    "Publication": "https://www.rbi.org.in/Publication_rss.xml",
}


class RbiRobotGuard:
    """Manages and enforces robots.txt policies across RBI domains."""

    def __init__(self, user_agent: str = "RegulatorIQ-research-bot/1.0"):
        self.user_agent = user_agent
        self.parsers: Dict[str, RobotFileParser] = {}
        self.crawl_delays: Dict[str, float] = {}

    def load_robots(self, host: str, content: str) -> None:
        """Parse robots.txt content directly."""
        rp = RobotFileParser()
        rp.parse(content.splitlines())
        self.parsers[host] = rp

        delay = settings.REQUEST_DELAY_SECONDS
        match = re.search(r"crawl-delay:\s*([\d\.]+)", content, re.IGNORECASE)
        if match:
            try:
                delay = float(match.group(1))
            except ValueError:
                pass
        self.crawl_delays[host] = max(delay, settings.REQUEST_DELAY_SECONDS)

    def fetch_and_save(self, client: httpx.Client, host: str, url: str) -> float:
        """Fetch robots.txt from network, store to docs/legal, and parse."""
        LEGAL_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"robots_{host.replace('.', '_')}.txt"
        target_file = LEGAL_DOCS_DIR / filename
        try:
            resp = client.get(url, timeout=settings.TIMEOUT)
            if resp.status_code == 200:
                content = resp.text
                target_file.write_text(content, encoding="utf-8")
                self.load_robots(host, content)
                logger.info(f"Loaded robots.txt for {host} (saved to {target_file.name})")
            else:
                logger.warning(f"Could not fetch robots.txt from {url}: status {resp.status_code}")
                self.crawl_delays[host] = settings.REQUEST_DELAY_SECONDS
        except Exception as e:
            logger.warning(f"Error fetching robots.txt from {url}: {e}")
            self.crawl_delays[host] = settings.REQUEST_DELAY_SECONDS
        return self.crawl_delays.get(host, settings.REQUEST_DELAY_SECONDS)

    def is_allowed(self, url: str) -> bool:
        """Check if URL is allowed under robots.txt."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        if host in self.parsers:
            return self.parsers[host].can_fetch(self.user_agent, url)
        # Default allow if no robots file available
        return True

    def get_crawl_delay(self, url: str) -> float:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        return self.crawl_delays.get(host, settings.REQUEST_DELAY_SECONDS)


class DocumentCandidate:
    """Represents a discovered official document before full payload download."""

    def __init__(
        self,
        doc_type: str,
        title: str,
        source_page_url: str,
        file_url: str,
        circular_no: Optional[str] = None,
        department: Optional[str] = None,
        issue_date: Optional[str] = None,
        year: Optional[int] = None,
        addressees: Optional[str] = None,
        superseded_hint: Optional[str] = None,
        updated_as_on: Optional[str] = None,
        file_ext: str = "pdf",
    ):
        self.doc_type = doc_type
        self.title = title
        self.source_page_url = source_page_url
        self.file_url = file_url
        self.circular_no = circular_no
        self.circular_no_normalised = normalise_circular_no(circular_no)
        self.department = department
        self.issue_date = issue_date
        self.year = year
        self.addressees = addressees
        self.superseded_hint = superseded_hint
        self.updated_as_on = updated_as_on
        self.file_ext = file_ext
        self.canonical_url = canonicalise_url(file_url or source_page_url)
        self.doc_id = compute_doc_id(self.canonical_url)


def parse_listing_html(html_content: str, base_url: str, doc_type: str) -> List[DocumentCandidate]:
    """Parse table rows and links from RBI listing pages."""
    candidates: List[DocumentCandidate] = []
    soup = BeautifulSoup(
        html_content, "lxml" if "lxml" in BeautifulSoup.__dict__ else "html.parser"
    )

    # Look for tables with links or list items
    links = soup.find_all("a", href=True)
    for a in links:
        raw_href = a.get("href")
        href = str(raw_href).strip() if raw_href else ""
        text = a.get_text(strip=True)
        if not text or len(text) < 5 or not href:
            continue

        full_url = urljoin(base_url, href)
        if not is_rbi_host(full_url):
            continue

        # Detect supersession hint on the anchor or parent row
        parent_row = a.find_parent("tr")
        row_text = parent_row.get_text(" ", strip=True) if parent_row else text
        superseded_hint = None
        if "superseded" in row_text.lower():
            superseded_hint = "Marked as superseded in listing"

        # Determine file extension
        lower_url = full_url.lower()
        if lower_url.endswith(".pdf"):
            ext = "pdf"
        elif lower_url.endswith(".docx"):
            ext = "docx"
        elif lower_url.endswith(".xlsx"):
            ext = "xlsx"
        else:
            ext = "html"

        # Clean title & updated_as_on
        clean_title, updated_date = extract_updated_as_on(text)

        # Detect circular no & issue date
        circ_no = normalise_circular_no(text) or normalise_circular_no(row_text)
        iso_date, year = parse_issue_date(row_text)

        candidate = DocumentCandidate(
            doc_type=doc_type,
            title=clean_title,
            source_page_url=base_url,
            file_url=full_url,
            circular_no=circ_no,
            issue_date=iso_date,
            year=year,
            superseded_hint=superseded_hint,
            updated_as_on=updated_date,
            file_ext=ext,
        )
        candidates.append(candidate)

    return candidates


def parse_rss_feed(feed_content: str, doc_type: str) -> List[DocumentCandidate]:
    """Parse RSS feed entries for recent circulars or notifications."""
    candidates: List[DocumentCandidate] = []
    feed = feedparser.parse(feed_content)

    for entry in feed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", "")
        if not link or not is_rbi_host(link):
            continue

        published = getattr(entry, "published", None) or getattr(entry, "updated", None)
        iso_date, year = parse_issue_date(published)

        clean_title, updated_date = extract_updated_as_on(title)
        circ_no = normalise_circular_no(title)

        candidate = DocumentCandidate(
            doc_type=doc_type,
            title=clean_title,
            source_page_url=link,
            file_url=link,
            circular_no=circ_no,
            issue_date=iso_date,
            year=year,
            updated_as_on=updated_date,
            file_ext="pdf" if link.lower().endswith(".pdf") else "html",
        )
        candidates.append(candidate)

    return candidates
