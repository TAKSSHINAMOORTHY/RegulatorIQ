"""Tracing protocol and implementations for agent observability.

Provides:
- Tracer protocol with span() context manager, event(), and set_usage()
- NoopTracer (zero-overhead default)
- InMemoryTracer (records spans and events for testing, debugging, and returning in RagAnswer.trace)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Protocol


class Tracer(Protocol):
    """Protocol for tracing agent execution across nodes and spans."""

    def span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        ...

    def event(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> None:
        ...

    def set_usage(self, calls: int, tokens: int) -> None:
        ...

    def get_trace(self) -> List[Dict[str, Any]]:
        ...


class NoopTracer:
    """Zero-overhead no-op tracer."""

    @contextmanager
    def span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        yield attrs or {}

    def event(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> None:
        pass

    def set_usage(self, calls: int, tokens: int) -> None:
        pass

    def get_trace(self) -> List[Dict[str, Any]]:
        return []


class InMemoryTracer:
    """Thread-local in-memory tracer that collects spans and events."""

    def __init__(self, redact_text: bool = False) -> None:
        self.redact_text = redact_text
        self.records: List[Dict[str, Any]] = []
        self.total_calls = 0
        self.total_tokens = 0

    @contextmanager
    def span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        start_t = time.perf_counter()
        span_data = dict(attrs or {})
        span_record: Dict[str, Any] = {
            "type": "span",
            "name": name,
            "start_time": time.time(),
            "attrs": span_data,
        }
        try:
            yield span_data
        finally:
            elapsed_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
            span_record["latency_ms"] = elapsed_ms
            span_record["attrs"] = self._sanitize(span_data)
            self.records.append(span_record)

    def event(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> None:
        self.records.append(
            {
                "type": "event",
                "name": name,
                "timestamp": time.time(),
                "attrs": self._sanitize(attrs or {}),
            }
        )

    def set_usage(self, calls: int, tokens: int) -> None:
        self.total_calls = calls
        self.total_tokens = tokens

    def get_trace(self) -> List[Dict[str, Any]]:
        return list(self.records)

    def _sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.redact_text:
            return data
        sanitized = dict(data)
        for k in ("question", "raw_query", "text", "prompt"):
            if k in sanitized:
                sanitized[k] = "[REDACTED]"
        return sanitized
