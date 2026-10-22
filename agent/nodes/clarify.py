"""Clarify node: handle ambiguous queries with interactive options or batch assumptions."""

from __future__ import annotations

from typing import Any, List, Optional

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState, ClarificationState
from agent.tracing import Tracer
from agent.types import RagAnswer


DEFAULT_OPTIONS = [
    "Scheduled Commercial Banks (SCBs)",
    "Non-Banking Financial Companies (NBFCs)",
    "Urban Co-operative Banks (UCBs)",
    "Small Finance Banks (SFBs)",
]


def node_clarify(
    state: AgentState,
    llm: Optional[LLM],
    tracer: Tracer,
    prompt_template: str,
    ambiguity_reason: str = "Query applies differently depending on regulated entity category",
) -> AgentState:
    """Evaluate clarification trigger and formulate question or explicit assumption."""
    with tracer.span("clarify", {"step": "clarify", "interactive": state.interactive}) as span:
        state.budget.steps += 1

        # Case 1: Interactive mode -> Ask user clarification
        if state.interactive:
            c_q = "Which regulated entity category does your inquiry concern?"
            opts = DEFAULT_OPTIONS

            if state.mode == "full" and llm is not None and not isinstance(llm.provider, ExtractiveLLMProvider):
                prompt = prompt_template.replace("{question}", state.standalone_question or state.question).replace("{ambiguity_reason}", ambiguity_reason)
                try:
                    res = llm.generate([{"role": "user", "content": prompt}], max_tokens=150)
                    state.budget.llm_calls_used += 1
                    state.budget.tokens_used += res.usage.get("total", 0)
                    parsed = res.parsed_json or {}
                    if parsed.get("question") and parsed.get("options"):
                        c_q = str(parsed["question"])
                        opts = [str(o) for o in parsed["options"][:4]]
                except Exception:
                    pass

            state.clarification = ClarificationState(
                needed=True,
                question=c_q,
                options=opts,
            )
            state.final = RagAnswer(
                answer=f"{c_q}\n" + "\n".join(f"- {o}" for o in opts),
                citations=[],
                refused=False,
                retrieved=[],
                timings={},
                usage={"in": 0, "out": 0},
                provider="agent_clarify",
                model="clarify_engine",
                clarification={"needed": True, "question": c_q, "options": opts},
                trace=tracer.get_trace(),
            )
            span["clarification_asked"] = True
            tracer.event("clarification", {"question": c_q, "options": opts})
            return state

        # Case 2: Non-interactive mode (eval / batch) -> Assume default entity and proceed
        assumption = "Assuming inquiry pertains to Scheduled Commercial Banks (SCBs)."
        state.warnings.append(f"Clarification skipped in batch mode: {assumption} Alternatives: NBFCs, UCBs.")
        span["clarification_skipped"] = True
        return state
