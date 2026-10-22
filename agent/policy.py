"""Refusal and clarification policies for compliance safety.

Governs when the agent must politely refuse or attach near-miss citations without hallucinating.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agent.types import RagAnswer


class RefusalPolicy:
    """Evaluates refusal criteria and constructs structured refusal answers."""

    def __init__(
        self,
        refusal_conf_threshold: float = 0.15,
        clarify_conf_threshold: float = 0.25,
        min_relevant_chunks: int = 2,
    ) -> None:
        self.refusal_conf_threshold = refusal_conf_threshold
        self.clarify_conf_threshold = clarify_conf_threshold
        self.min_relevant_chunks = min_relevant_chunks

    def should_refuse_after_retrieval(
        self,
        relevant_chunks_count: int,
        confidence: float,
        has_exact_identifier_hit: bool,
    ) -> Tuple[bool, Optional[str]]:
        """Determine if retrieval results require refusal."""
        if has_exact_identifier_hit:
            return False, None

        if relevant_chunks_count == 0 and confidence < self.refusal_conf_threshold:
            return (
                True,
                "No official Reserve Bank of India (RBI) documents in the repository contain evidence answering this question.",
            )

        return False, None

    def build_refusal_response(
        self,
        reason: str,
        near_miss_chunks: Optional[List[Any]] = None,
        timings: Optional[Dict[str, float]] = None,
        usage: Optional[Dict[str, int]] = None,
        trace: Optional[List[Dict[str, Any]]] = None,
    ) -> RagAnswer:
        """Construct compliant refusal response with optional related documents."""
        text = reason
        citations: List[Dict[str, Any]] = []

        if near_miss_chunks:
            text += "\n\nRelated official RBI directives found in the repository:\n"
            for i, c in enumerate(near_miss_chunks[:3], start=1):
                chunk_obj = getattr(c, "chunk", c)
                circ = getattr(chunk_obj, "circular_no", None) or "RBI Directive"
                title = getattr(chunk_obj, "title", "")
                date_str = getattr(chunk_obj, "issue_date", "") or ""
                url = getattr(chunk_obj, "source_url", "")
                text += f"[{i}] {circ} - {title} ({date_str})\n"
                citations.append(
                    {
                        "ref_num": i,
                        "chunk_id": getattr(chunk_obj, "chunk_id", f"c_{i}"),
                        "doc_id": getattr(chunk_obj, "doc_id", f"d_{i}"),
                        "circular_no": circ,
                        "title": title,
                        "issue_date": date_str,
                        "source_url": url,
                        "status": "related",
                    }
                )

        return RagAnswer(
            answer=text.strip(),
            citations=citations,
            refused=True,
            retrieved=[],
            timings=timings or {},
            usage=usage or {"in": 0, "out": 0},
            provider="agent_policy",
            model="policy_engine",
            trace=trace or [],
        )
