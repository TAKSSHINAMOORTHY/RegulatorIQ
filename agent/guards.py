"""Input safety guardrails: prompt-injection detection, PII redaction, scope checks, advice refusal.

Deterministic, zero-LLM pre-flight filter enforcing security, privacy, and regulatory boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional, Tuple

import yaml

from config.paths import CONFIG_DIR, INJECTION_PATTERNS_PATH


@dataclass
class GuardOutcome:
    """Outcome produced by the guard node."""

    status: Literal["allow", "refuse", "allow_with_redaction"]
    clean_text: str
    refusal_reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def luhn_checksum_valid(card_num_str: str) -> bool:
    """Validate numeric card string using Luhn algorithm."""
    digits = [int(c) for c in card_num_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


class SafetyGuard:
    """Pre-flight safety, PII, and injection filter."""

    def __init__(
        self,
        max_length: int = 1500,
        patterns_path: Optional[Path] = None,
        out_of_scope_path: Optional[Path] = None,
    ) -> None:
        self.max_length = max_length
        self.patterns_path = patterns_path or INJECTION_PATTERNS_PATH
        self.out_of_scope_path = out_of_scope_path or (CONFIG_DIR / "out_of_scope.yaml")

        self.injection_regexes: List[re.Pattern] = []
        self.advice_regexes: List[re.Pattern] = []
        self.out_of_scope_regexes: List[re.Pattern] = []

        self._load_patterns()

    def _load_patterns(self) -> None:
        if self.patterns_path.exists():
            with open(self.patterns_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                for p in data.get("injection_patterns", []):
                    self.injection_regexes.append(re.compile(p))
                for p in data.get("advice_patterns", []):
                    self.advice_regexes.append(re.compile(p))

        if self.out_of_scope_path.exists():
            with open(self.out_of_scope_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                for p in data.get("patterns", []):
                    self.out_of_scope_regexes.append(re.compile(p))

    def sanitize_control_characters(self, text: str) -> str:
        """Strip non-printable control characters except newline and tab."""
        # Remove null bytes and control chars (except \n, \r, \t)
        return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    def redact_pii(self, text: str) -> Tuple[str, List[str]]:
        """Detect and redact Aadhaar, PAN, payment card numbers, email, phone."""
        clean = text
        warnings: List[str] = []

        # 1. Email addresses
        email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
        if email_pattern.search(clean):
            warnings.append("PII detected: email address redacted")
            clean = email_pattern.sub("[EMAIL REDACTED]", clean)

        # 2. Indian Phone numbers (+91 or 10 digits starting with 6-9)
        phone_pattern = re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b")
        if phone_pattern.search(clean):
            warnings.append("PII detected: phone number redacted")
            clean = phone_pattern.sub("[PHONE REDACTED]", clean)

        # 3. PAN card format: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)
        pan_pattern = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
        if pan_pattern.search(clean):
            warnings.append("PII detected: PAN number redacted")
            clean = pan_pattern.sub("[PAN REDACTED]", clean)

        # 4. Credit/Debit card numbers (13-19 digits with spaces or hyphens)
        raw_card_candidates = re.findall(r"\b(?:\d[ -]*?){13,19}\b", clean)
        for cand in raw_card_candidates:
            num_only = re.sub(r"\D", "", cand)
            if luhn_checksum_valid(num_only):
                warnings.append("PII detected: credit/debit card number redacted")
                clean = clean.replace(cand, "[CARD REDACTED]")

        # 5. Aadhaar-like 12 digits: e.g. 1234 5678 9012 or 123456789012 (not part of circular e.g. 2024-25)
        aadhaar_pattern = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
        if aadhaar_pattern.search(clean):
            warnings.append("PII detected: Aadhaar number redacted")
            clean = aadhaar_pattern.sub("[AADHAAR REDACTED]", clean)

        return clean, warnings

    def check(self, raw_text: str) -> GuardOutcome:
        """Run complete deterministic guardrails checks on input."""
        if not raw_text or not raw_text.strip():
            return GuardOutcome(
                status="refuse",
                clean_text="",
                refusal_reason="Empty question received. Please ask a regulatory compliance question regarding official RBI directives.",
            )

        # 1. Length limit check
        if len(raw_text) > self.max_length:
            return GuardOutcome(
                status="refuse",
                clean_text=raw_text[: self.max_length],
                refusal_reason=f"Question exceeds maximum permitted length of {self.max_length} characters.",
            )

        # 2. Control characters sanitation
        sanitized = self.sanitize_control_characters(raw_text).strip()

        # 3. Prompt injection checks
        for regex in self.injection_regexes:
            if regex.search(sanitized):
                return GuardOutcome(
                    status="refuse",
                    clean_text=sanitized,
                    refusal_reason="Question rejected by security policy: prompt override, injection pattern, or system-level query detected.",
                    warnings=["prompt_injection_detected"],
                )

        # 4. Personal financial/investment advice checks
        for regex in self.advice_regexes:
            if regex.search(sanitized):
                return GuardOutcome(
                    status="refuse",
                    clean_text=sanitized,
                    refusal_reason="RegulatorIQ provides compliance analysis of official RBI directives and cannot offer personal financial, investment, or loan approval advice.",
                    warnings=["personal_advice_request"],
                )

        # 5. Out of scope checks
        for regex in self.out_of_scope_regexes:
            if regex.search(sanitized):
                return GuardOutcome(
                    status="refuse",
                    clean_text=sanitized,
                    refusal_reason="Question is outside the regulatory scope of the Reserve Bank of India (RBI). RegulatorIQ only answers queries regarding official RBI circulars, notifications, and master directions.",
                    warnings=["out_of_scope_detected"],
                )

        # 6. PII redaction
        clean_text, pii_warnings = self.redact_pii(sanitized)
        if pii_warnings:
            return GuardOutcome(
                status="allow_with_redaction",
                clean_text=clean_text,
                warnings=pii_warnings,
            )

        return GuardOutcome(status="allow", clean_text=clean_text)


_DEFAULT_GUARD: Optional[SafetyGuard] = None


def redact_pii(text: str) -> Tuple[str, List[str]]:
    """Convenience module function for PII redaction using default SafetyGuard."""
    global _DEFAULT_GUARD
    if _DEFAULT_GUARD is None:
        _DEFAULT_GUARD = SafetyGuard()
    return _DEFAULT_GUARD.redact_pii(text)
