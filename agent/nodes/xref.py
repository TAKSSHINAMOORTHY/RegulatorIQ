"""XRef node: traverse cross-references between related circulars."""

from __future__ import annotations

from agent.state import AgentState
from agent.tracing import Tracer
from agent.xref import XRefTraverser


def node_xref(
    state: AgentState,
    traverser: XRefTraverser,
    tracer: Tracer,
) -> AgentState:
    """Follow explicit cross-references and amendment pointers in top evidence."""
    with tracer.span("xref", {"step": "xref"}) as span:
        state.budget.steps += 1
        all_chunks = []
        for ch_list in state.evidence.values():
            all_chunks.extend(ch_list)

        findings = traverser.traverse(
            ranked_chunks=all_chunks,
            query=state.standalone_question or state.question,
        )

        for f in findings:
            state.xref_findings.append(
                {
                    "src_doc_id": f.src_doc_id,
                    "target_doc_id": f.target_doc_id,
                    "relation": f.relation,
                    "reference_text": f.reference_text,
                    "path": f.path,
                }
            )
            # Add cross-referenced chunks to primary sub-question evidence
            if state.plan.sub_questions:
                primary_id = state.plan.sub_questions[0].id
                state.evidence.setdefault(primary_id, []).extend(f.retrieved_chunks)

        span["xref_count"] = len(findings)
        tracer.event(
            "xref",
            {"findings": state.xref_findings},
        )
        return state
