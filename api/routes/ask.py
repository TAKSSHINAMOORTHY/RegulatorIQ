"""Ask Endpoint for RegulatorIQ API.

POST /ask executes agentic regulatory retrieval and reasoning.
Supports both SSE streaming (Accept: text/event-stream) and non-streaming (Accept: application/json),
enforcing concurrency semaphores, queue timeouts, client disconnect cancellation,
request execution timeouts, rate limits, and output sanitization.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from agent.events import AgentEvent
from agent.types import RagAnswer
from api.budget import GlobalBudgetGuard
from api.deps import (
    get_current_budget_guard,
    get_current_rate_limiter,
    get_current_settings,
    get_current_state,
    get_request_client_ip,
    verify_api_key,
)
from api.errors import RateLimitExceeded, ServiceUnavailable
from api.observability import LocalJsonlTracer, metrics_registry
from api.ratelimit import RateLimiter
from api.schemas import AskRequest
from api.security import sanitize_citations, sanitize_text
from api.settings import APISettings
from api.sse import format_sse_comment, format_sse_event
from api.state import AppState

logger = logging.getLogger("regulatoriq.ask")

router = APIRouter(tags=["Regulatory Q&A"])

# Global concurrency semaphore initialized on app startup
_ask_semaphore: Optional[asyncio.Semaphore] = None


def get_ask_semaphore(max_concurrent: int = 2) -> asyncio.Semaphore:
    """Get or create singleton concurrency semaphore."""
    global _ask_semaphore
    if _ask_semaphore is None:
        _ask_semaphore = asyncio.Semaphore(max_concurrent)
    return _ask_semaphore


@router.post("/ask", dependencies=[Depends(verify_api_key)])
async def ask_question(
    request: Request,
    body: AskRequest,
    accept: Optional[str] = Header(default="text/event-stream"),
    client_ip: str = Depends(get_request_client_ip),
    settings: APISettings = Depends(get_current_settings),
    state: AppState = Depends(get_current_state),
    limiter: RateLimiter = Depends(get_current_rate_limiter),
    budget_guard: GlobalBudgetGuard = Depends(get_current_budget_guard),
) -> Any:
    """Execute regulatory analysis with streaming SSE or non-streaming JSON."""
    req_id = getattr(request.state, "request_id", secrets.token_hex(8))

    # 1. Rate Limiting Check
    if limiter:
        allowed, retry_after = limiter.check_ask_rate_limit(client_ip)
        if not allowed:
            metrics_registry.record_rate_limited("/ask")
            raise RateLimitExceeded(retry_after)

    # 2. Engine Readiness Check
    if not state.is_ready or not state.agent_runner:
        raise ServiceUnavailable(
            message=state.failure_hint
            or "Engine is bootstrapping models and index. Please retry shortly.",
            retry_after_s=5,
        )

    # 3. Concurrency Semaphore Acquisition with Queue Timeout
    semaphore = get_ask_semaphore(settings.MAX_CONCURRENT_ASKS)
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=settings.ASK_QUEUE_TIMEOUT_S)
    except asyncio.TimeoutError:
        metrics_registry.record_queue_wait()
        raise ServiceUnavailable(
            message="Server is busy handling maximum concurrent queries. Please retry.",
            retry_after_s=3,
        )

    # Prepare session options
    session_opts: Dict[str, Any] = {
        "as_of": str(body.options.as_of) if body.options.as_of else None,
        "interactive": body.options.interactive,
        "include_superseded": body.options.include_superseded,
        "doc_types": body.options.doc_types,
        "mode": state.mode.value,
    }
    history_dicts = [h.model_dump() for h in body.history]

    # Non-streaming JSON mode
    if (
        accept
        and "application/json" in accept.lower()
        and "text/event-stream" not in accept.lower()
    ):
        t0 = time.perf_counter()
        tracer = LocalJsonlTracer(
            req_id, mode=state.mode.value, redact=settings.TRACE_REDACT_QUESTIONS
        )
        try:
            with tracer.span("ask_run", {"question": body.question, "opts": session_opts}):
                ans: RagAnswer = await asyncio.wait_for(
                    asyncio.to_thread(
                        state.agent_runner.run,
                        body.question,
                        history=history_dicts,
                        session_opts=session_opts,
                    ),
                    timeout=settings.REQUEST_TIMEOUT_S,
                )
        except asyncio.TimeoutError:
            semaphore.release()
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={
                    "error": "request_timeout",
                    "message": f"Execution exceeded maximum timeout of {settings.REQUEST_TIMEOUT_S}s",
                    "request_id": req_id,
                },
                headers={"X-Request-ID": req_id},
            )
        except Exception as e:
            semaphore.release()
            logger.exception(f"Execution error on /ask: {e}")
            raise
        else:
            semaphore.release()

        # Update metrics & budget
        latency = time.perf_counter() - t0
        metrics_registry.record_ask_latency(latency)
        metrics_registry.record_request("/ask", 200, state.mode.value)
        if hasattr(ans, "llm_calls"):
            metrics_registry.record_llm_usage(ans.llm_calls, ans.usage.get("total", 0))
            if budget_guard:
                budget_guard.record_llm_calls(ans.llm_calls)

        tracer.flush()

        # Sanitize non-streaming output
        clean_ans = sanitize_text(ans.answer)
        clean_cits = sanitize_citations(ans.citations)

        resp_dict = ans.to_dict()
        resp_dict["answer"] = clean_ans
        resp_dict["citations"] = clean_cits
        resp_dict["request_id"] = req_id

        return JSONResponse(
            content=resp_dict,
            headers={
                "Cache-Control": "no-store",
                "X-Request-ID": req_id,
            },
        )

    # Default: SSE Streaming Response
    async def sse_stream() -> AsyncIterator[str]:
        t0 = time.perf_counter()
        seq = 1
        index_ver = (
            state.index_store.manifest.get("version", "unknown") if state.index_store else "unknown"
        )
        tracer = LocalJsonlTracer(
            req_id, mode=state.mode.value, redact=settings.TRACE_REDACT_QUESTIONS
        )

        # Emit initial 'meta' event
        yield format_sse_event(
            "meta",
            {"request_id": req_id, "mode": state.mode.value, "index_version": index_ver},
            event_id=seq,
        )
        seq += 1

        event_queue: asyncio.Queue[Optional[AgentEvent]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def stream_worker() -> None:
            try:
                for ev in state.agent_runner.stream(
                    body.question,
                    history=history_dicts,
                    session_opts=session_opts,
                ):
                    loop.call_soon_threadsafe(event_queue.put_nowait, ev)
            except Exception as exc:
                err_ev = AgentEvent(
                    seq=999,
                    ts=time.time(),
                    step="error",
                    type="error",
                    data={"message": str(exc)},
                )
                loop.call_soon_threadsafe(event_queue.put_nowait, err_ev)
            finally:
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

        loop.run_in_executor(None, stream_worker)

        first_token_seen = False
        grounding_seen = False

        try:
            while True:
                # Check client cancellation
                if await request.is_disconnected():
                    logger.info(f"Client disconnected during stream [request_id={req_id}]")
                    metrics_registry.record_cancelled()
                    break

                try:
                    ev = await asyncio.wait_for(event_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Emit SSE keepalive heartbeat
                    yield format_sse_comment("ping")
                    continue

                if ev is None:
                    break

                ev_type = ev.type
                ev_data = ev.data

                # Enforce order contract: token cannot precede grounding
                if ev_type == "grounding":
                    grounding_seen = True
                elif ev_type == "token":
                    if not grounding_seen:
                        continue
                    if not first_token_seen:
                        first_token_seen = True
                        ttft = time.perf_counter() - t0
                        metrics_registry.record_ttft(ttft)

                # Record metrics
                if ev_type == "refusal":
                    metrics_registry.record_refusal()
                elif ev_type == "clarification":
                    metrics_registry.record_clarification()

                # Format and emit frame
                yield format_sse_event(ev_type, ev_data, event_id=seq)
                seq += 1

                if ev_type in ("final", "refusal", "clarification", "error"):
                    break

        except asyncio.CancelledError:
            metrics_registry.record_cancelled()
        finally:
            semaphore.release()
            total_lat = time.perf_counter() - t0
            metrics_registry.record_ask_latency(total_lat)
            metrics_registry.record_request("/ask", 200, state.mode.value)
            tracer.flush()

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "X-Request-ID": req_id,
        },
    )
