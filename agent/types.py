"""Common types for agent and LLM interactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMResult:
    """Standard result returned by LLM adapter."""

    text: str = ""
    parsed_json: Optional[Dict[str, Any]] = None
    usage: Dict[str, int] = field(default_factory=lambda: {"in": 0, "out": 0})
    provider: str = ""
    model: str = ""
    cached: bool = False
    latency_s: float = 0.0
    error: Optional[str] = None


@dataclass
class Citation:
    """Citation information linking answer to source chunk."""

    ref_num: int
    chunk_id: str
    doc_id: str
    circular_no: Optional[str] = None
    title: str = ""
    issue_date: Optional[str] = None
    para_ref: Optional[str] = None
    page_start: Optional[int] = None
    source_url: str = ""


@dataclass
class RagAnswer:
    """Standardized response from RAG pipelines."""

    answer: str
    citations: List[Dict[str, Any]]
    refused: bool
    retrieved: List[Dict[str, Any]]
    timings: Dict[str, float]
    usage: Dict[str, int]
    provider: str
    model: str
    trace: List[Dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    llm_calls: int = 0
    clarification: Optional[Dict[str, Any]] = None
    validity_findings: List[Dict[str, Any]] = field(default_factory=list)
    grounding_report: Optional[Dict[str, Any]] = None
    mode: str = "rules"
    degraded_flags: List[str] = field(default_factory=list)
    disclaimer_key: str = "regulatory_disclaimer"

    def to_dict(self) -> Dict[str, Any]:
        """Convert RagAnswer dataclass to dictionary."""
        from dataclasses import asdict

        return asdict(self)
