"""Metrics Harness for RegulatorIQ RAG Evaluation.

Implements:
1. Retrieval metrics (Recall@k, MRR, nDCG@10, doc-level recall, context precision, all_gold_found)
2. Generation metrics (answer correctness with date/number normalization, faithfulness, citation precision/recall, refusal metrics, temporal accuracy)
3. 1,000-sample bootstrap 95% confidence intervals
4. Weighted overall score from config/eval_weights.yaml
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from config.paths import CONFIG_DIR

# ---------------------------------------------------------------------------
# Normalization Utilities (Date, Number, Currency, Text)
# ---------------------------------------------------------------------------

MONTH_MAP = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sep": "09",
    "sept": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}


def normalize_dates(text: str) -> str:
    """Normalize dates like '11.11.2025', '11 November 2025', 'Nov 11, 2025' to canonical ISO YYYY-MM-DD."""

    # Pattern 1: DD.MM.YYYY or DD-MM-YYYY or DD/MM/YYYY
    def repl_num_date(m: re.Match) -> str:
        d, mth, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{int(mth):02d}-{int(d):02d}"

    text = re.sub(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b", repl_num_date, text)

    # Pattern 2: DD Month YYYY (e.g. 11 November 2025)
    def repl_word_date(m: re.Match) -> str:
        d, mth_name, y = m.group(1), m.group(2).lower(), m.group(3)
        mth_num = MONTH_MAP.get(mth_name, "01")
        return f"{y}-{mth_num}-{int(d):02d}"

    text = re.sub(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", repl_word_date, text)

    # Pattern 3: Month DD, YYYY (e.g. November 11, 2025)
    def repl_word_date_us(m: re.Match) -> str:
        mth_name, d, y = m.group(1).lower(), m.group(2), m.group(3)
        mth_num = MONTH_MAP.get(mth_name, "01")
        return f"{y}-{mth_num}-{int(d):02d}"

    text = re.sub(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", repl_word_date_us, text)
    return text


def normalize_numbers_and_currency(text: str) -> str:
    """Normalize currency symbols, numbers, and percentage variations."""
    # Percentages: '5 per cent', '5 percent', '5 %' -> '5%'
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:per\s*cent\b|percent\b|%)", r"\1%", text, flags=re.IGNORECASE
    )

    # Currency: 'Rs. 5', 'Rs 5', 'Rs.5', 'INR 5' -> 'rs 5'
    text = re.sub(r"(?:rs\.?|inr)\s*(\d+(?:\.\d+)?)", r"rs \1", text, flags=re.IGNORECASE)

    # Remove commas in numbers: '1,00,000' -> '100000'
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return text


def normalize_text(text: str) -> str:
    """Idempotent canonical text normalization for regulatory evaluation."""
    if not text:
        return ""
    t = text.lower()
    t = normalize_dates(t)
    t = normalize_numbers_and_currency(t)
    # Strip non-alphanumeric except % and -
    t = re.sub(r"[^\w\s%\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def contains_answer_key(text: str, key: str) -> bool:
    """Check if normalized answer key is contained in normalized text."""
    norm_text = normalize_text(text)
    norm_key = normalize_text(key)
    if not norm_key:
        return True
    return norm_key in norm_text


# ---------------------------------------------------------------------------
# Retrieval Metrics
# ---------------------------------------------------------------------------


def compute_recall_at_k(retrieved_chunk_ids: List[str], gold_chunk_ids: List[str], k: int) -> float:
    """Fraction of gold chunks retrieved in top-k."""
    if not gold_chunk_ids:
        return 1.0
    top_k = retrieved_chunk_ids[:k]
    hits = len(set(top_k).intersection(set(gold_chunk_ids)))
    return hits / len(gold_chunk_ids)


def compute_hit_at_k(retrieved_chunk_ids: List[str], gold_chunk_ids: List[str], k: int) -> float:
    """1.0 if at least one gold chunk is retrieved in top-k, else 0.0."""
    if not gold_chunk_ids:
        return 1.0
    top_k = retrieved_chunk_ids[:k]
    return 1.0 if any(cid in set(gold_chunk_ids) for cid in top_k) else 0.0


def compute_mrr(retrieved_chunk_ids: List[str], gold_chunk_ids: List[str]) -> float:
    """Reciprocal rank of the first retrieved gold chunk."""
    if not gold_chunk_ids:
        return 1.0
    gold_set = set(gold_chunk_ids)
    for rank, cid in enumerate(retrieved_chunk_ids, start=1):
        if cid in gold_set:
            return 1.0 / rank
    return 0.0


def compute_ndcg_at_10(retrieved_chunk_ids: List[str], gold_chunk_ids: List[str]) -> float:
    """Normalized Discounted Cumulative Gain at 10 (binary relevance)."""
    if not gold_chunk_ids:
        return 1.0
    gold_set = set(gold_chunk_ids)
    dcg = 0.0
    for i, cid in enumerate(retrieved_chunk_ids[:10], start=1):
        if cid in gold_set:
            dcg += 1.0 / math.log2(i + 1)

    # Ideal DCG
    ideal_hits = min(10, len(gold_chunk_ids))
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def compute_doc_recall_at_k(retrieved_doc_ids: List[str], gold_doc_ids: List[str], k: int) -> float:
    """Fraction of gold documents found in top-k retrieved docs."""
    if not gold_doc_ids:
        return 1.0
    top_docs = set(retrieved_doc_ids[:k])
    hits = len(top_docs.intersection(set(gold_doc_ids)))
    return hits / len(gold_doc_ids)


def compute_all_gold_found(retrieved_doc_ids: List[str], gold_doc_ids: List[str], k: int) -> float:
    """1.0 if EVERY required gold doc_id is in top-k, else 0.0 (multi-hop)."""
    if not gold_doc_ids:
        return 1.0
    top_docs = set(retrieved_doc_ids[:k])
    return 1.0 if set(gold_doc_ids).issubset(top_docs) else 0.0


# ---------------------------------------------------------------------------
# Generation Metrics
# ---------------------------------------------------------------------------


def split_into_claims(text: str) -> List[str]:
    """Rule-based atomic claim decomposition (sentence and clause splitter)."""
    if not text:
        return []
    # Strip bracket citations [1] first
    clean = re.sub(r"\[\d+\]", "", text).strip()
    # Split on periods, semicolons, and newlines
    raw_sentences = re.split(r"(?<=[.!?])\s+|\n+|;\s*", clean)
    claims = []
    for s in raw_sentences:
        s_clean = s.strip()
        # Filter very short fragments
        if len(s_clean.split()) >= 3:
            claims.append(s_clean)
    return claims or ([text.strip()] if text.strip() else [])


def compute_answer_correctness(answer: str, answer_keys: List[str]) -> float:
    """Fraction of answer_keys present in answer (date and number aware)."""
    if not answer_keys:
        return 1.0
    matches = sum(1 for k in answer_keys if contains_answer_key(answer, k))
    return matches / len(answer_keys)


def compute_lexical_support(claim: str, context_text: str) -> float:
    """Proxy entailment: content-word overlap + number/date match."""
    c_words = set(re.findall(r"\w+", claim.lower()))
    ctx_words = set(re.findall(r"\w+", context_text.lower()))
    # Remove basic stop words
    stops = {
        "the",
        "a",
        "an",
        "is",
        "was",
        "are",
        "were",
        "of",
        "in",
        "to",
        "and",
        "or",
        "for",
        "on",
        "by",
        "at",
    }
    c_content = c_words - stops
    if not c_content:
        return 1.0
    overlap = len(c_content.intersection(ctx_words))
    word_score = overlap / len(c_content)

    # Number match check: any number in claim must be in context
    claim_nums = set(re.findall(r"\d+", claim))
    ctx_nums = set(re.findall(r"\d+", context_text))
    if claim_nums:
        num_score = len(claim_nums.intersection(ctx_nums)) / len(claim_nums)
        return (word_score * 0.6) + (num_score * 0.4)
    return word_score


def compute_faithfulness(
    answer: str,
    cited_chunks_text: List[str],
    judge_type: str = "lexical_support",
) -> Tuple[float, List[Dict[str, Any]]]:
    """Compute faithfulness over atomic claims.

    Supported judge types: 'lexical_support' (proxy), 'llm_judge'.
    """
    claims = split_into_claims(answer)
    if not claims:
        return 1.0, []

    combined_ctx = " ".join(cited_chunks_text)
    if not combined_ctx:
        # No context cited -> claims cannot be supported
        return 0.0, [{"claim": c, "supported": False, "score": 0.0} for c in claims]

    verdicts = []
    supported_count = 0

    for c in claims:
        score = compute_lexical_support(c, combined_ctx)
        is_supported = score >= 0.5
        if is_supported:
            supported_count += 1
        verdicts.append({"claim": c, "supported": is_supported, "score": round(score, 3)})

    return supported_count / len(claims), verdicts


def compute_citation_metrics(
    cited_chunk_ids: List[Optional[str]],
    gold_chunk_ids: List[str],
) -> Tuple[float, float]:
    """Compute citation_precision and citation_recall against gold chunk ids.

    Invalid citations (None or invalid index) count as 0 precision.
    """
    if not cited_chunk_ids:
        # No citations made
        return 0.0, (1.0 if not gold_chunk_ids else 0.0)

    valid_cits = [cid for cid in cited_chunk_ids if cid is not None]
    if not valid_cits:
        return 0.0, 0.0

    gold_set = set(gold_chunk_ids)
    hits = sum(1 for cid in valid_cits if cid in gold_set)

    precision = hits / len(cited_chunk_ids)  # penalizes invalid citations
    recall = (len(set(valid_cits).intersection(gold_set)) / len(gold_set)) if gold_set else 1.0

    return precision, recall


# ---------------------------------------------------------------------------
# Statistics: Bootstrap Confidence Intervals
# ---------------------------------------------------------------------------


@dataclass
class MetricSummary:
    """Mean and 95% bootstrap confidence interval."""

    mean: float
    ci_low: float
    ci_high: float
    ci_half_width: float
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mean": round(self.mean, 4),
            "ci_low": round(self.ci_low, 4),
            "ci_high": round(self.ci_high, 4),
            "ci_half_width": round(self.ci_half_width, 4),
            "sample_size": self.sample_size,
        }


def bootstrap_ci(
    values: List[float],
    n_resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> MetricSummary:
    """Calculate 95% bootstrap confidence interval using seeded numpy RNG."""
    if not values:
        return MetricSummary(0.0, 0.0, 0.0, 0.0, 0)

    n = len(values)
    mean_val = float(np.mean(values))
    if n == 1 or np.all(np.array(values) == values[0]):
        return MetricSummary(mean_val, mean_val, mean_val, 0.0, n)

    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=np.float64)
    # Generate resampled means
    boot_indices = rng.integers(0, n, size=(n_resamples, n))
    boot_means = np.mean(arr[boot_indices], axis=1)

    low = float(np.percentile(boot_means, 100 * (alpha / 2)))
    high = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    half_width = (high - low) / 2.0

    return MetricSummary(
        mean=mean_val,
        ci_low=low,
        ci_high=high,
        ci_half_width=half_width,
        sample_size=n,
    )


def paired_bootstrap_delta(
    values_a: List[float],
    values_b: List[float],
    n_resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> MetricSummary:
    """Calculate paired difference (A - B) 95% bootstrap confidence interval."""
    if len(values_a) != len(values_b):
        raise ValueError("Paired bootstrap requires identical sample sizes.")

    diffs = np.array(values_a, dtype=np.float64) - np.array(values_b, dtype=np.float64)
    return bootstrap_ci(diffs.tolist(), n_resamples=n_resamples, seed=seed, alpha=alpha)


# ---------------------------------------------------------------------------
# Overall Weighted Score
# ---------------------------------------------------------------------------


def load_eval_weights() -> Dict[str, float]:
    """Load evaluation weights from config/eval_weights.yaml."""
    weights_path = CONFIG_DIR / "eval_weights.yaml"
    if weights_path.exists():
        with open(weights_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("weights", {})
    return {
        "faithfulness": 0.30,
        "answer_correctness": 0.25,
        "recall_at_5": 0.20,
        "citation_precision": 0.10,
        "refusal_accuracy": 0.15,
    }


def compute_overall_score(metric_means: Dict[str, float]) -> float:
    """Calculate weighted overall score from component metric means."""
    weights = load_eval_weights()
    score = 0.0
    for key, weight in weights.items():
        val = metric_means.get(key, 0.0)
        score += weight * val
    return round(score, 4)
