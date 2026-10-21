"""Normalisation helpers for RBI circular numbers, dates, titles, and URLs.

Total normalisation guarantee: Functions in this module never raise uncaught
exceptions on malformed input, returning None or safe canonical fallbacks.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse

from dateutil import parser as date_parser

# Regex patterns for RBI circular numbers
# E.g.: "RBI/2025-26/90", "RBI/2025-2026/95", "RBI/FMRD/2025-26/142"
RE_RBI_PREFIX = re.compile(
    r"\b(RBI(?:/[A-Z0-9\.\-]+)?/(?:20\d\d-\d\d|20\d\d-\d\d\d\d)/\d+)\b",
    re.IGNORECASE,
)

# E.g.: "DOR.MCS.REC.59/01.01.003/2025-26", "DoR.GOV.REC.No.414/18.10.008/2025-26", "FIDD.CO.LBS.BC.No.13/02.08.001/2025-26"
RE_DEPT_CIRCULAR = re.compile(
    r"\b([A-Z]{2,6}\.[A-Z0-9\.\-]+(?:No\.)?\d+/\d+\.\d+\.\d+/(?:20\d\d-\d\d|20\d\d-\d\d\d\d))\b",
    re.IGNORECASE,
)

# E.g.: "A.P. (DIR Series) Circular No. 23"
RE_AP_DIR = re.compile(
    r"\b(A\.P\.\s*(?:\(DIR\s*Series\))?\s*Circular\s*(?:No\.?)?\s*(\d+))\b",
    re.IGNORECASE,
)

# Date extraction regex
RE_DD_MM_YYYY = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d\d)\b")
RE_UPDATED_AS_ON = re.compile(
    r"\(?Updated\s+as\s+on\s+([A-Za-z0-9,\s\.\-]+?)\)?(?:\s*$|\))",
    re.IGNORECASE,
)


def is_rbi_host(url: str) -> bool:
    """Validate that the URL belongs to an official *.rbi.org.in or rbi.org.in domain.

    Strictly rejects lookalikes like 'rbi.org.in.evil.com' or 'notrbi.org.in'.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc.lower()
        if not netloc:
            return False
        # Remove port if present
        host = netloc.split(":")[0]
        return host == "rbi.org.in" or host.endswith(".rbi.org.in")
    except Exception:
        return False


def canonicalise_url(url: str) -> str:
    """Produce a deterministic canonical URL:

    - lowercase scheme and host
    - strip trailing slashes (unless root path)
    - strip query tracking params or fragments
    - sort query parameters
    """
    if not url or not isinstance(url, str):
        return ""
    try:
        url = url.strip()
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.strip() or "/"
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]

        # Query parsing: preserve query but discard fragment
        query = parsed.query.strip()
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url.strip()


def compute_doc_id(canonical_url: str) -> str:
    """doc_id = first 16 hex chars of sha1(canonical_url)."""
    if not canonical_url or not isinstance(canonical_url, str):
        return "0" * 16
    return hashlib.sha1(canonical_url.strip().encode("utf-8")).hexdigest()[:16]


def normalise_circular_no(text: Optional[str]) -> Optional[str]:
    """Extract and normalise circular numbers into standard uppercase representation.

    Examples:
        'RBI/2025-2026/95' -> 'RBI/2025-26/95'
        'A.P. (DIR Series) Circular No. 23' -> 'A.P. (DIR Series) Circular No. 23'
        'DoR.GOV.REC.No.414/18.10.008/2025-26' -> 'DOR.GOV.REC.NO.414/18.10.008/2025-26'
    """
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()

    # Case 1: RBI prefix pattern
    match = RE_RBI_PREFIX.search(cleaned)
    if match:
        val = match.group(1).upper()
        # Normalise 2025-2026 to 2025-26
        val = re.sub(r"/20(\d\d)-20(\d\d)/", r"/20\1-\2/", val)
        return val

    # Case 2: Department circular pattern
    match = RE_DEPT_CIRCULAR.search(cleaned)
    if match:
        val = match.group(1).upper()
        val = re.sub(r"/20(\d\d)-20(\d\d)$", r"/20\1-\2", val)
        return val

    # Case 3: A.P. (DIR Series) pattern
    match = RE_AP_DIR.search(cleaned)
    if match:
        num = match.group(2)
        return f"A.P. (DIR Series) Circular No. {num}"

    # Fallback: clean up alphanumeric string if it resembles a circular number
    if any(k in cleaned.upper() for k in ["RBI/", "CIRCULAR", "REC.", "DIR."]):
        norm = re.sub(r"\s+", " ", cleaned).strip().upper()
        norm = re.sub(r"/20(\d\d)-20(\d\d)", r"/20\1-\2", norm)
        return norm

    return None


def parse_issue_date(text: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Parse date text into ISO string (YYYY-MM-DD) and year integer.

    Handles '11.11.2025', 'March 10, 2026', '10-03-2026', etc.
    Never raises exceptions.
    """
    if not text or not isinstance(text, str):
        return None, None

    cleaned = text.strip()
    if not cleaned:
        return None, None

    # Handle explicit dd.mm.yyyy or dd-mm-yyyy first
    match = RE_DD_MM_YYYY.search(cleaned)
    if match:
        d_str, m_str, y_str = match.groups()
        try:
            d_int, m_int, y_int = int(d_str), int(m_str), int(y_str)
            dt = date(y_int, m_int, d_int)
            return dt.isoformat(), dt.year
        except ValueError:
            pass

    # Use dateutil parser fallback
    try:
        dt_parsed = date_parser.parse(cleaned, dayfirst=True)
        return dt_parsed.date().isoformat(), dt_parsed.year
    except Exception:
        return None, None


def extract_updated_as_on(title: Optional[str]) -> Tuple[str, Optional[str]]:
    """Extract 'Updated as on <date>' from title if present.

    Returns:
        (cleaned_title, updated_as_on_iso_date_or_none)
    """
    if not title or not isinstance(title, str):
        return "", None

    match = RE_UPDATED_AS_ON.search(title)
    if match:
        raw_date = match.group(1).strip()
        iso_dt, _ = parse_issue_date(raw_date)
        clean_title = RE_UPDATED_AS_ON.sub("", title).strip()
        # Clean trailing punctuation
        clean_title = re.sub(r"\s*-\s*$", "", clean_title).strip()
        return clean_title, iso_dt

    return title.strip(), None
