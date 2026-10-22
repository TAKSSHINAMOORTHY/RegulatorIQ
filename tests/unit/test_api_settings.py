"""Unit tests for API settings validation and production safeguards."""

import pytest
from pydantic import ValidationError

from api.settings import APISettings


def test_settings_defaults():
    s = APISettings(ENV="dev")
    assert s.PORT == 8000
    assert s.MAX_BODY_BYTES == 16384
    assert s.MAX_QUESTION_CHARS == 1000
    assert s.MAX_CONCURRENT_ASKS == 2
    assert s.FEEDBACK_SINK == "jsonl"


def test_cors_wildcard_fails_in_prod():
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS cannot contain"):
        APISettings(ENV="prod", CORS_ALLOWED_ORIGINS="*,http://example.com")


def test_cors_wildcard_allowed_in_dev():
    s = APISettings(ENV="dev", CORS_ALLOWED_ORIGINS="*")
    assert "*" in s.cors_origins_list


def test_docs_enabled_in_prod_requires_override():
    with pytest.raises(ValueError, match="DOCS_ENABLED=1 requires ALLOW_DOCS_IN_PROD=1"):
        APISettings(ENV="prod", DOCS_ENABLED=1, ALLOW_DOCS_IN_PROD=0)

    # Allowed with explicit override
    s = APISettings(ENV="prod", DOCS_ENABLED=1, ALLOW_DOCS_IN_PROD=1)
    assert s.DOCS_ENABLED == 1


def test_bad_env_fails():
    with pytest.raises(ValidationError):
        APISettings(ENV="invalid_environment_name")


def test_bad_feedback_sink_fails():
    with pytest.raises(ValidationError):
        APISettings(ENV="dev", FEEDBACK_SINK="unsupported_sink")


def test_parsed_lists():
    s = APISettings(
        ENV="dev",
        CORS_ALLOWED_ORIGINS="http://localhost:3000, https://app.example.com ",
        TRUSTED_PROXIES="10.0.0.1, 10.0.0.2 ",
        API_KEYS="key1, key2",
    )
    assert s.cors_origins_list == ["http://localhost:3000", "https://app.example.com"]
    assert s.trusted_proxies_list == ["10.0.0.1", "10.0.0.2"]
    assert s.api_keys_list == ["key1", "key2"]
