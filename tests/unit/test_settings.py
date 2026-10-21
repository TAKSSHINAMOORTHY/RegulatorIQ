"""Unit tests for settings validation."""

import pytest
from pydantic import ValidationError

from config.settings import Settings


def test_default_settings():
    s = Settings()
    assert "rbi.org.in" in s.CRAWLER_CONTACT or "github.com" in s.CRAWLER_CONTACT
    assert s.REQUEST_DELAY_SECONDS >= 0.1
    assert s.MAX_CONCURRENCY in (1, 2)


def test_settings_validation_errors():
    with pytest.raises(ValidationError):
        # Concurrency above hard cap of 2
        Settings(MAX_CONCURRENCY=5)

    with pytest.raises(ValidationError):
        # Negative delay
        Settings(REQUEST_DELAY_SECONDS=-1.0)
