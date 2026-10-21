"""Unit tests for manifest validation and serialization."""

import pytest
from pydantic import ValidationError

from ingest.manifest import ManifestRecord


def test_manifest_record_valid():
    rec = ManifestRecord(
        doc_id="abcd1234efgh5678",
        doc_type="Master Direction",
        title="Reserve Bank of India Master Direction - KYC",
        source_page_url="https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336",
        file_url="https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx?did=336",
        bytes=50000,
        status="ok",
    )
    assert rec.doc_id == "abcd1234efgh5678"
    assert rec.status == "ok"


def test_manifest_record_invalid_status():
    with pytest.raises(ValidationError):
        ManifestRecord(
            doc_id="abcd1234efgh5678",
            doc_type="Master Direction",
            title="Title",
            source_page_url="https://rbi.org.in",
            file_url="https://rbi.org.in",
            status="unrecognized_status",  # type: ignore
        )
