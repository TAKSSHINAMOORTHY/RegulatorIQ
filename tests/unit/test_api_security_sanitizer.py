"""Unit tests for Output Sanitizer and URL Allowlist."""

from api.security import is_allowed_rbi_url, sanitize_citations, sanitize_text


def test_is_allowed_rbi_url():
    # Valid official RBI domains
    assert is_allowed_rbi_url("https://rbi.org.in")
    assert is_allowed_rbi_url("https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12111")
    assert is_allowed_rbi_url("https://m.rbi.org.in/docs")
    assert is_allowed_rbi_url("http://sub.department.rbi.org.in/page")

    # Disallowed external and look-alike domains
    assert not is_allowed_rbi_url("https://rbi.org.in.evil.com/phish")
    assert not is_allowed_rbi_url("https://evil-rbi.org.in")
    assert not is_allowed_rbi_url("https://google.com")
    assert not is_allowed_rbi_url("https://notrbi.org.in")
    assert not is_allowed_rbi_url("javascript:alert(1)")


def test_sanitize_text_urls():
    text = (
        "Check official rules at https://www.rbi.org.in/guidelines. "
        "Also visit phishing site https://rbi.org.in.fake.com/steal or https://google.com."
    )
    cleaned = sanitize_text(text)
    assert "https://www.rbi.org.in/guidelines" in cleaned
    assert "fake.com" not in cleaned
    assert "google.com" not in cleaned
    assert "[UNVERIFIED_EXTERNAL_LINK_REMOVED]" in cleaned


def test_sanitize_text_secrets():
    text = (
        "Here is my key: AIzaSyD3fake1234567890123456789012345 "
        "and Groq key: gsk_123456789012345678901234567890123456789012345678 "
        "and OpenAI: sk-12345678901234567890123456789012"
    )
    cleaned = sanitize_text(text)
    assert "AIzaSy" not in cleaned
    assert "gsk_" not in cleaned
    assert "sk-" not in cleaned
    assert "[REDACTED_API_KEY]" in cleaned


def test_sanitize_text_file_paths():
    text = "Error occurred in /Users/datchu/Projects/secret.py or /var/log/syslog"
    cleaned = sanitize_text(text)
    assert "/Users/datchu" not in cleaned
    assert "/var/log" not in cleaned
    assert "[SYSTEM_PATH_REDACTED]" in cleaned


def test_sanitize_citations():
    citations = [
        {"source_url": "https://www.rbi.org.in/circulars/123", "title": "Valid"},
        {"source_url": "https://evil.com/phish", "title": "Phishing"},
    ]
    clean_cits = sanitize_citations(citations)
    assert clean_cits[0]["source_url"] == "https://www.rbi.org.in/circulars/123"
    assert clean_cits[1]["source_url"] == "https://www.rbi.org.in"
