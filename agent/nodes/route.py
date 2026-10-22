"""Route node: classify query intent into regulatory workflows or chitchat bypass."""

from __future__ import annotations

from typing import Any, Optional

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.query_analysis import QueryAnalyzer


CHITCHAT_PATTERNS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "thanks",
    "thank you",
    "bye",
    "who are you",
    "what can you do",
}


def node_route(
    state: AgentState,
    analyzer: QueryAnalyzer,
    llm: Optional[LLM],
    tracer: Tracer,
    prompt_template: str,
) -> AgentState:
    """Classify user intent into regulatory task type or direct chitchat."""
    with tracer.span("route", {"step": "route"}) as span:
        state.budget.steps += 1
        query = (state.standalone_question or state.question).strip().lower()

        # 1. Chitchat check
        clean_q = "".join(c for c in query if c.isalnum() or c.isspace()).strip()
        words_count = len(clean_q.split())
        is_chat = clean_q in CHITCHAT_PATTERNS or (
            words_count <= 5
            and any(
                p in clean_q
                for p in ("hi", "hello", "hey", "good morning", "good afternoon", "thanks", "thank you", "bye")
            )
        )
        if is_chat:
            state.intent = "chitchat"
            span["intent"] = "chitchat"
            tracer.event("routing", {"intent": "chitchat", "mode": "chitchat_bypass"})
            return state

        # 2. FULL mode LLM route (if enabled and non-extractive)
        if state.mode == "full" and llm is not None and not isinstance(llm.provider, ExtractiveLLMProvider):
            prompt = prompt_template.replace("{history}", str(state.history[-2:])).replace("{question}", state.standalone_question or state.question)
            try:
                res = llm.generate([{"role": "user", "content": prompt}], max_tokens=60)
                state.budget.llm_calls_used += 1
                state.budget.tokens_used += res.usage.get("total", 0)
                parsed = res.parsed_json or {}
                intent = parsed.get("intent", "").lower()
                valid_intents = {"lookup", "definition", "threshold", "timeline", "comparison", "applicability", "validity", "procedure", "chitchat", "out_of_scope"}
                if intent in valid_intents:
                    state.intent = intent
                    span["intent"] = intent
                    return state
            except Exception:
                pass

        # 3. RULES mode / fallback using deterministic QueryPlan
        plan = analyzer.analyze(state.standalone_question or state.question)
        if plan.intents:
            state.intent = plan.intents[0]
        else:
            state.intent = "lookup"

        span["intent"] = state.intent
        return state
