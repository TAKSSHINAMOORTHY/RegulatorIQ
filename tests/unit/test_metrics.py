"""Unit and property-based tests for evaluation metrics harness."""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from evals.metrics import (
    bootstrap_ci,
    compute_all_gold_found,
    compute_citation_metrics,
    compute_doc_recall_at_k,
    compute_hit_at_k,
    compute_mrr,
    compute_ndcg_at_10,
    compute_recall_at_k,
    contains_answer_key,
    load_eval_weights,
    normalize_dates,
    normalize_numbers_and_currency,
    normalize_text,
    split_into_claims,
)

# ---------------------------------------------------------------------------
# Hand-computed Toy Cases
# ---------------------------------------------------------------------------


def test_retrieval_metrics_toy_cases():
    gold = ["c1", "c2"]
    retrieved = ["c3", "c1", "c4", "c5", "c2"]

    # Recall@k
    assert compute_recall_at_k(retrieved, gold, k=1) == 0.0
    assert compute_recall_at_k(retrieved, gold, k=2) == 0.5  # found c1
    assert compute_recall_at_k(retrieved, gold, k=5) == 1.0  # found c1 and c2

    # Hit@k
    assert compute_hit_at_k(retrieved, gold, k=1) == 0.0
    assert compute_hit_at_k(retrieved, gold, k=2) == 1.0
    assert compute_hit_at_k(retrieved, gold, k=5) == 1.0

    # MRR (first gold chunk c1 is at rank 2 -> 1/2 = 0.5)
    assert compute_mrr(retrieved, gold) == 0.5

    # If first gold chunk at rank 1 -> 1.0
    assert compute_mrr(["c1", "c3"], gold) == 1.0
    # If no gold chunk found -> 0.0
    assert compute_mrr(["c9", "c8"], gold) == 0.0


def test_ndcg_at_10_toy_cases():
    gold = ["c1"]
    # If gold at rank 1: DCG = 1/log2(2) = 1.0, IDCG = 1.0 -> nDCG = 1.0
    assert math.isclose(compute_ndcg_at_10(["c1"], gold), 1.0)

    # If gold at rank 2: DCG = 1/log2(3) = 0.6309, IDCG = 1.0 -> nDCG = 0.6309
    assert math.isclose(compute_ndcg_at_10(["c2", "c1"], gold), 1.0 / math.log2(3))

    # Empty gold -> 1.0
    assert compute_ndcg_at_10(["c1"], []) == 1.0


def test_doc_recall_and_all_gold_found():
    gold_docs = ["d1", "d2"]
    # Only d1 retrieved
    assert compute_doc_recall_at_k(["d1", "d3"], gold_docs, k=2) == 0.5
    assert compute_all_gold_found(["d1", "d3"], gold_docs, k=2) == 0.0

    # Both retrieved
    assert compute_doc_recall_at_k(["d1", "d2"], gold_docs, k=2) == 1.0
    assert compute_all_gold_found(["d1", "d2"], gold_docs, k=2) == 1.0


def test_date_and_number_normalization_table():
    # Dates
    assert normalize_dates("Issued on 11.11.2025.") == "Issued on 2025-11-11."
    assert normalize_dates("Issued on 11-11-2025.") == "Issued on 2025-11-11."
    assert normalize_dates("Dated 11 November 2025.") == "Dated 2025-11-11."
    assert normalize_dates("On November 11, 2025.") == "On 2025-11-11."

    # Currency and numbers
    assert "rs 5 crore" in normalize_numbers_and_currency("Rs. 5 crore")
    assert "rs 5 crore" in normalize_numbers_and_currency("Rs 5 crore")
    assert "rs 5 crore" in normalize_numbers_and_currency("Rs.5 crore")
    assert "rs 5 crore" in normalize_numbers_and_currency("INR 5 crore")

    # Percentages
    assert "5%" in normalize_numbers_and_currency("5 per cent")
    assert "5%" in normalize_numbers_and_currency("5 percent")
    assert "5%" in normalize_numbers_and_currency("5 %")


def test_answer_key_containment():
    answer = (
        "The prescribed threshold was 5% effective 11 November 2025 under circular RBI/2025/10."
    )
    assert contains_answer_key(answer, "5 per cent")
    assert contains_answer_key(answer, "11.11.2025")
    assert contains_answer_key(answer, "RBI/2025/10")

    # Missing key
    assert not contains_answer_key(answer, "10 per cent")


def test_claim_splitter():
    text = "The bank was placed under directions [1]. Depositor withdrawals are capped at Rs 5,000 [1]; this remains in force for six months [2]."
    claims = split_into_claims(text)
    assert len(claims) >= 2
    assert any("placed under directions" in c for c in claims)
    assert any("withdrawals are capped" in c for c in claims)


def test_citation_precision_and_recall():
    gold = ["c1", "c2"]
    # Perfect citations
    prec, rec = compute_citation_metrics(["c1", "c2"], gold)
    assert prec == 1.0 and rec == 1.0

    # Half correct citations
    prec, rec = compute_citation_metrics(["c1", "c99"], gold)
    assert prec == 0.5 and rec == 0.5

    # Invalid citation index (None)
    prec, rec = compute_citation_metrics(["c1", None], gold)
    assert prec == 0.5 and rec == 0.5


def test_bootstrap_ci_reproducible_and_narrow_for_constant():
    # Constant data must yield half_width = 0.0
    res_const = bootstrap_ci([0.8] * 20, seed=42)
    assert math.isclose(res_const.mean, 0.8)
    assert res_const.ci_half_width == 0.0

    # Reproducible with same seed
    vals = [0.1, 0.4, 0.7, 0.9, 0.5, 0.6]
    res1 = bootstrap_ci(vals, seed=123)
    res2 = bootstrap_ci(vals, seed=123)
    assert res1.ci_low == res2.ci_low
    assert res1.ci_high == res2.ci_high


def test_eval_weights_sum_to_one():
    weights = load_eval_weights()
    total = sum(weights.values())
    assert math.isclose(total, 1.0, rel_tol=1e-5), f"Weights sum to {total}, expected 1.0"


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------


@given(
    retrieved=st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=20),
    gold=st.lists(st.text(min_size=1, max_size=5), min_size=1, max_size=5),
)
@settings(max_examples=30, deadline=None)
def test_recall_at_k_monotonic_non_decreasing(retrieved, gold):
    """recall@k must be monotonically non-decreasing in k."""
    r1 = compute_recall_at_k(retrieved, gold, k=1)
    r3 = compute_recall_at_k(retrieved, gold, k=3)
    r5 = compute_recall_at_k(retrieved, gold, k=5)
    r10 = compute_recall_at_k(retrieved, gold, k=10)
    assert 0.0 <= r1 <= r3 <= r5 <= r10 <= 1.0


@given(text=st.text(min_size=1, max_size=100))
@settings(max_examples=30, deadline=None)
def test_text_normalization_idempotent(text):
    """Normalizer must be idempotent: f(f(x)) == f(x)."""
    norm1 = normalize_text(text)
    norm2 = normalize_text(norm1)
    assert norm1 == norm2
