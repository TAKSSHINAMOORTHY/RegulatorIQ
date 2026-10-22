"""Guard node: deterministic safety, injection, and PII inspection."""

from __future__ import annotations

from typing import Any, Dict

from agent.guards import SafetyGuard
from agent.policy import RefusalPolicy
from agent.state import AgentState
from agent.tracing import Tracer


def node_guard(
    state: AgentState,
    guard: SafetyGuard,
    policy: RefusalPolicy,
    tracer: Tracer,
) -> AgentState:
    """Execute pre-flight safety and sanitisation checks on user query."""
    with tracer.span("guard", {"step": "guard", "raw_length": len(state.question)}) as span:
        state.budget.steps += 1
        outcome = guard.check(state.question)

        span["status"] = outcome.status
        if outcome.status == "refuse":
            state.refused = True
            state.refusal_reason = outcome.refusal_reason or "Question rejected by safety policy."
            state.draft_answer = state.refusal_reason
            state.warnings.extend(outcome.warnings)
            state.final = policy.build_refusal_response(
                reason=state.refusal_reason,
                trace=tracer.get_trace(),
            )
            tracer.event("refusal", {"reason": state.refusal_reason, "step": "guard"})
            return state

        if outcome.status == "allow_with_redaction":
            state.question = outcome.clean_text
            state.warnings.extend(outcome.warnings)
            tracer.event("redaction", {"warnings": outcome.warnings, "step": "guard"})
        else:
            state.question = outcome.clean_text

        return state
