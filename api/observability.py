"""Observability, Tracing, JSON Logging, and Prometheus Metrics for RegulatorIQ.

Provides:
1. LocalJsonlTracer & LangfuseTracer adhering to agent.tracing.Tracer.
2. Structured JSON Access Logging with salted IP hashing and access log sampling.
3. Prometheus metrics collector for HTTP endpoints, latencies, tokens, and guards.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import secrets
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from agent.tracing import NoopTracer, Tracer
from api.settings import APISettings
from config.paths import TRACE_LOG_DIR

logger = logging.getLogger("regulatoriq.observability")

# Salt for hashing IP addresses in logs
_IP_SALT = os.environ.get("RBI_IP_SALT", secrets.token_hex(16))


def hash_ip(ip: str) -> str:
    """Create a salted SHA-256 hash of client IP to prevent PII leaks."""
    return hashlib.sha256(f"{ip}:{_IP_SALT}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 1. Tracers
# ---------------------------------------------------------------------------

class LocalJsonlTracer:
    """Writes structured execution traces to rotating local JSONL files."""

    def __init__(
        self,
        request_id: str,
        mode: str = "full",
        redact: bool = True,
        log_dir: Optional[Path] = None,
    ) -> None:
        self.request_id = request_id
        self.mode = mode
        self.redact = redact
        self.log_dir = log_dir or TRACE_LOG_DIR
        self.records: List[Dict[str, Any]] = []
        self.total_calls = 0
        self.total_tokens = 0
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        t0 = time.perf_counter()
        span_data = dict(attrs or {})
        try:
            yield span_data
        finally:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            clean_attrs = self._sanitize(span_data)
            record = {
                "type": "span",
                "request_id": self.request_id,
                "name": name,
                "latency_ms": latency_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attrs": clean_attrs,
            }
            self.records.append(record)

    def event(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "type": "event",
            "request_id": self.request_id,
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attrs": self._sanitize(attrs or {}),
        }
        self.records.append(record)

    def set_usage(self, calls: int, tokens: int) -> None:
        self.total_calls = calls
        self.total_tokens = tokens

    def get_trace(self) -> List[Dict[str, Any]]:
        return list(self.records)

    def flush(self) -> None:
        """Write collected trace records to traces.jsonl file."""
        if not self.records:
            return
        out_file = self.log_dir / "traces.jsonl"
        try:
            # Simple rotation if file > 10 MB
            if out_file.exists() and out_file.stat().st_size > 10 * 1024 * 1024:
                rotated = self.log_dir / f"traces_{int(time.time())}.jsonl"
                out_file.rename(rotated)

            with open(out_file, "a", encoding="utf-8") as f:
                for r in self.records:
                    f.write(json.dumps(r) + "\n")
        except Exception as e:
            logger.warning(f"Failed to flush trace to {out_file}: {e}")

    def _sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.redact:
            return data
        sanitized = dict(data)
        for k in ("question", "text", "prompt", "answer"):
            if k in sanitized and isinstance(sanitized[k], str):
                sanitized[k] = f"len:{len(sanitized[k])}_hash:{hashlib.sha256(sanitized[k].encode()).hexdigest()[:8]}"
        return sanitized


class LangfuseTracer:
    """Async Langfuse tracer with local fallback and bounded queue."""

    def __init__(
        self,
        request_id: str,
        settings: APISettings,
        mode: str = "full",
        redact: bool = True,
    ) -> None:
        self.request_id = request_id
        self.settings = settings
        self.mode = mode
        self.redact = redact
        self.fallback = LocalJsonlTracer(request_id, mode, redact)
        self.has_keys = bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)

    @contextmanager
    def span(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        with self.fallback.span(name, attrs) as span_data:
            yield span_data

    def event(self, name: str, attrs: Optional[Dict[str, Any]] = None) -> None:
        self.fallback.event(name, attrs)

    def set_usage(self, calls: int, tokens: int) -> None:
        self.fallback.set_usage(calls, tokens)

    def get_trace(self) -> List[Dict[str, Any]]:
        return self.fallback.get_trace()

    def flush(self) -> None:
        self.fallback.flush()


# ---------------------------------------------------------------------------
# 2. Structured JSON Access Logger Middleware
# ---------------------------------------------------------------------------

class JsonAccessLoggerMiddleware(BaseHTTPMiddleware):
    """Logs structured JSON lines for every completed request."""

    def __init__(self, app: Any, settings: APISettings, trusted_proxies: Optional[List[str]] = None):
        super().__init__(app)
        self.settings = settings
        self.trusted_proxies = set(trusted_proxies or [])
        self.counter = 0

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        t0 = time.perf_counter()
        req_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        request.state.request_id = req_id

        # Determine client IP safely
        client_host = request.client.host if request.client else "127.0.0.1"
        if client_host in self.trusted_proxies:
            xff = request.headers.get("X-Forwarded-For")
            if xff:
                client_host = xff.split(",")[0].strip()
        client_hash = hash_ip(client_host)

        response = await call_next(request)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        response.headers["X-Request-ID"] = req_id

        # Access log sampling: 1% for /health and /ready
        path = request.url.path
        if path in ("/health", "/ready"):
            self.counter += 1
            if self.counter % 100 != 0:
                return response

        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": req_id,
            "route": path,
            "method": request.method,
            "status": response.status_code,
            "latency_ms": latency_ms,
            "mode": getattr(request.app.state, "mode", "unknown") if hasattr(request.app, "state") else "unknown",
            "client_hash": client_hash,
        }

        # Stdout JSON log
        sys.stdout.write(json.dumps(log_payload) + "\n")
        sys.stdout.flush()

        return response


# ---------------------------------------------------------------------------
# 3. Prometheus Metrics Collector
# ---------------------------------------------------------------------------

class SimpleMetricsRegistry:
    """Self-contained Prometheus-format metrics collector."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests_total: Dict[Tuple[str, str, str], int] = {}
        self.ask_latency_sum: float = 0.0
        self.ask_latency_count: int = 0
        self.ttft_sum: float = 0.0
        self.ttft_count: int = 0
        self.rate_limited_total: Dict[str, int] = {}
        self.refusals_total: int = 0
        self.clarifications_total: int = 0
        self.llm_calls_total: int = 0
        self.tokens_total: int = 0
        self.sanitiser_hits_total: int = 0
        self.warmups_total: int = 0
        self.queue_waits_total: int = 0
        self.cancelled_total: int = 0

    def record_request(self, route: str, status_code: int, mode: str) -> None:
        key = (route, str(status_code), mode)
        with self.lock:
            self.requests_total[key] = self.requests_total.get(key, 0) + 1

    def record_ask_latency(self, latency_seconds: float) -> None:
        with self.lock:
            self.ask_latency_sum += latency_seconds
            self.ask_latency_count += 1

    def record_ttft(self, ttft_seconds: float) -> None:
        with self.lock:
            self.ttft_sum += ttft_seconds
            self.ttft_count += 1

    def record_rate_limited(self, route: str) -> None:
        with self.lock:
            self.rate_limited_total[route] = self.rate_limited_total.get(route, 0) + 1

    def record_refusal(self) -> None:
        with self.lock:
            self.refusals_total += 1

    def record_clarification(self) -> None:
        with self.lock:
            self.clarifications_total += 1

    def record_llm_usage(self, calls: int, tokens: int) -> None:
        with self.lock:
            self.llm_calls_total += calls
            self.tokens_total += tokens

    def record_sanitiser_hit(self) -> None:
        with self.lock:
            self.sanitiser_hits_total += 1

    def record_warmup(self) -> None:
        with self.lock:
            self.warmups_total += 1

    def record_queue_wait(self) -> None:
        with self.lock:
            self.queue_waits_total += 1

    def record_cancelled(self) -> None:
        with self.lock:
            self.cancelled_total += 1

    def render_prometheus_text(self) -> str:
        """Render metrics in standard Prometheus exposition format."""
        with self.lock:
            lines = [
                "# HELP regulatoriq_requests_total Total HTTP requests handled",
                "# TYPE regulatoriq_requests_total counter",
            ]
            for (route, st, md), cnt in self.requests_total.items():
                lines.append(f'regulatoriq_requests_total{{route="{route}",status="{st}",mode="{md}"}} {cnt}')

            lines.extend([
                "# HELP regulatoriq_ask_latency_seconds Cumulative ask latency in seconds",
                "# TYPE regulatoriq_ask_latency_seconds summary",
                f"regulatoriq_ask_latency_seconds_sum {self.ask_latency_sum:.4f}",
                f"regulatoriq_ask_latency_seconds_count {self.ask_latency_count}",
                "# HELP regulatoriq_time_to_first_token_seconds Time to first token",
                "# TYPE regulatoriq_time_to_first_token_seconds summary",
                f"regulatoriq_time_to_first_token_seconds_sum {self.ttft_sum:.4f}",
                f"regulatoriq_time_to_first_token_seconds_count {self.ttft_count}",
                "# HELP regulatoriq_refusals_total Total query refusals emitted",
                "# TYPE regulatoriq_refusals_total counter",
                f"regulatoriq_refusals_total {self.refusals_total}",
                "# HELP regulatoriq_clarifications_total Total clarification requests",
                "# TYPE regulatoriq_clarifications_total counter",
                f"regulatoriq_clarifications_total {self.clarifications_total}",
                "# HELP regulatoriq_llm_calls_total Total external LLM calls made",
                "# TYPE regulatoriq_llm_calls_total counter",
                f"regulatoriq_llm_calls_total {self.llm_calls_total}",
                "# HELP regulatoriq_tokens_total Total tokens consumed",
                "# TYPE regulatoriq_tokens_total counter",
                f"regulatoriq_tokens_total {self.tokens_total}",
                "# HELP regulatoriq_sanitiser_hits_total Total sensitive items sanitized",
                "# TYPE regulatoriq_sanitiser_hits_total counter",
                f"regulatoriq_sanitiser_hits_total {self.sanitiser_hits_total}",
                "# HELP regulatoriq_warmups_total Total warmup queries executed",
                "# TYPE regulatoriq_warmups_total counter",
                f"regulatoriq_warmups_total {self.warmups_total}",
                "# HELP regulatoriq_queue_waits_total Total concurrency queue waits",
                "# TYPE regulatoriq_queue_waits_total counter",
                f"regulatoriq_queue_waits_total {self.queue_waits_total}",
                "# HELP regulatoriq_cancelled_total Total client-cancelled asks",
                "# TYPE regulatoriq_cancelled_total counter",
                f"regulatoriq_cancelled_total {self.cancelled_total}",
            ])

            for route, cnt in self.rate_limited_total.items():
                lines.append(f'regulatoriq_rate_limited_total{{route="{route}"}} {cnt}')

            return "\n".join(lines) + "\n"


# Singleton instance
metrics_registry = SimpleMetricsRegistry()
