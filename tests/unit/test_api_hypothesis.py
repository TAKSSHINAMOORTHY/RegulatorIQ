"""Property-based tests for FastAPI API using Hypothesis."""

import json

from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from api.main import create_app
from api.security import is_allowed_rbi_url, sanitize_text
from api.settings import APISettings
from api.sse import format_sse_event


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=50)
def test_hypothesis_sanitizer_safety(raw_text):
    sanitized = sanitize_text(raw_text)
    assert isinstance(sanitized, str)
    # Check that known forbidden secrets/paths are not left unredacted
    assert "sk-" not in sanitized or "[REDACTED" in sanitized


@given(st.text(min_size=1, max_size=100), st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50)))
@settings(max_examples=50)
def test_hypothesis_sse_encoder_roundtrip(event_type, payload):
    frame = format_sse_event(event_type, payload, event_id=1)
    assert frame.startswith("id: 1\n")
    assert f"event: {event_type}\n" in frame
    assert frame.endswith("\n\n")

    # Extract data line and assert valid json
    data_line = [l for l in frame.split("\n") if l.startswith("data: ")][0]
    json_part = data_line[len("data: ") :]
    parsed = json.loads(json_part)
    assert isinstance(parsed, dict)
