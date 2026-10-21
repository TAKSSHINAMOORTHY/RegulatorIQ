"""Polite downloader with jitter, atomic disk persistence, and circuit breakers."""

from __future__ import annotations

import hashlib
import logging
import random
import time
from pathlib import Path
from typing import Optional

import httpx

from config.paths import RAW_RBI_DIR
from config.settings import settings
from ingest.discover import DocumentCandidate, RbiRobotGuard
from ingest.manifest import ManifestRecord, append_manifest_record

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker tracking consecutive 403/429 blocks from official servers."""

    def __init__(self, block_threshold: int = 20, max_trips: int = 3, pause_seconds: float = 900.0):
        self.block_threshold = block_threshold
        self.max_trips = max_trips
        self.pause_seconds = pause_seconds
        self.consecutive_blocks = 0
        self.breaker_trips = 0
        self.listing_only_mode = False

    def record_success(self) -> None:
        self.consecutive_blocks = 0

    def record_block(self) -> bool:
        """Record a 403 or 429 response. Returns True if breaker tripped."""
        self.consecutive_blocks += 1
        if self.consecutive_blocks >= self.block_threshold:
            self.breaker_trips += 1
            self.consecutive_blocks = 0
            if self.breaker_trips >= self.max_trips:
                self.listing_only_mode = True
                logger.error(
                    f"Circuit breaker tripped {self.breaker_trips} times! Switching to listing-only mode."
                )
            else:
                logger.warning(
                    f"Circuit breaker tripped (trip #{self.breaker_trips}). Pausing for {self.pause_seconds}s..."
                )
            return True
        return False


class PoliteDownloader:
    """Manages polite, jittered downloads with atomic disk persistence."""

    def __init__(
        self,
        robot_guard: Optional[RbiRobotGuard] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        client: Optional[httpx.Client] = None,
        sleep_enabled: bool = True,
    ):
        self.robot_guard = robot_guard or RbiRobotGuard()
        self.breaker = circuit_breaker or CircuitBreaker()
        self.sleep_enabled = sleep_enabled
        self.client = client or httpx.Client(
            http2=True,
            timeout=settings.TIMEOUT,
            headers={"User-Agent": f"RegulatorIQ-research-bot/1.0 (+{settings.CRAWLER_CONTACT})"},
            follow_redirects=True,
        )

    def _sleep_with_jitter(self, base_delay: float) -> None:
        """Sleep with +- 20% jitter to prevent artificial synchronization."""
        if not self.sleep_enabled:
            return
        jitter = random.uniform(0.8, 1.2)
        sleep_time = max(0.05, base_delay * jitter)
        time.sleep(sleep_time)

    def _target_file_path(self, candidate: DocumentCandidate) -> Path:
        """data/raw/rbi/<doc_type>/<year>/<doc_id>.<ext>."""
        safe_type = candidate.doc_type.replace(" ", "_").lower()
        year_str = str(candidate.year or "undated")
        ext = candidate.file_ext or "pdf"
        dest_dir = RAW_RBI_DIR / safe_type / year_str
        dest_dir.mkdir(parents=True, exist_ok=True)
        return dest_dir / f"{candidate.doc_id}.{ext}"

    def download_candidate(self, candidate: DocumentCandidate) -> ManifestRecord:
        """Download candidate payload, verify integrity, and save atomically."""
        from config.paths import ROOT

        target_path = self._target_file_path(candidate)
        try:
            rel_path = str(target_path.relative_to(ROOT))
        except ValueError:
            rel_path = str(target_path)

        # Check robots.txt
        if not self.robot_guard.is_allowed(candidate.file_url):
            logger.warning(f"Robots.txt disallowed: {candidate.file_url}")
            record = ManifestRecord(
                doc_id=candidate.doc_id,
                doc_type=candidate.doc_type,
                title=candidate.title,
                circular_no=candidate.circular_no,
                circular_no_normalised=candidate.circular_no_normalised,
                department=candidate.department,
                issue_date=candidate.issue_date,
                year=candidate.year,
                addressees=candidate.addressees,
                source_page_url=candidate.source_page_url,
                file_url=candidate.file_url,
                file_ext=candidate.file_ext,
                local_path=rel_path,
                robots_allowed=False,
                status="blocked",
                error="Disallowed by robots.txt",
                superseded_hint=candidate.superseded_hint,
                updated_as_on=candidate.updated_as_on,
            )
            append_manifest_record(record)
            return record

        # Check circuit breaker
        if self.breaker.listing_only_mode:
            record = ManifestRecord(
                doc_id=candidate.doc_id,
                doc_type=candidate.doc_type,
                title=candidate.title,
                circular_no=candidate.circular_no,
                circular_no_normalised=candidate.circular_no_normalised,
                department=candidate.department,
                issue_date=candidate.issue_date,
                year=candidate.year,
                addressees=candidate.addressees,
                source_page_url=candidate.source_page_url,
                file_url=candidate.file_url,
                file_ext=candidate.file_ext,
                local_path=rel_path,
                status="skipped",
                error="Listing-only mode active due to circuit breaker",
                superseded_hint=candidate.superseded_hint,
                updated_as_on=candidate.updated_as_on,
            )
            append_manifest_record(record)
            return record

        # Respect crawl delay
        delay = self.robot_guard.get_crawl_delay(candidate.file_url)
        self._sleep_with_jitter(delay)

        try:
            resp = self.client.get(candidate.file_url)
            status_code = resp.status_code

            # Check 401/403/429
            if status_code in (403, 429):
                tripped = self.breaker.record_block()
                if tripped and not self.breaker.listing_only_mode:
                    time.sleep(min(self.breaker.pause_seconds, 1.0))
                record = ManifestRecord(
                    doc_id=candidate.doc_id,
                    doc_type=candidate.doc_type,
                    title=candidate.title,
                    circular_no=candidate.circular_no,
                    circular_no_normalised=candidate.circular_no_normalised,
                    department=candidate.department,
                    issue_date=candidate.issue_date,
                    year=candidate.year,
                    addressees=candidate.addressees,
                    source_page_url=candidate.source_page_url,
                    file_url=candidate.file_url,
                    file_ext=candidate.file_ext,
                    local_path=rel_path,
                    http_status=status_code,
                    status="blocked",
                    error=f"Server returned HTTP {status_code}",
                    superseded_hint=candidate.superseded_hint,
                    updated_as_on=candidate.updated_as_on,
                )
                append_manifest_record(record)
                return record

            if status_code != 200:
                record = ManifestRecord(
                    doc_id=candidate.doc_id,
                    doc_type=candidate.doc_type,
                    title=candidate.title,
                    circular_no=candidate.circular_no,
                    circular_no_normalised=candidate.circular_no_normalised,
                    department=candidate.department,
                    issue_date=candidate.issue_date,
                    year=candidate.year,
                    addressees=candidate.addressees,
                    source_page_url=candidate.source_page_url,
                    file_url=candidate.file_url,
                    file_ext=candidate.file_ext,
                    local_path=rel_path,
                    http_status=status_code,
                    status="failed",
                    error=f"HTTP status {status_code}",
                    superseded_hint=candidate.superseded_hint,
                    updated_as_on=candidate.updated_as_on,
                )
                append_manifest_record(record)
                return record

            # Validate payload integrity
            content = resp.content
            payload_bytes = len(content)
            sha256_hash = hashlib.sha256(content).hexdigest()

            # PDF validation: starts with %PDF and > 1KB
            if candidate.file_ext == "pdf":
                if not content.startswith(b"%PDF") or payload_bytes < 100:
                    record = ManifestRecord(
                        doc_id=candidate.doc_id,
                        doc_type=candidate.doc_type,
                        title=candidate.title,
                        circular_no=candidate.circular_no,
                        circular_no_normalised=candidate.circular_no_normalised,
                        department=candidate.department,
                        issue_date=candidate.issue_date,
                        year=candidate.year,
                        addressees=candidate.addressees,
                        source_page_url=candidate.source_page_url,
                        file_url=candidate.file_url,
                        file_ext=candidate.file_ext,
                        local_path=rel_path,
                        http_status=status_code,
                        bytes=payload_bytes,
                        status="failed",
                        error="Invalid PDF header or truncated payload",
                        superseded_hint=candidate.superseded_hint,
                        updated_as_on=candidate.updated_as_on,
                    )
                    append_manifest_record(record)
                    return record

            # Atomic file save
            temp_path = target_path.with_suffix(".tmp")
            temp_path.write_bytes(content)
            temp_path.replace(target_path)

            self.breaker.record_success()

            record = ManifestRecord(
                doc_id=candidate.doc_id,
                doc_type=candidate.doc_type,
                title=candidate.title,
                circular_no=candidate.circular_no,
                circular_no_normalised=candidate.circular_no_normalised,
                department=candidate.department,
                issue_date=candidate.issue_date,
                year=candidate.year,
                addressees=candidate.addressees,
                source_page_url=candidate.source_page_url,
                file_url=candidate.file_url,
                file_ext=candidate.file_ext,
                local_path=rel_path,
                http_status=status_code,
                bytes=payload_bytes,
                sha256=sha256_hash,
                status="ok",
                superseded_hint=candidate.superseded_hint,
                updated_as_on=candidate.updated_as_on,
            )
            append_manifest_record(record)
            return record

        except Exception as e:
            record = ManifestRecord(
                doc_id=candidate.doc_id,
                doc_type=candidate.doc_type,
                title=candidate.title,
                circular_no=candidate.circular_no,
                circular_no_normalised=candidate.circular_no_normalised,
                department=candidate.department,
                issue_date=candidate.issue_date,
                year=candidate.year,
                addressees=candidate.addressees,
                source_page_url=candidate.source_page_url,
                file_url=candidate.file_url,
                file_ext=candidate.file_ext,
                local_path=rel_path,
                status="failed",
                error=str(e),
                superseded_hint=candidate.superseded_hint,
                updated_as_on=candidate.updated_as_on,
            )
            append_manifest_record(record)
            return record
