"""Condense node: resolve elliptical follow-up questions using conversation history."""

from __future__ import annotations

import re
from typing import Optional

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.query_analysis import QueryAnalyzer


def node_condense(
    state: AgentState,
    llm: Optional[LLM],
    analyzer: QueryAnalyzer,
    tracer: Tracer,
    prompt_template: str,
) -> AgentState:
    """Produce self-contained standalone question if input is elliptical."""
    with tracer.span("condense", {"step": "condense"}) as span:
        state.budget.steps += 1
        q = state.question.strip()
        words = q.split()

        # Check if question is elliptical: < 6 words or contains pronouns without identifier
        pronouns = {"it", "that", "this", "those", "these", "its", "they", "their"}
        has_pronoun = any(w.lower() in pronouns for w in words)
        is_short = len(words) < 6
        has_id = bool(re.search(r"RBI/[0-9]{4}-[0-9]{2,4}/[0-9]+", q, re.IGNORECASE))

        is_elliptical = (is_short or has_pronoun) and not has_id and len(state.history) > 0

        if not is_elliptical:
            state.standalone_question = q
            span["condensed"] = False
            return state

        span["condensed"] = True
        prev_turn = state.history[-1]
        prev_q = prev_turn.get("question", "") or prev_turn.get("content", "")

        # Full mode with generative LLM
        if (
            state.mode == "full"
            and llm is not None
            and not isinstance(llm.provider, ExtractiveLLMProvider)
        ):
            hist_str = "\n".join(
                f"User: {h.get('question', '')}\nAssistant: {h.get('answer', '')}"
                for h in state.history[-4:]
            )
            prompt = prompt_template.replace("{history}", hist_str).replace("{question}", q)
            try:
                res = llm.generate([{"role": "user", "content": prompt}], max_tokens=100)
                state.budget.llm_calls_used += 1
                state.budget.tokens_used += res.usage.get("total", 0)
                parsed = res.parsed_json or {}
                standalone = str(parsed.get("standalone_question", res.text.strip()))
                if standalone and len(standalone) > 3:
                    state.standalone_question = standalone
                    return state
            except Exception:
                pass

        # Rules mode fallback: prepend previous question's core subject/identifier
        prev_plan = analyzer.analyze(prev_q)
        topic = prev_plan.topics[0] if prev_plan.topics else ""
        ident = prev_plan.identifiers[0] if prev_plan.identifiers else ""

        lead = ident or topic
        if lead:
            state.standalone_question = f"{lead}: {q}"
        else:
            state.standalone_question = f"{prev_q} - {q}"

        return state
