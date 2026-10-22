"""Agentic RAG StateGraph assembly using LangGraph and budget-enforcing state machine.

Implements the complete regulatory intelligence workflow:
guard -> condense -> route -> clarify -> decompose -> retrieve -> grade -> validity -> xref -> generate -> selfcheck -> finalize -> END
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from agent.guards import SafetyGuard
from agent.llm import LLM
from agent.nodes.clarify import node_clarify
from agent.nodes.condense import node_condense
from agent.nodes.decompose import node_decompose
from agent.nodes.finalize import node_finalize
from agent.nodes.generate import node_generate
from agent.nodes.grade import node_grade
from agent.nodes.guard import node_guard
from agent.nodes.retrieve import node_retrieve
from agent.nodes.rewrite_retry import node_rewrite_retry
from agent.nodes.route import node_route
from agent.nodes.selfcheck import node_selfcheck
from agent.nodes.validity import node_validity
from agent.nodes.xref import node_xref
from agent.policy import RefusalPolicy
from agent.selfcheck import SelfChecker
from agent.state import AgentState, SubQuestion
from agent.tracing import NoopTracer, Tracer
from agent.validity import ValidityResolver
from agent.xref import XRefTraverser
from retrieval.pipeline import Retriever
from retrieval.query_analysis import QueryAnalyzer
from retrieval.rewrite import QueryRewriter


class RegulatoryAgentGraph:
    """Configured LangGraph execution graph for RBI compliance queries."""

    def __init__(
        self,
        config: Dict[str, Any],
        retriever: Retriever,
        llm: Optional[LLM] = None,
        tracer: Optional[Tracer] = None,
        prompts: Optional[Dict[str, str]] = None,
    ) -> None:
        self.config = config
        self.retriever = retriever
        self.llm = llm
        self.tracer: Tracer = tracer or NoopTracer()
        self.prompts = prompts or {}

        # Budgets and thresholds
        budgets = config.get("budgets", {})
        self.max_steps = int(budgets.get("max_graph_steps", 14))
        self.max_llm_calls = int(budgets.get("max_llm_calls", 6))
        self.max_rounds = int(budgets.get("max_retrieval_rounds", 3))
        self.timeout_s = float(budgets.get("wall_clock_timeout_s", 25.0))
        self.max_subquestions = int(budgets.get("max_subquestions", 4))
        self.token_budget = int(budgets.get("context_token_budget", 3000))

        thresholds = config.get("thresholds", {})
        self.grade_threshold = float(thresholds.get("grade_threshold", 0.35))
        self.min_relevant = int(thresholds.get("min_relevant_chunks", 2))
        self.refusal_threshold = float(thresholds.get("refusal_conf_threshold", 0.15))
        self.clarify_threshold = float(thresholds.get("clarify_conf_threshold", 0.25))

        caps = config.get("capabilities", {})
        self.enable_router = bool(caps.get("router", True))
        self.enable_decompose = bool(caps.get("decompose", True))
        self.enable_grade_retry = bool(caps.get("grade_retry", True))
        self.enable_validity = bool(caps.get("validity", True))
        self.enable_xref = bool(caps.get("xref", True))
        self.enable_selfcheck = bool(caps.get("selfcheck", True))
        self.enable_clarify = bool(caps.get("clarify", True))

        # Helper components
        self.guard = SafetyGuard()
        self.policy = RefusalPolicy(
            refusal_conf_threshold=self.refusal_threshold,
            clarify_conf_threshold=self.clarify_threshold,
            min_relevant_chunks=self.min_relevant,
        )
        self.analyzer = QueryAnalyzer()
        self.rewriter = QueryRewriter(llm=self.llm)
        self.validity_resolver = ValidityResolver(store=self.retriever.store)
        self.xref_traverser = XRefTraverser(store=self.retriever.store)
        self.selfchecker = SelfChecker()

        self.graph = self._build_graph()

    def _check_budget(self, state: AgentState) -> bool:
        """Return True if hard budget or timeout is exceeded."""
        elapsed = time.time() - state.budget.started_at
        if state.budget.steps >= self.max_steps:
            state.warnings.append("degraded_budget: max_graph_steps reached")
            return True
        if state.budget.llm_calls_used >= self.max_llm_calls:
            state.warnings.append("degraded_budget: max_llm_calls reached")
            state.mode = "rules"  # switch rest of run to rules
            return False
        if elapsed >= self.timeout_s:
            state.warnings.append("degraded_budget: wall_clock_timeout reached")
            return True
        return False

    def _build_graph(self) -> Any:
        builder = StateGraph(AgentState)

        # 1. Guard
        def step_guard(state: AgentState) -> AgentState:
            return node_guard(state, self.guard, self.policy, self.tracer)

        # 2. Condense
        def step_condense(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            tmpl = self.prompts.get("condense.v1.txt", "{question}")
            return node_condense(state, self.llm, self.analyzer, self.tracer, tmpl)

        # 3. Route
        def step_route(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            if not self.enable_router:
                state.intent = "lookup"
                return state
            tmpl = self.prompts.get("router.v1.txt", "{question}")
            return node_route(state, self.analyzer, self.llm, self.tracer, tmpl)

        # Direct chitchat handler
        def step_direct_chitchat(state: AgentState) -> AgentState:
            state.draft_answer = (
                "Hello! I am RegulatorIQ, an AI compliance assistant for the Reserve Bank of India (RBI). "
                "How can I assist you with banking circulars, master directions, or regulatory norms today?"
            )
            state.refused = False
            return state

        # 4. Clarify
        def step_clarify(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            if not self.enable_clarify:
                return state
            tmpl = self.prompts.get("clarify.v1.txt", "{question}")
            return node_clarify(state, self.llm, self.tracer, tmpl)

        # 5. Decompose
        def step_decompose(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            if not self.enable_decompose:
                state.plan.sub_questions = [
                    SubQuestion(
                        id="q1",
                        text=state.standalone_question or state.question,
                        combine_strategy="direct",
                    )
                ]
                return state
            tmpl = self.prompts.get("decompose.v1.txt", "{question}")
            return node_decompose(state, self.llm, self.tracer, tmpl, self.max_subquestions)

        # 6. Retrieve
        def step_retrieve(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            return node_retrieve(state, self.retriever, self.tracer)

        # 7. Grade
        def step_grade(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            if not self.enable_grade_retry:
                return state
            tmpl = self.prompts.get("grade.v1.txt", "{question}")
            s, _ = node_grade(
                state,
                self.llm,
                self.tracer,
                tmpl,
                self.grade_threshold,
                self.min_relevant,
                self.max_rounds,
            )
            return s

        # 8. Rewrite Retry
        def step_rewrite_retry(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            tmpl = self.prompts.get("rewrite.v1.txt", "{question}")
            return node_rewrite_retry(
                state, self.analyzer, self.rewriter, self.llm, self.tracer, tmpl
            )

        # 9. Validity
        def step_validity(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            if not self.enable_validity:
                return state
            return node_validity(state, self.validity_resolver, self.tracer)

        # 10. XRef
        def step_xref(state: AgentState) -> AgentState:
            if self._check_budget(state):
                return state
            if not self.enable_xref:
                return state
            return node_xref(state, self.xref_traverser, self.tracer)

        # 11. Generate
        def step_generate(state: AgentState) -> AgentState:
            if state.budget.steps >= self.max_steps:
                state.warnings.append("degraded_budget: max_graph_steps reached")
            tmpl = self.prompts.get("generate.v1.txt", "{context}\n{question}")
            return node_generate(state, self.llm, self.tracer, tmpl, self.token_budget)

        # 12. Selfcheck
        def step_selfcheck(state: AgentState) -> AgentState:
            if state.budget.steps >= self.max_steps:
                return state
            if not self.enable_selfcheck:
                return state
            tmpl = self.prompts.get("selfcheck.v1.txt", "{context}")
            return node_selfcheck(state, self.selfchecker, self.llm, self.tracer, tmpl)

        # 13. Finalize
        def step_finalize(state: AgentState) -> AgentState:
            return node_finalize(state, self.tracer, max_steps=self.max_steps)

        # Add Nodes to Graph
        builder.add_node("guard", step_guard)
        builder.add_node("condense", step_condense)
        builder.add_node("route", step_route)
        builder.add_node("direct_chitchat", step_direct_chitchat)
        builder.add_node("clarify", step_clarify)
        builder.add_node("decompose", step_decompose)
        builder.add_node("retrieve", step_retrieve)
        builder.add_node("grade", step_grade)
        builder.add_node("rewrite_retry", step_rewrite_retry)
        builder.add_node("validity", step_validity)
        builder.add_node("xref", step_xref)
        builder.add_node("generate", step_generate)
        builder.add_node("selfcheck", step_selfcheck)
        builder.add_node("finalize", step_finalize)

        # Edge logic
        builder.add_edge(START, "guard")

        def route_after_guard(s: AgentState) -> str:
            return "finalize" if s.refused else "condense"

        builder.add_conditional_edges(
            "guard", route_after_guard, {"finalize": "finalize", "condense": "condense"}
        )
        builder.add_edge("condense", "route")

        def route_after_route(s: AgentState) -> str:
            if s.intent == "chitchat":
                return "direct_chitchat"
            if s.interactive and "ambiguous" in (s.standalone_question or s.question).lower():
                return "clarify"
            return "decompose"

        builder.add_conditional_edges(
            "route",
            route_after_route,
            {"direct_chitchat": "direct_chitchat", "clarify": "clarify", "decompose": "decompose"},
        )

        builder.add_edge("direct_chitchat", "finalize")

        def route_after_clarify(s: AgentState) -> str:
            return "finalize" if (s.clarification and s.clarification.needed) else "decompose"

        builder.add_conditional_edges(
            "clarify", route_after_clarify, {"finalize": "finalize", "decompose": "decompose"}
        )
        builder.add_edge("decompose", "retrieve")
        builder.add_edge("retrieve", "grade")

        def route_after_grade(s: AgentState) -> str:
            if (s.budget.steps + 5 >= self.max_steps) or (
                time.time() - s.budget.started_at >= self.timeout_s
            ):
                return "validity"
            if not self.enable_grade_retry:
                return "validity"
            # Evaluate grades across all chunks
            has_relevant = any(g.get("verdict") == "relevant" for g in s.grades.values())
            if not has_relevant and s.rounds < self.max_rounds:
                return "rewrite_retry"
            return "validity"

        builder.add_conditional_edges(
            "grade",
            route_after_grade,
            {"rewrite_retry": "rewrite_retry", "validity": "validity"},
        )

        builder.add_edge("rewrite_retry", "retrieve")
        builder.add_edge("validity", "xref")
        builder.add_edge("xref", "generate")
        builder.add_edge("generate", "selfcheck")
        builder.add_edge("selfcheck", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

    def run(self, state: AgentState) -> AgentState:
        """Execute state through compiled graph to completion."""
        res_dict = self.graph.invoke(state)
        if isinstance(res_dict, AgentState):
            return res_dict
        if isinstance(res_dict, dict):
            return AgentState.model_validate(res_dict)
        return state
