"""Query rewriting modules: rules, LLM rewriting, HyDE, and multi-query paraphrasing.

Guarantees:
- Strict preservation of all identifiers, circular numbers, and numerical quantities.
- Rejection of any LLM rewrite that drops original identifiers or numbers.
- Safe degraded fallback to deterministic rules when LLM provider is unavailable or extractive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from agent.llm import LLM, ExtractiveLLMProvider
from retrieval.query_analysis import QueryAnalyzer, QueryPlan


@dataclass
class RewriteResult:
    """Output bundle from the query rewriting pipeline."""

    query_variants: List[str]
    hyde_passage: Optional[str] = None
    degraded_rewrite: bool = False
    rejected_rewrites: List[str] = field(default_factory=list)


def extract_numbers_and_ids(text: str) -> List[str]:
    """Extract all numeric quantities and alphanumeric identifier tokens from text."""
    # Find numbers: e.g. 90, 4.5, 2024, 25
    nums = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    # Find tokens with digits (e.g. RBI/2025-26/90)
    words = re.findall(r"\b[A-Za-z0-9\/\.\-]+[0-9]+[A-Za-z0-9\/\.\-]*\b", text)
    tokens = set(nums + words)
    return sorted(list(tokens), key=len, reverse=True)


def validate_rewrite(original: str, rewritten: str, identifiers: List[str]) -> bool:
    """Verify that rewritten text preserves all identifiers and numbers from original."""
    if not rewritten or not rewritten.strip():
        return False

    rewritten_lower = rewritten.lower()

    # 1. Check all explicit identifiers
    for ident in identifiers:
        if ident.lower() not in rewritten_lower:
            return False

    # 2. Check all numbers present in the original
    original_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", original)
    for num in original_numbers:
        # Check as word or substring
        if not re.search(r"\b" + re.escape(num) + r"\b", rewritten):
            return False

    return True


class QueryRewriter:
    """Modular query rewriting engine with safety guards and rule-based fallbacks."""

    def __init__(
        self,
        llm: Optional[LLM] = None,
        use_rules: bool = True,
        use_llm_rewrite: bool = False,
        use_hyde: bool = False,
        use_multi_query: bool = False,
    ) -> None:
        self.llm = llm
        self.use_rules = use_rules
        self.use_llm_rewrite = use_llm_rewrite
        self.use_hyde = use_hyde
        self.use_multi_query = use_multi_query
        self.analyzer = QueryAnalyzer()

    def rewrite(self, plan: QueryPlan) -> RewriteResult:
        """Execute configured rewrite techniques on the query plan."""
        variants: List[str] = list(plan.query_variants)
        rejected: List[str] = []
        hyde_passage: Optional[str] = None
        degraded = False

        # If LLM methods are requested, check LLM suitability
        llm = self.llm
        if (self.use_llm_rewrite or self.use_hyde or self.use_multi_query) and llm is None:
            try:
                llm = LLM()
            except Exception:
                llm = None

        is_extractive_or_none = llm is None or isinstance(llm.provider, ExtractiveLLMProvider)

        if (
            self.use_llm_rewrite or self.use_hyde or self.use_multi_query
        ) and is_extractive_or_none:
            degraded = True

        # 1. LLM Rewrite (D2)
        if self.use_llm_rewrite and not is_extractive_or_none and llm is not None:
            prompt = (
                f"You are a regulatory search assistant. Rewrite the following query into a "
                f"standalone, keyword-rich search query. CRITICAL: You must preserve all circular numbers, "
                f"identifiers, dates, and numbers verbatim. Do not explain, return only the rewritten query.\n\n"
                f"Original Query: {plan.raw}\n"
                f"Rewritten Query:"
            )
            try:
                res = llm.generate(messages=[{"role": "user", "content": prompt}], max_tokens=100)
                rewritten = res.text.strip().strip('"').strip("'")
                if validate_rewrite(plan.raw, rewritten, plan.identifiers):
                    if rewritten not in variants:
                        variants.append(rewritten)
                else:
                    rejected.append(rewritten)
            except Exception:
                degraded = True

        # 2. HyDE (D3)
        if self.use_hyde and not is_extractive_or_none and llm is not None:
            prompt = (
                f"Write a short, authoritative 2-sentence excerpt from an official Reserve Bank of India "
                f"circular or master direction that answers this question: {plan.raw}\n"
                f"Excerpt:"
            )
            try:
                res = llm.generate(messages=[{"role": "user", "content": prompt}], max_tokens=150)
                hyde_passage = res.text.strip()
            except Exception:
                degraded = True

        # 3. Multi-Query Paraphrases (D4)
        if self.use_multi_query and not is_extractive_or_none and llm is not None:
            prompt = (
                f"Generate up to 3 distinct search query paraphrases for the following banking query. "
                f"CRITICAL: Keep all identifiers and numbers verbatim in every paraphrase. "
                f"Return one per line.\n\n"
                f"Query: {plan.raw}\n"
                f"Paraphrases:"
            )
            try:
                res = llm.generate(messages=[{"role": "user", "content": prompt}], max_tokens=150)
                lines = [
                    line.strip("- *0123456789.").strip()
                    for line in res.text.split("\n")
                    if line.strip()
                ]
                for p in lines[:3]:
                    if validate_rewrite(plan.raw, p, plan.identifiers):
                        if p not in variants:
                            variants.append(p)
                    else:
                        rejected.append(p)
            except Exception:
                degraded = True

        return RewriteResult(
            query_variants=variants,
            hyde_passage=hyde_passage,
            degraded_rewrite=degraded,
            rejected_rewrites=rejected,
        )
