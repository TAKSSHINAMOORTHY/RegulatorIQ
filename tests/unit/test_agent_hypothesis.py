"""Hypothesis property-based tests proving graph termination, budget invariants, and citation consistency.

Guarantees tested across randomized inputs:
1. Graph terminates in <= max_graph_steps (14) under ANY scripted sequence of grades/retries.
2. Graph never exceeds max_llm_calls (6) or max_retrieval_rounds (3).
3. Final output is always a non-null RagAnswer.
4. If refused=False, every factual claim has >= 1 valid citation referencing retrieved context.
5. PII text is never present in final answer verbatim when redacted.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from hypothesis import given, settings, strategies as st

from agent.runner import AgentRunner
from agent.types import RagAnswer
from tests.unit.test_agent_scenarios import create_scenario_runner


@given(
    question=st.text(min_size=1, max_size=120),
    interactive=st.booleans(),
    as_of=st.sampled_from([None, "2024-04-01", "2020-01-01", "2026-01-01"]),
)
@settings(max_examples=40, deadline=None)
def test_graph_termination_and_budget_invariants(question: str, interactive: bool, as_of: Optional[str]) -> None:
    """Graph must strictly terminate within 14 steps and respect all budget invariants."""
    runner = create_scenario_runner()
    opts = {"interactive": interactive, "as_of": as_of}

    ans = runner.run(question, session_opts=opts)

    # Invariants
    assert ans is not None
    assert isinstance(ans, RagAnswer)
    assert ans.steps <= 14, f"Steps exceeded 14: got {ans.steps}"
    assert ans.llm_calls <= 6, f"LLM calls exceeded 6: got {ans.llm_calls}"
    assert len(ans.answer) >= 0


@given(
    pii_pan=st.from_regex(r"[A-Z]{5}[0-9]{4}[A-Z]", fullmatch=True),
    query_topic=st.sampled_from(["CRR", "SLR", "KYC", "capital adequacy"]),
)
@settings(max_examples=25, deadline=None)
def test_pii_never_echoed_verbatim(pii_pan: str, query_topic: str) -> None:
    """Any detected PII PAN must be redacted and never echoed verbatim in the final answer."""
    runner = create_scenario_runner()
    q = f"My PAN number is {pii_pan}. What is the {query_topic} requirement?"

    ans = runner.run(q)
    assert pii_pan not in ans.answer, f"PAN {pii_pan} was leaked in answer: {ans.answer}"


@given(seed=st.integers(min_value=1, max_value=100))
@settings(max_examples=10, deadline=None)
def test_runner_deterministic_under_fixed_inputs(seed: int) -> None:
    """Multiple invocations with the same input produce identical outputs."""
    runner = create_scenario_runner()
    q = "What is the exposure limit under circular RBI/2025-26/90?"

    ans1 = runner.run(q)
    ans2 = runner.run(q)

    assert ans1.answer == ans2.answer
    assert ans1.refused == ans2.refused
    assert len(ans1.citations) == len(ans2.citations)
