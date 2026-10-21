"""Manifest schema, validation, and serialization for RBI documents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from config.paths import MANIFEST_JSONL_PATH, MANIFEST_PARQUET_PATH

StatusType = Literal["ok", "skipped", "failed", "blocked"]


class ManifestRecord(BaseModel):
    """Schema for a single scraped/acquired RBI document row in the manifest."""

    doc_id: str = Field(..., description="First 16 hex chars of sha1(canonical_url)")
    doc_type: str = Field(
        ..., description="e.g. Master Direction, Circular, Notification, Press Release"
    )
    title: str = Field(..., description="Title of the circular or document")
    circular_no: Optional[str] = Field(default=None, description="Raw circular number")
    circular_no_normalised: Optional[str] = Field(
        default=None, description="Standardised uppercase circular number"
    )
    department: Optional[str] = Field(default=None, description="Issuing RBI department")
    issue_date: Optional[str] = Field(
        default=None, description="ISO formatted issue date YYYY-MM-DD"
    )
    year: Optional[int] = Field(default=None, description="Issue year as integer")
    addressees: Optional[str] = Field(
        default=None, description="Target entities (e.g. All Commercial Banks)"
    )
    source_page_url: str = Field(
        ..., description="URL of the listing or detail page on *.rbi.org.in"
    )
    file_url: str = Field(..., description="URL of the actual downloadable file or canonical page")
    file_ext: str = Field(default="pdf", description="File extension: pdf, html, docx, xlsx")
    local_path: Optional[str] = Field(default=None, description="Relative path in data/raw/rbi/...")
    http_status: Optional[int] = Field(default=None, description="HTTP response code")
    bytes: int = Field(default=0, description="Payload size in bytes")
    sha256: Optional[str] = Field(default=None, description="SHA-256 hash of payload")
    fetched_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="ISO timestamp of acquisition",
    )
    robots_allowed: bool = Field(
        default=True, description="Whether robots.txt allowed crawling this URL"
    )
    status: StatusType = Field(default="ok", description="Status: ok | skipped | failed | blocked")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    superseded_hint: Optional[str] = Field(
        default=None,
        description="Text fragment like 'This Master Direction has been superseded' if present on the page",
    )
    updated_as_on: Optional[str] = Field(
        default=None,
        description="Date string if title says 'Updated as on ...'",
    )


def append_manifest_record(record: ManifestRecord) -> None:
    """Append a single record atomically to the JSONL manifest."""
    MANIFEST_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def load_manifest_records() -> List[ManifestRecord]:
    """Load all records from the JSONL manifest."""
    if not MANIFEST_JSONL_PATH.exists():
        return []
    records: List[ManifestRecord] = []
    with open(MANIFEST_JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(ManifestRecord.model_validate_json(line))
    return records


def export_manifest_parquet() -> Path:
    """Export the JSONL manifest to data/manifests/rbi_manifest.parquet (zstd compressed)."""
    records = load_manifest_records()
    if not records:
        df = pd.DataFrame(columns=list(ManifestRecord.model_fields.keys()))
    else:
        df = pd.DataFrame([r.model_dump() for r in records])

    MANIFEST_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(MANIFEST_PARQUET_PATH, compression="zstd", index=False)
    return MANIFEST_PARQUET_PATH
