"""Rewrite retry node: reformulate queries upon insufficient evidence."""

from __future__ import annotations

from typing import Optional, Set

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.query_analysis import QueryAnalyzer
from retrieval.rewrite import QueryRewriter


def node_rewrite_retry(
    state: AgentState,
    analyzer: QueryAnalyzer,
    rewriter: QueryRewriter,
    llm: Optional[LLM],
    tracer: Tracer,
    prompt_template: str,
) -> AgentState:
    """Generate new query variants targeting the specific evidence gap."""
    with tracer.span("rewrite_retry", {"step": "rewrite_retry", "round": state.rounds}) as span:
        state.budget.steps += 1
        new_sub_qs = []
        seen_queries: Set[str] = {sq.text.lower().strip() for sq in state.plan.sub_questions}

        for sub_q in state.plan.sub_questions:
            old_text = sub_q.text
            plan = analyzer.analyze(old_text)

            # Failure reason analysis:
            # 1. If all chunks superseded -> set wants_history=True
            chunks = state.evidence.get(sub_q.id, [])
            if chunks and all(not getattr(c.chunk, "is_current", True) for c in chunks):
                state.wants_history = True
                span["action"] = "allow_history"

            # 2. Query expansion
            new_text = old_text
            # Try synonym / abbreviation expansion
            expanded = rewriter.rewrite(plan)
            for v in expanded.query_variants:
                if v.lower().strip() not in seen_queries:
                    new_text = v
                    break

            # 3. If in FULL mode and LLM available, generate targeted retry
            if (
                state.mode == "full"
                and new_text.lower().strip() in seen_queries
                and llm is not None
                and not isinstance(llm.provider, ExtractiveLLMProvider)
            ):
                prompt = prompt_template.replace("{question}", old_text).replace(
                    "{failure_reason}", "low relevance in retrieved evidence"
                )
                try:
                    res = llm.generate([{"role": "user", "content": prompt}], max_tokens=100)
                    state.budget.llm_calls_used += 1
                    state.budget.tokens_used += res.usage.get("total", 0)
                    parsed = res.parsed_json or {}
                    candidate_rewrite = str(parsed.get("rewritten_query", res.text.strip()))
                    if (
                        candidate_rewrite.lower().strip() not in seen_queries
                        and len(candidate_rewrite) > 3
                    ):
                        new_text = candidate_rewrite
                except Exception:
                    pass

            # Fallback if still identical: append regulatory directive keywords
            if new_text.lower().strip() in seen_queries:
                new_text = f"{old_text} Reserve Bank of India Master Direction guidelines"

            seen_queries.add(new_text.lower().strip())
            sub_q.text = new_text
            new_sub_qs.append(sub_q)

        state.plan.sub_questions = new_sub_qs
        tracer.event(
            "query_retry", {"sub_questions": [s.text for s in new_sub_qs], "round": state.rounds}
        )
        return state
