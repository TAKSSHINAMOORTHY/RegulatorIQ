"""Text cleaning rules for RBI regulatory documents.

Each cleaning rule is deterministic and independently unit-testable.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Tuple

# Common ligature replacements
LIGATURES: Dict[str, str] = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
}

# Regex to detect de-hyphenation across line breaks: "regula-\ntion" -> "regulation"
RE_DEHYPHEN = re.compile(r"([A-Za-z]{2,})-\s*\n\s*([A-Za-z]{2,})")

# Boilerplate letterhead fragments often at top of RBI circulars
RE_LETTERHEAD = re.compile(
    r"(?:RESERVE\s+BANK\s+OF\s+INDIA|भारतीय\s+रिज़र्व\s+बैंक|"
    r"Central\s+Office|Shahid\s+Bhagat\s+Singh\s+Road|Mumbai\s*[-–]\s*400\s*001|"
    r"Department\s+of\s+Regulation|Department\s+of\s+Banking\s+Operations|"
    r"Foreign\s+Exchange\s+Department|Financial\s+Inclusion\s+and\s+Development\s+Department|"
    r"www\.rbi\.org\.in|helpdoc@rbi\.org\.in)",
    re.IGNORECASE,
)

# Numbering and clause markers
RE_NUMBERED_ITEM = re.compile(r"^\s*(\d+(?:\.\d+)*|[A-Za-z]\.|\([a-z0-9]+\))\s+", re.MULTILINE)


def clean_unicode(text: str) -> str:
    """Normalize unicode with NFKC, fix ligatures and soft hyphens."""
    if not text:
        return ""
    # Replace soft hyphens
    text = text.replace("\xad", "")
    for lig, replacement in LIGATURES.items():
        text = text.replace(lig, replacement)
    return unicodedata.normalize("NFKC", text)


def dehyphenate(text: str) -> str:
    """De-hyphenate line breaks only when the joined word is purely alphabetic."""
    if not text:
        return ""
    return RE_DEHYPHEN.sub(r"\1\2", text)


def remove_letterhead_boilerplate(text: str) -> Tuple[str, List[str]]:
    """Remove RBI name/address header boilerplate from the document body.

    Returns:
        (cleaned_body, extracted_boilerplate_lines)
    """
    if not text:
        return "", []

    lines = text.splitlines()
    body_lines: List[str] = []
    boilerplate: List[str] = []
    header_zone = True

    for i, line in enumerate(lines):
        clean_line = line.strip()
        # Header zone typically ends after first 20 lines or when substantial content starts
        if i > 25:
            header_zone = False

        if header_zone and RE_LETTERHEAD.search(clean_line):
            boilerplate.append(clean_line)
        else:
            # If line is not pure boilerplate, add to body
            body_lines.append(line)

    return "\n".join(body_lines), boilerplate


def remove_repeating_headers_footers(pages: List[str]) -> List[str]:
    """Remove repeating header/footer lines that recur on >= 60% of pages with the same text

    after digit masking.
    """
    if not pages or len(pages) < 2:
        return pages

    total_pages = len(pages)
    line_counts: Dict[str, int] = {}

    def mask_digits(s: str) -> str:
        return re.sub(r"\d+", "<NUM>", s.strip().lower())

    for page in pages:
        seen_on_page: set[str] = set()
        for line in page.splitlines():
            clean = line.strip()
            if len(clean) > 3:
                masked = mask_digits(clean)
                seen_on_page.add(masked)
        for m in seen_on_page:
            line_counts[m] = line_counts.get(m, 0) + 1

    repeating_masked = {m for m, count in line_counts.items() if (count / total_pages) >= 0.60}

    cleaned_pages: List[str] = []
    for page in pages:
        kept_lines: List[str] = []
        for line in page.splitlines():
            clean = line.strip()
            # Remove bare page numbers
            if re.match(r"^\s*[-–—]?\s*\d+\s*[-–—]?\s*$", clean):
                continue
            if mask_digits(clean) in repeating_masked:
                continue
            kept_lines.append(line)
        cleaned_pages.append("\n".join(kept_lines))

    return cleaned_pages


def normalise_spacing(text: str) -> str:
    """Collapse excess horizontal whitespace while strictly preserving paragraph breaks."""
    if not text:
        return ""
    paragraphs = re.split(r"\n\s*\n", text)
    cleaned_paras: List[str] = []
    for p in paragraphs:
        # Collapse multiple spaces and tabs within paragraph lines
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in p.splitlines()]
        joined = " ".join(lines).strip()
        if joined:
            cleaned_paras.append(joined)
    return "\n\n".join(cleaned_paras)


def compute_quality_score(text: str) -> float:
    """Compute document quality score (0..1) based on alpha ratio, line length sanity,

    and replacement characters.
    """
    if not text or len(text.strip()) == 0:
        return 0.0

    total_chars = len(text)
    alpha_chars = sum(1 for c in text if c.isalpha())
    alpha_ratio = alpha_chars / total_chars

    # Check for unicode replacement chars or garbage
    replacement_chars = text.count("\ufffd") + text.count("???")
    garbage_ratio = replacement_chars / max(1, total_chars)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        avg_line_len = sum(len(line) for line in lines) / len(lines)
        line_sanity = 1.0 if 20 <= avg_line_len <= 150 else 0.7
    else:
        line_sanity = 0.0

    score = 0.5 * alpha_ratio + 0.3 * line_sanity + 0.2 * max(0.0, 1.0 - garbage_ratio * 10)
    return max(0.0, min(1.0, round(score, 3)))
