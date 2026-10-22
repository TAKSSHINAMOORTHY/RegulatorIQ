"""Concurrency test for AgentRunner: 16 parallel threads running against shared instances."""

from __future__ import annotations

import concurrent.futures
from typing import List

from agent.runner import AgentRunner
from agent.types import RagAnswer
from tests.unit.test_agent_scenarios import create_scenario_runner


def test_16_parallel_runner_threads_no_state_leakage() -> None:
    """Verify 16 parallel run() invocations on shared runner without cross-talk or race conditions."""
    runner = create_scenario_runner()

    questions = [
        ("What is the CRR requirement under Master Direction 2025?", "CRR"),
        ("What is the SLR requirement under circular RBI/2025-26/10?", "SLR"),
        ("Hi there", "chitchat"),
        ("What are the KYC norms?", "KYC"),
    ] * 4  # Total 16 queries

    def execute_query(idx: int, q_tuple: tuple[str, str]) -> tuple[int, str, RagAnswer]:
        q, expected_intent = q_tuple
        # Run with question-specific options
        ans = runner.run(q, session_opts={"as_of": "2025-04-01"})
        return idx, expected_intent, ans

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(execute_query, i, questions[i]) for i in range(16)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 16
    for idx, expected_intent, ans in results:
        assert isinstance(ans, RagAnswer)
        assert ans.steps <= 14
        assert ans.llm_calls <= 6
        if expected_intent == "chitchat":
            assert not ans.refused
            assert len(ans.citations) == 0
            assert "RegulatorIQ" in ans.answer
        else:
            assert len(ans.answer) > 0
