"""Metric validity tests verifying harness calibration, oracle upper bounds, and failure modes."""

from __future__ import annotations

import pytest

from agent.selfcheck import SelfChecker
from dataclasses import dataclass

@dataclass
class MockChunk:
    text: str
    chunk_id: str = "chk_crr"
    source_url: str = "https://www.rbi.org.in/crr"


def test_selfcheck_flags_wrong_number_100_percent() -> None:
    """SelfChecker must flag a deliberately fabricated number with 100% precision."""
    checker = SelfChecker()

    # Evidence has CRR of 4.5%
    evidence_chunks = [
        MockChunk(
            text="The Reserve Bank of India mandates that Cash Reserve Ratio (CRR) shall be 4.50 percent of NDTL."
        )
    ]

    # Draft answer invents 18.25%
    bad_draft = "The Reserve Bank of India mandates that Cash Reserve Ratio (CRR) shall be 18.25 percent [1]."
    report = checker.audit(bad_draft, evidence_chunks)

    assert not report.passed
    assert len(report.hard_check_failures) > 0
    assert any("18" in str(fail) for fail in report.hard_check_failures)


def test_selfcheck_passes_grounded_numbers() -> None:
    """SelfChecker must pass correctly cited numbers present in evidence."""
    checker = SelfChecker()

    evidence_chunks = [
        MockChunk(
            text="The Reserve Bank of India mandates that Cash Reserve Ratio (CRR) shall be 4.50 percent of NDTL."
        )
    ]

    good_draft = "The Reserve Bank of India mandates that Cash Reserve Ratio (CRR) shall be 4.50 percent [1]."
    report = checker.audit(good_draft, evidence_chunks)
    assert report.passed
    assert len(report.hard_check_failures) == 0


def test_oracle_vs_refusal_metrics() -> None:
    """Validate behavior of always-refuse and oracle configurations."""
    # Always refuse scenario
    answerable_labels = [True, True, True, False, False]
    refusal_decisions = [True, True, True, True, True]

    # Metrics on always-refuse:
    # refusal_accuracy on unanswerable (last 2): 2 / 2 = 1.0
    unans_total = sum(1 for a in answerable_labels if not a)
    unans_refused = sum(1 for a, r in zip(answerable_labels, refusal_decisions) if not a and r)
    refusal_accuracy = unans_refused / unans_total
    assert refusal_accuracy == 1.0

    # false_refusal_rate on answerable (first 3): 3 / 3 = 1.0
    ans_total = sum(1 for a in answerable_labels if a)
    ans_refused = sum(1 for a, r in zip(answerable_labels, refusal_decisions) if a and r)
    false_refusal_rate = ans_refused / ans_total
    assert false_refusal_rate == 1.0
