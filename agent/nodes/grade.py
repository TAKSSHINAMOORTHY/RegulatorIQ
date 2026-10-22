"""Grade node: evaluate evidence sufficiency and grade chunks per sub-question."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.hybrid import RankedChunk


def node_grade(
    state: AgentState,
    llm: Optional[LLM],
    tracer: Tracer,
    prompt_template: str,
    grade_threshold: float = 0.35,
    min_relevant_chunks: int = 2,
    max_retrieval_rounds: int = 3,
) -> Tuple[AgentState, Literal["enough", "rewrite_retry", "give_up"]]:
    """Grade retrieved chunks and decide whether evidence is sufficient or retry is needed."""
    with tracer.span("grade", {"step": "grade", "round": state.rounds}) as span:
        state.budget.steps += 1
        all_grades: Dict[str, Dict[str, Any]] = {}
        all_satisfied = True

        for sub_q in state.plan.sub_questions:
            chunks = state.evidence.get(sub_q.id, [])
            relevant_count = 0
            borderline_chunks: List[RankedChunk] = []

            for rc in chunks:
                cid = rc.chunk.chunk_id
                score = getattr(rc, "rerank_score", 0.0) or getattr(rc, "fused_score", 0.0)

                # 1. Cheap deterministic threshold grading
                if score >= grade_threshold:
                    verdict = "relevant"
                    reason = f"High rerank score ({score:.3f} >= {grade_threshold:.2f})"
                    relevant_count += 1
                elif score >= (grade_threshold - 0.15):
                    # Borderline candidate
                    verdict = "partial"
                    reason = f"Borderline score ({score:.3f})"
                    borderline_chunks.append(rc)
                else:
                    verdict = "irrelevant"
                    reason = f"Low relevance score ({score:.3f} < {grade_threshold:.2f})"

                all_grades[cid] = {"verdict": verdict, "reason": reason, "score": score}

            # Check if identifier exact match is present
            has_id_match = any(
                getattr(rc.chunk, "circular_no", None)
                and getattr(rc.chunk, "circular_no") in sub_q.text
                for rc in chunks
            )

            # 2. FULL mode batch LLM grading ONLY for borderline chunks if relevant_count is below minimum
            if (
                state.mode == "full"
                and relevant_count < min_relevant_chunks
                and borderline_chunks
                and llm is not None
                and not isinstance(llm.provider, ExtractiveLLMProvider)
            ):
                passages_str = "\n\n".join(
                    f"[{rc.chunk.chunk_id}]: {rc.chunk.text[:300]}" for rc in borderline_chunks[:4]
                )
                prompt = prompt_template.replace("{question}", sub_q.text).replace(
                    "{passages}", passages_str
                )
                try:
                    res = llm.generate([{"role": "user", "content": prompt}], max_tokens=200)
                    state.budget.llm_calls_used += 1
                    state.budget.tokens_used += res.usage.get("total", 0)
                    parsed = res.parsed_json or {}
                    grades_dict = parsed.get("grades", {})
                    for bc in borderline_chunks:
                        cid = bc.chunk.chunk_id
                        if cid in grades_dict:
                            llm_verdict = str(grades_dict[cid].get("verdict", "partial")).lower()
                            llm_reason = str(grades_dict[cid].get("reason", "LLM graded"))
                            all_grades[cid] = {
                                "verdict": llm_verdict,
                                "reason": llm_reason,
                                "score": bc.rerank_score,
                            }
                            if llm_verdict == "relevant":
                                relevant_count += 1
                except Exception:
                    pass

            is_sub_q_satisfied = (
                (relevant_count >= min_relevant_chunks)
                or has_id_match
                or (len(chunks) > 0 and chunks[0].rerank_score >= 0.70)
            )
            if not is_sub_q_satisfied:
                all_satisfied = False

        state.grades.update(all_grades)

        tracer.event(
            "grade",
            {
                "round": state.rounds,
                "grades_summary": {
                    "relevant": sum(1 for g in all_grades.values() if g["verdict"] == "relevant"),
                    "partial": sum(1 for g in all_grades.values() if g["verdict"] == "partial"),
                    "irrelevant": sum(
                        1 for g in all_grades.values() if g["verdict"] == "irrelevant"
                    ),
                },
            },
        )

        if all_satisfied:
            span["outcome"] = "enough"
            return state, "enough"

        if state.rounds < max_retrieval_rounds:
            span["outcome"] = "rewrite_retry"
            return state, "rewrite_retry"

        span["outcome"] = "give_up"
        return state, "give_up"
