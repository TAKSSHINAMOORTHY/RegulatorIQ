"""Selfcheck node: verify factual accuracy, claim grounding, and handle corrective regeneration."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from agent.llm import LLM, ExtractiveLLMProvider
from agent.selfcheck import GroundingReport, SelfChecker
from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.context import build_context


def node_selfcheck(
    state: AgentState,
    checker: SelfChecker,
    llm: Optional[LLM],
    tracer: Tracer,
    corrective_prompt_template: str,
    max_regenerations: int = 1,
) -> AgentState:
    """Audit draft answer for hallucinations, invalid citations, and unsupported figures."""
    with tracer.span("selfcheck", {"step": "selfcheck"}) as span:
        state.budget.steps += 1

        if state.refused or not state.draft_answer:
            span["skipped"] = True
            return state

        # Flatten evidence chunks
        all_rcs = []
        for sq in state.plan.sub_questions:
            all_rcs.extend(state.evidence.get(sq.id, []))
        bundle = build_context(all_rcs, token_budget=3000)
        context_chunks = [item.chunk for item in bundle.items]

        # First audit pass
        report = checker.audit(state.draft_answer, context_chunks, regenerated=False)

        # Corrective regeneration loop if check failed and in FULL mode
        regens = 0
        while not report.passed and regens < max_regenerations:
            regens += 1
            if state.mode == "full" and llm is not None and not isinstance(llm.provider, ExtractiveLLMProvider):
                unsupported_list = "\n".join(f"- {c['claim']}" for c in report.claims if c["status"] == "unsupported")
                failures_list = "\n".join(f"- {f}" for f in report.hard_check_failures)
                corr_prompt = (
                    f"Your previous regulatory compliance answer failed factual grounding verification.\n\n"
                    f"Unsupported claims:\n{unsupported_list}\n\n"
                    f"Grounding violations:\n{failures_list}\n\n"
                    f"Please rewrite the answer relying ONLY on verified facts in the context. "
                    f"Omit any claim that cannot be proven directly from the official citations.\n\n"
                    f"Context:\n{bundle.text}\n\n"
                    f"Question: {state.standalone_question or state.question}\n\n"
                    f"Return JSON: {{\"answer\": \"...\", \"citations\": [...]}}"
                )
                try:
                    res = llm.generate([{"role": "user", "content": corr_prompt}], max_tokens=1024)
                    state.budget.llm_calls_used += 1
                    state.budget.tokens_used += res.usage.get("total", 0)
                    parsed = res.parsed_json or {}
                    state.draft_answer = str(parsed.get("answer", res.text.strip()))
                    report = checker.audit(state.draft_answer, context_chunks, regenerated=True)
                except Exception:
                    break
            else:
                break

        # If still failing after regeneration -> prune unsupported sentences
        if not report.passed:
            pruned_text, redacted_sentences = checker.prune_unsupported_sentences(state.draft_answer, report)
            if pruned_text.strip() and len(pruned_text.split()) >= 10:
                state.draft_answer = pruned_text
                state.warnings.append("partially_redacted: ungrounded regulatory claims removed")
                report.redacted_sentences = redacted_sentences
                report.passed = True
            else:
                # Refuse partial
                state.refused = True
                state.refusal_reason = "I couldn't verify enough of this answer from official RBI documents in the repository."
                state.draft_answer = f"{state.refusal_reason}\n\nVerified fragment:\n{pruned_text}"
                report.redacted_sentences = redacted_sentences

        state.grounding_report = {
            "passed": report.passed,
            "supported_ratio": report.supported_ratio,
            "hard_check_failures": report.hard_check_failures,
            "judge_type": report.judge_type,
            "regenerated": report.regenerated,
            "redacted_sentences": report.redacted_sentences,
            "claims": report.claims,
        }

        span["passed"] = report.passed
        span["supported_ratio"] = report.supported_ratio
        tracer.event("grounding", state.grounding_report)
        return state
