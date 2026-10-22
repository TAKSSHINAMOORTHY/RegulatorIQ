"""Finalize node: construct final RagAnswer with metadata, citations, and disclaimer."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from agent.state import AgentState
from agent.tracing import Tracer
from agent.types import RagAnswer
from retrieval.context import build_context


def is_rbi_url(url: str) -> bool:
    """Validate that citation URL points strictly to official rbi.org.in domains."""
    if not url:
        return False
    # Must contain rbi.org.in and start with https:// or http://
    return bool(re.match(r"^https?://([a-zA-Z0-9-]+\.)*rbi\.org\.in(/.*)?$", url, re.IGNORECASE))


def node_finalize(
    state: AgentState,
    tracer: Tracer,
    disclaimer_key: str = "regulatory_disclaimer",
    max_steps: int = 14,
) -> AgentState:
    """Package final RagAnswer adhering to output contract."""
    with tracer.span("finalize", {"step": "finalize"}):
        state.budget.steps = min(state.budget.steps + 1, max_steps)

        # Flatten evidence chunks in order
        all_rcs = []
        for sq in state.plan.sub_questions:
            all_rcs.extend(state.evidence.get(sq.id, []))
        bundle = build_context(all_rcs, token_budget=3000)

        # Extract citation numbers from final answer
        found_refs = [int(m) for m in re.findall(r"\[(\d+)\]", state.draft_answer)]
        raw_citations = sorted(list(set(found_refs)))

        citations: List[Dict[str, Any]] = []
        for ref_num in raw_citations:
            idx = ref_num - 1
            if 0 <= idx < len(bundle.items):
                item = bundle.items[idx]
                c = item.chunk
                raw_url = getattr(c, "source_url", "")
                safe_url = raw_url if is_rbi_url(raw_url) else ""

                citations.append(
                    {
                        "ref_num": ref_num,
                        "chunk_id": c.chunk_id,
                        "doc_id": c.doc_id,
                        "circular_no": getattr(c, "circular_no", None),
                        "title": getattr(c, "title", ""),
                        "issue_date": getattr(c, "issue_date", None),
                        "para_ref": getattr(c, "para_ref", None),
                        "page_start": getattr(c, "page_start", None),
                        "source_url": safe_url,
                        "status": item.status,
                    }
                )

        # Emit citation events
        for cite in citations:
            tracer.event("citation", cite)

        elapsed_ms = round((time.time() - state.budget.started_at) * 1000.0, 2)
        degraded_flags = []
        if state.mode == "rules":
            degraded_flags.append("rules_mode")
        if any("partially_redacted" in w for w in state.warnings):
            degraded_flags.append("partially_redacted")

        ans_text = (
            state.draft_answer
            or state.refusal_reason
            or (state.final.answer if state.final else "")
        )
        final_ans = RagAnswer(
            answer=ans_text,
            citations=citations,
            refused=state.refused,
            retrieved=[
                {
                    "chunk_id": item.chunk.chunk_id,
                    "doc_id": item.chunk.doc_id,
                    "fused_score": item.fused_score,
                    "rerank_score": item.rerank_score,
                    "rank": item.rank,
                    "status": item.status,
                }
                for item in bundle.items
            ],
            timings={"total_ms": elapsed_ms},
            usage={
                "in": state.budget.tokens_used // 2,
                "out": state.budget.tokens_used // 2,
                "total": state.budget.tokens_used,
            },
            provider=state.mode,
            model="agentic_v1",
            trace=tracer.get_trace(),
            steps=state.budget.steps,
            llm_calls=state.budget.llm_calls_used,
            clarification=state.clarification.model_dump() if state.clarification.needed else None,
            validity_findings=state.validity_findings,
            grounding_report=state.grounding_report,
            mode=state.mode,
            degraded_flags=degraded_flags,
            disclaimer_key=disclaimer_key,
        )

        state.final = final_ans
        tracer.event(
            "final",
            {"refused": state.refused, "citations_count": len(citations), "latency_ms": elapsed_ms},
        )
        return state
