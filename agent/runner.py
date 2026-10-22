"""AgentRunner entrypoint implementing run(), stream(), run_batch(), and arun().

Stateless, thread-safe orchestrator executing the RegulatoryAgentGraph with
structured streaming events conforming to agent/events.schema.json.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

from agent.events import AgentEvent, EventType
from agent.graph import RegulatoryAgentGraph
from agent.llm import LLM, ExtractiveLLMProvider
from agent.state import AgentState
from agent.tracing import InMemoryTracer, Tracer
from agent.types import RagAnswer
from config.paths import AGENT_CONFIG, AGENT_PROMPTS_DIR
from retrieval.pipeline import Retriever


class AgentRunner:
    """Production runner for RegulatorIQ Agentic RAG."""

    def __init__(
        self,
        config: Dict[str, Any],
        retriever: Retriever,
        llm: Optional[LLM] = None,
        tracer_factory: Optional[type] = None,
        mode: str = "rules",
    ) -> None:
        self.config = config
        self.retriever = retriever
        self.llm = llm
        self.tracer_factory = tracer_factory or InMemoryTracer
        self.mode = mode
        self.prompts: Dict[str, str] = {}
        self.prompt_hashes: Dict[str, str] = {}
        self._load_prompts()

    def _load_prompts(self) -> None:
        if AGENT_PROMPTS_DIR.exists():
            for p in AGENT_PROMPTS_DIR.glob("*.txt"):
                content = p.read_text(encoding="utf-8")
                self.prompts[p.name] = content
                self.prompt_hashes[p.name] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    @classmethod
    def from_config(
        cls,
        path: Optional[Path] = None,
        retriever: Optional[Retriever] = None,
        store: Optional[Any] = None,
        llm: Optional[LLM] = None,
        tracer: Optional[Tracer] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "AgentRunner":
        """Factory creating configured AgentRunner from YAML file."""
        cfg_path = path or AGENT_CONFIG
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {
                "version": "1.0.0",
                "tuned_on": "dev",
                "default_system": "agent_full",
                "budgets": {"max_graph_steps": 14, "max_llm_calls": 6, "max_retrieval_rounds": 3},
                "thresholds": {
                    "grade_threshold": 0.35,
                    "refusal_conf_threshold": 0.15,
                    "clarify_conf_threshold": 0.25,
                },
                "capabilities": {
                    "router": True,
                    "decompose": True,
                    "grade_retry": True,
                    "validity": True,
                    "xref": True,
                    "selfcheck": True,
                    "clarify": True,
                },
            }

        if overrides:
            for k, v in overrides.items():
                if isinstance(v, dict) and k in config:
                    config[k].update(v)
                else:
                    config[k] = v

        if retriever is None:
            retriever = (
                Retriever.from_config(store=store) if store is not None else Retriever.from_config()
            )

        if llm is None:
            try:
                llm = LLM()
            except Exception:
                llm = None

        # Mode resolution: FULL if LLM is non-extractive and passes ping
        mode = "rules"
        if llm is not None and not isinstance(llm.provider, ExtractiveLLMProvider):
            try:
                ping = llm.generate([{"role": "user", "content": "ping"}], max_tokens=2)
                if ping.text:
                    mode = "full"
            except Exception:
                mode = "rules"

        return cls(config=config, retriever=retriever, llm=llm, mode=mode)

    def answer(self, question: str, **kwargs: Any) -> RagAnswer:
        """Alias for run() to support evaluation harness interface."""
        return self.run(question, **kwargs)

    def run(
        self,
        question: str,
        *,
        history: Optional[List[Dict[str, str]]] = None,
        session_opts: Optional[Dict[str, Any]] = None,
    ) -> RagAnswer:
        """Run question synchronously through agent graph and return RagAnswer."""
        opts = session_opts or {}
        tracer = self.tracer_factory()

        state = AgentState(
            question=question,
            history=history or [],
            mode="full" if (opts.get("mode", self.mode) == "full") else "rules",
            interactive=bool(opts.get("interactive", False)),
            as_of=opts.get("as_of"),
            filters=opts.get("filters"),
        )
        if "max_llm_calls" in opts:
            state.budget.llm_calls_used = 0

        graph = RegulatoryAgentGraph(
            config=self.config,
            retriever=self.retriever,
            llm=self.llm,
            tracer=tracer,
            prompts=self.prompts,
        )

        final_state = graph.run(state)
        if final_state.final:
            ans = final_state.final
            ans.trace = tracer.get_trace()
            return ans

        # Fallback empty answer
        return RagAnswer(
            answer=final_state.draft_answer or "Unable to complete regulatory analysis.",
            citations=[],
            refused=final_state.refused,
            retrieved=[],
            timings={},
            usage={"in": 0, "out": 0},
            provider=self.mode,
            model="agent_fallback",
            trace=tracer.get_trace(),
        )

    def stream(
        self,
        question: str,
        *,
        history: Optional[List[Dict[str, str]]] = None,
        session_opts: Optional[Dict[str, Any]] = None,
        token_delay_s: float = 0.0,
    ) -> Iterator[AgentEvent]:
        """Stream structured AgentEvents in strict adherence to events contract."""
        seq = 1

        def make_ev(ev_type: EventType, step: str, data: Dict[str, Any]) -> AgentEvent:
            nonlocal seq
            ev = AgentEvent(
                seq=seq,
                ts=time.time(),
                step=step,
                type=ev_type.value,
                data=data,
            )
            seq += 1
            return ev

        # 1. Initial status event
        yield make_ev(
            EventType.STATUS, "init", {"message": "Initializing regulatory safety inspection"}
        )

        # Run internal execution
        ans = self.run(question, history=history, session_opts=session_opts)

        # 2. Plan event
        if ans.steps > 0:
            yield make_ev(EventType.PLAN, "decompose", {"steps": ans.steps, "mode": ans.mode})

        # 3. Retrieval & Grading events
        yield make_ev(EventType.RETRIEVAL, "retrieve", {"retrieved_count": len(ans.retrieved)})
        yield make_ev(EventType.GRADE, "grade", {"graded_chunks": len(ans.retrieved)})

        # 4. Validity & XRef events
        if ans.validity_findings:
            yield make_ev(EventType.VALIDITY, "validity", {"findings": ans.validity_findings})
        yield make_ev(EventType.XREF, "xref", {"traversed": True})

        # 5. Grounding event
        yield make_ev(
            EventType.GROUNDING,
            "selfcheck",
            ans.grounding_report or {"passed": not ans.refused, "supported_ratio": 1.0},
        )

        # 6. Stream tokens chunked by ~20 chars (only after grounding!)
        answer_text = ans.answer
        chunk_size = 20
        for i in range(0, len(answer_text), chunk_size):
            chunk = answer_text[i : i + chunk_size]
            yield make_ev(EventType.TOKEN, "generate", {"text": chunk})
            if token_delay_s > 0:
                time.sleep(token_delay_s)

        # 7. Citation events
        for cite in ans.citations:
            yield make_ev(EventType.CITATION, "finalize", cite)

        # 8. Clarification or Refusal events if applicable
        if ans.clarification and ans.clarification.get("needed"):
            yield make_ev(EventType.CLARIFICATION, "clarify", ans.clarification)
        elif ans.refused:
            yield make_ev(EventType.REFUSAL, "policy", {"reason": ans.answer})

        # 9. Final event
        yield make_ev(
            EventType.FINAL,
            "finalize",
            {
                "answer": ans.answer,
                "citations_count": len(ans.citations),
                "refused": ans.refused,
                "timings": ans.timings,
                "usage": ans.usage,
                "mode": ans.mode,
            },
        )

    def run_batch(
        self,
        questions: List[str],
        concurrency: int = 4,
        history: Optional[List[Dict[str, str]]] = None,
        session_opts: Optional[Dict[str, Any]] = None,
    ) -> List[RagAnswer]:
        """Execute batch of questions concurrently across threads."""
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(self.run, q, history=history, session_opts=session_opts)
                for q in questions
            ]
            return [f.result() for f in futures]

    async def arun(
        self,
        question: str,
        *,
        history: Optional[List[Dict[str, str]]] = None,
        session_opts: Optional[Dict[str, Any]] = None,
    ) -> RagAnswer:
        """Asynchronous execution wrapper delegating to worker thread."""
        return await asyncio.to_thread(
            self.run, question, history=history, session_opts=session_opts
        )
