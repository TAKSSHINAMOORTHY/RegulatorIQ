"""Decompose node: split multi-part questions into focused sub-questions."""

from __future__ import annotations

import re
from typing import List, Optional

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState, PlanState, SubQuestion
from agent.tracing import Tracer


def node_decompose(
    state: AgentState,
    llm: Optional[LLM],
    tracer: Tracer,
    prompt_template: str,
    max_subquestions: int = 4,
) -> AgentState:
    """Break multi-part or comparative questions into focused sub-questions."""
    with tracer.span("decompose", {"step": "decompose"}) as span:
        state.budget.steps += 1
        q = (state.standalone_question or state.question).strip()

        # Check for multi-part / comparative markers
        compare_patterns = [
            r"\bcompare\s+(.+?)\s+and\s+(.+)",
            r"\bdifference\s+between\s+(.+?)\s+and\s+(.+)",
            r"\b(.+?)\s+versus\s+(.+)",
            r"\b(.+?)\s+vs\.?\s+(.+)",
        ]
        conj_patterns = [
            r"\b(.+?)\s+and\s+also\s+(.+)",
            r"\b(.+?)\s+and\s+what\s+(.+)",
        ]

        sub_qs: List[SubQuestion] = []
        strategy = "direct"

        # 1. Check comparison regexes
        matched_compare = False
        for pat in compare_patterns:
            m = re.search(pat, q, re.IGNORECASE)
            if m:
                part1, part2 = m.group(1).strip(), m.group(2).strip()
                sub_qs = [
                    SubQuestion(
                        id="q1",
                        text=f"Regulatory guidelines for {part1}",
                        combine_strategy="compare",
                    ),
                    SubQuestion(
                        id="q2",
                        text=f"Regulatory guidelines for {part2}",
                        combine_strategy="compare",
                    ),
                ]
                strategy = "compare"
                matched_compare = True
                break

        # 2. Check conjunction regexes if not matched
        if not matched_compare:
            for pat in conj_patterns:
                m = re.search(pat, q, re.IGNORECASE)
                if m:
                    p1, p2 = m.group(1).strip(), m.group(2).strip()
                    sub_qs = [
                        SubQuestion(id="q1", text=p1, combine_strategy="merge"),
                        SubQuestion(
                            id="q2",
                            text=f"What {p2}" if not p2.lower().startswith("what") else p2,
                            combine_strategy="merge",
                        ),
                    ]
                    strategy = "merge"
                    break

        # 3. FULL mode with LLM if multi-part suspected or explicit comparison intent
        if (
            state.mode == "full"
            and state.intent in ("comparison", "procedure")
            and llm is not None
            and not isinstance(llm.provider, ExtractiveLLMProvider)
        ):
            prompt = prompt_template.replace("{question}", q)
            try:
                res = llm.generate([{"role": "user", "content": prompt}], max_tokens=250)
                state.budget.llm_calls_used += 1
                state.budget.tokens_used += res.usage.get("total", 0)
                parsed = res.parsed_json or {}
                if parsed.get("sub_questions") and isinstance(parsed["sub_questions"], list):
                    llm_subs: List[SubQuestion] = []
                    for item in parsed["sub_questions"][:max_subquestions]:
                        if isinstance(item, dict) and item.get("text"):
                            llm_subs.append(
                                SubQuestion(
                                    id=str(item.get("id", f"q{len(llm_subs) + 1}")),
                                    text=str(item["text"]),
                                    combine_strategy=str(item.get("combine_strategy", "merge")),
                                )
                            )
                    if llm_subs:
                        sub_qs = llm_subs
                        strategy = str(parsed.get("strategy", strategy))
            except Exception:
                pass

        # If no decomposition needed, question stays single-part direct
        if not sub_qs:
            sub_qs = [SubQuestion(id="q1", text=q, combine_strategy="direct")]
            strategy = "direct"

        state.plan = PlanState(sub_questions=sub_qs, strategy=strategy)
        span["sub_questions_count"] = len(sub_qs)
        span["strategy"] = strategy
        tracer.event(
            "plan", {"strategy": strategy, "sub_questions": [s.model_dump() for s in sub_qs]}
        )
        return state
