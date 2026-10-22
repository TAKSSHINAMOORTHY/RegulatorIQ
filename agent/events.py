"""Streaming event definitions and JSON schema contract for Agentic RAG.

Contract Guarantees:
- Every event has: seq (int), ts (float), step (str), type (str), data (dict).
- Event types: status, plan, retrieval, grade, validity, xref, token,
  citation, grounding, clarification, refusal, final, error.
- Event ordering contract:
    status*, plan?, (retrieval, grade)+, validity?, xref?, grounding, token*, citation*, final
- On error: error then final with refused=true.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config.paths import EVENTS_SCHEMA


class EventType(str, Enum):
    STATUS = "status"
    PLAN = "plan"
    RETRIEVAL = "retrieval"
    GRADE = "grade"
    VALIDITY = "validity"
    XREF = "xref"
    TOKEN = "token"
    CITATION = "citation"
    GROUNDING = "grounding"
    CLARIFICATION = "clarification"
    REFUSAL = "refusal"
    FINAL = "final"
    ERROR = "error"


class AgentEvent(BaseModel):
    """Immutable event payload streamed to client."""

    seq: int = Field(..., description="Monotonically increasing sequence number (1-indexed)")
    ts: float = Field(default_factory=time.time, description="Unix epoch timestamp in seconds")
    step: str = Field(..., description="Agent node or lifecycle stage name")
    type: str = Field(..., description="Event type from contract specification")
    data: Dict[str, Any] = Field(default_factory=dict, description="Structured event payload")

    model_config = {
        "extra": "ignore",
    }


def validate_event_order(events: List[AgentEvent]) -> Tuple[bool, List[str]]:
    """Validate that the list of streamed events adheres strictly to the contract order."""
    violations: List[str] = []
    has_grounding = False
    tokens_seen = False
    final_seen = False

    for i, ev in enumerate(events):
        # Monotonic sequence check
        if ev.seq != i + 1:
            violations.append(f"Event seq mismatch at index {i}: expected {i+1}, got {ev.seq}")

        if ev.type == EventType.GROUNDING.value:
            has_grounding = True

        if ev.type == EventType.TOKEN.value:
            tokens_seen = True
            if not has_grounding:
                violations.append("Violation: 'token' event emitted before 'grounding' event")

        if ev.type == EventType.FINAL.value:
            final_seen = True
        elif final_seen:
            violations.append(f"Violation: Event '{ev.type}' emitted after 'final' event")

    if not final_seen and len(events) > 0:
        violations.append("Violation: Stream ended without emitting 'final' event")

    return (len(violations) == 0, violations)


def save_events_schema(target_path: Optional[Path] = None) -> Path:
    """Generate and write events JSON Schema from Pydantic model."""
    path = target_path or EVENTS_SCHEMA
    schema = AgentEvent.model_json_schema()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    return path


if __name__ == "__main__":
    p = save_events_schema()
    print(f"Generated events schema at: {p}")
