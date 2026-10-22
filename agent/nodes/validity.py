"""Validity node: resolve latest valid rule and successor documents."""

from __future__ import annotations

from agent.state import AgentState
from agent.tracing import Tracer
from agent.validity import ValidityResolver


def node_validity(
    state: AgentState,
    resolver: ValidityResolver,
    tracer: Tracer,
) -> AgentState:
    """Resolve document supersession and amendment chains using the link graph."""
    with tracer.span("validity", {"step": "validity"}) as span:
        state.budget.steps += 1
        all_chunks = []
        for ch_list in state.evidence.values():
            all_chunks.extend(ch_list)

        findings = resolver.resolve_validity(
            ranked_chunks=all_chunks,
            as_of_date=state.as_of,
            wants_current=not state.wants_history,
        )

        state.validity_findings = [
            {
                "doc_id": f.old_doc_id,
                "circular_no": f.circular_no,
                "title": f.title,
                "status": f.status,
                "successor_circulars": f.successor_circulars,
                "amendment_circulars": f.amendment_circulars,
                "explanation": f.explanation,
                "confidence": f.confidence,
            }
            for f in findings
        ]

        span["findings_count"] = len(findings)
        tracer.event(
            "validity",
            {"findings": state.validity_findings},
        )
        return state
