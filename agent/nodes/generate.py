"""Generate node: draft regulatory answer with structured citations and document statuses."""

from __future__ import annotations

import re
from typing import Optional

from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState
from agent.tracing import Tracer
from retrieval.context import build_context


def node_generate(
    state: AgentState,
    llm: Optional[LLM],
    tracer: Tracer,
    prompt_template: str,
    token_budget: int = 3000,
) -> AgentState:
    """Generate drafted regulatory compliance answer in FULL or RULES mode."""
    with tracer.span("generate", {"step": "generate", "mode": state.mode}) as span:
        state.budget.steps += 1

        # Flatten evidence in sub-question priority order
        all_rcs = []
        for sq in state.plan.sub_questions:
            all_rcs.extend(state.evidence.get(sq.id, []))

        # Assemble deduplicated, budgeted context bundle
        bundle = build_context(all_rcs, token_budget=token_budget)
        span["context_tokens"] = bundle.token_count
        span["context_items"] = len(bundle.items)

        if not bundle.items:
            state.draft_answer = "No official Reserve Bank of India documents in the repository contain evidence answering this question."
            state.refused = True
            state.refusal_reason = state.draft_answer
            return state

        # Prepare status summaries from validity findings
        status_lines = []
        for vf in state.validity_findings:
            if vf.get("explanation"):
                status_lines.append(f"Document Status: {vf['explanation']}")

        status_block = "\n".join(status_lines)

        # 1. FULL mode: generative LLM
        if (
            state.mode == "full"
            and llm is not None
            and not isinstance(llm.provider, ExtractiveLLMProvider)
        ):
            full_context = bundle.text
            if status_block:
                full_context += f"\n\n{status_block}"

            prompt = prompt_template.replace("{context}", full_context).replace(
                "{question}", state.standalone_question or state.question
            )
            try:
                res = llm.generate([{"role": "user", "content": prompt}], max_tokens=1024)
                state.budget.llm_calls_used += 1
                state.budget.tokens_used += res.usage.get("total", 0)
                parsed = res.parsed_json or {}
                if parsed.get("refused"):
                    state.refused = True
                    state.refusal_reason = str(
                        parsed.get("refusal_reason", "Insufficient official evidence")
                    )
                    state.draft_answer = str(parsed.get("answer", state.refusal_reason))
                else:
                    ans_text = str(parsed.get("answer", res.text.strip()))
                    state.draft_answer = ans_text
                return state
            except Exception:
                state.warnings.append(
                    "LLM generation failed, falling back to extractive rules mode"
                )

        # 2. RULES mode: deterministic extractive answer synthesis
        lines = []
        assumptions = [w for w in state.warnings if "Assuming" in w]
        if assumptions:
            lines.append(f"Assumptions: {assumptions[0]}")

        for i, item in enumerate(bundle.items[:3], start=1):
            c = item.chunk
            circ = getattr(c, "circular_no", None) or "RBI Directive"
            # Extract first 2 complete sentences from chunk
            sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", c.text) if s.strip()]
            for s in sents[:2]:
                clean_s = s.rstrip(".")
                lines.append(f"Under {circ}, {clean_s} [{i}].")

        if status_lines:
            lines.append("\n" + "\n".join(status_lines))

        state.draft_answer = "\n\n".join(lines)
        return state
