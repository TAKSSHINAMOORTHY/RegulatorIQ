"""Retrieve node: execute hybrid retrieval and reranking for sub-questions."""

from __future__ import annotations

from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.pipeline import Retriever


def node_retrieve(
    state: AgentState,
    retriever: Retriever,
    tracer: Tracer,
) -> AgentState:
    """Retrieve evidence chunks for each active sub-question."""
    with tracer.span("retrieve", {"step": "retrieve", "round": state.rounds + 1}) as span:
        state.budget.steps += 1
        state.budget.retrieval_rounds += 1
        state.rounds += 1

        sub_qs = state.plan.sub_questions or []
        total_chunks = 0

        for sub_q in sub_qs:
            q_text = sub_q.text
            res = retriever.retrieve(
                question=q_text,
                as_of=state.as_of,
                history=state.wants_history,
                filters=state.filters,
            )
            state.evidence[sub_q.id] = list(res.chunks)
            total_chunks += len(res.chunks)

            # Record warnings if any
            if res.warnings:
                state.warnings.extend(res.warnings)

        span["total_chunks_retrieved"] = total_chunks
        tracer.event(
            "retrieval",
            {
                "round": state.rounds,
                "sub_questions": [s.id for s in sub_qs],
                "chunk_counts": {s.id: len(state.evidence.get(s.id, [])) for s in sub_qs},
            },
        )
        return state
