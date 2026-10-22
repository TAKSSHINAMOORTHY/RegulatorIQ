"""Feedback Storage and Ingestion for RegulatorIQ.

Accepts user ratings ('up'/'down') and comments. Enforces PII redaction on
submitted comments, handles multiple storage backends (JSONL, SQLite, None),
and bridges feedback scores to Langfuse traces when enabled.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from agent.guards import redact_pii
from api.schemas import FeedbackRequest

logger = logging.getLogger("regulatoriq.feedback")


class FeedbackStore:
    """Manages persistent storage of user feedback."""

    def __init__(self, sink_type: str = "jsonl", file_path: Optional[Path] = None):
        self.sink_type = sink_type.lower()
        self.file_path = file_path
        self.lock = threading.Lock()

        if self.file_path and self.sink_type != "none":
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            if self.sink_type == "sqlite":
                self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Create feedback table in SQLite database."""
        assert self.file_path is not None
        with sqlite3.connect(str(self.file_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    reason TEXT,
                    comment TEXT,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_feedback(self, req: FeedbackRequest, client_hash: str) -> None:
        """Persist feedback record after redacting potential PII."""
        if self.sink_type == "none":
            return

        # Redact any PII in user comments
        clean_comment = None
        if req.comment:
            clean_comment, _ = redact_pii(req.comment)

        record: Dict[str, Any] = {
            "request_id": req.request_id,
            "rating": req.rating,
            "reason": req.reason,
            "comment": clean_comment,
            "client_hash": client_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self.lock:
            if self.sink_type == "sqlite" and self.file_path:
                try:
                    with sqlite3.connect(str(self.file_path)) as conn:
                        conn.execute(
                            "INSERT INTO feedback (request_id, rating, reason, comment, timestamp) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (
                                req.request_id,
                                req.rating,
                                req.reason,
                                clean_comment,
                                record["timestamp"],
                            ),
                        )
                        conn.commit()
                except Exception as e:
                    logger.error(f"Failed to save feedback to sqlite: {e}")
            elif self.file_path:
                try:
                    # Append JSONL with 10MB rotation
                    if self.file_path.exists() and self.file_path.stat().st_size > 10 * 1024 * 1024:
                        rot = self.file_path.parent / f"feedback_{int(time.time())}.jsonl"
                        self.file_path.rename(rot)

                    with open(self.file_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record) + "\n")
                except Exception as e:
                    logger.error(f"Failed to append feedback to jsonl: {e}")
