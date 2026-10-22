"""Typed AgentState definition using Pydantic v2.

Maintains all state across the lifecycle of an Agentic RAG invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from agent.types import RagAnswer


class SubQuestion(BaseModel):
    id: str = Field(..., description="Unique sub-question identifier e.g. 'q1'")
    text: str = Field(..., description="Self-contained query string")
    intent: Optional[str] = Field(default=None, description="Inferred intent")
    combine_strategy: Optional[str] = Field(
        default="merge", description="compare | merge | sequence"
    )


class PlanState(BaseModel):
    sub_questions: List[SubQuestion] = Field(default_factory=list)
    strategy: str = Field(default="direct", description="direct | decompose | compare | sequence")


class ClarificationState(BaseModel):
    needed: bool = False
    question: Optional[str] = None
    options: List[str] = Field(default_factory=list)


class BudgetState(BaseModel):
    llm_calls_used: int = 0
    tokens_used: int = 0
    retrieval_rounds: int = 0
    steps: int = 0
    started_at: float = Field(default_factory=time.time)


class AgentState(BaseModel):
    """Immutable state machine payload for LangGraph and fallback agent graph."""

    question: str
    history: List[Dict[str, str]] = Field(default_factory=list)
    standalone_question: str = ""
    mode: Literal["full", "rules"] = "rules"
    intent: str = "lookup"
    plan: PlanState = Field(default_factory=PlanState)
    filters: Optional[Dict[str, Any]] = None
    as_of: Optional[str] = None
    wants_history: bool = False

    # Evidence and evaluations
    evidence: Dict[str, List[Any]] = Field(default_factory=dict)
    grades: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    rounds: int = 0
    validity_findings: List[Dict[str, Any]] = Field(default_factory=list)
    xref_findings: List[Dict[str, Any]] = Field(default_factory=list)

    # Synthesis & checking
    draft_answer: str = ""
    grounding_report: Optional[Dict[str, Any]] = None
    final: Optional[RagAnswer] = None
    refused: bool = False
    refusal_reason: Optional[str] = None

    # Interactions & budgets
    clarification: ClarificationState = Field(default_factory=ClarificationState)
    budget: BudgetState = Field(default_factory=BudgetState)
    warnings: List[str] = Field(default_factory=list)
    trace: List[Dict[str, Any]] = Field(default_factory=list)

    # Session options
    interactive: bool = False
    cost_estimate: Dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "ignore",
    }
