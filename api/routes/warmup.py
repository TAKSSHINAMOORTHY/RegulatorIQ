"""Warmup Route for RegulatorIQ Service.

POST /warmup performs an authenticated dry-run that primes dense embedding models,
BM25 inverted indices, FAISS buffers, and cross-encoder rerankers WITHOUT invoking
any external LLM API calls.
"""

from __future__ import annotations

import time
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import (
    get_current_rate_limiter,
    get_current_state,
    get_request_client_ip,
    verify_warmup_token,
)
from api.observability import metrics_registry
from api.ratelimit import RateLimiter
from api.schemas import WarmupResponse
from api.state import AppState, ServiceMode

router = APIRouter(tags=["Operations"])


@router.post("/warmup", response_model=WarmupResponse, dependencies=[Depends(verify_warmup_token)])
def execute_warmup(
    client_ip: str = Depends(get_request_client_ip),
    state: AppState = Depends(get_current_state),
    limiter: RateLimiter = Depends(get_current_rate_limiter),
) -> WarmupResponse:
    """Pre-warm retrieval and reranking models without consuming LLM budget."""
    if not state.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot warm up: service is not ready yet.",
        )

    # Check separate warmup daily cap
    if limiter:
        allowed, retry_after = limiter.check_warmup_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Warmup daily limit reached. Retry after {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    timings: Dict[str, float] = {}
    fixed_query = "Reserve Bank of India Master Direction framework"

    retriever = state.retriever
    if retriever:
        # 1. Warm dense embedding
        t0 = time.perf_counter()
        if hasattr(retriever, "embedder") and retriever.embedder:
            try:
                retriever.embedder.embed_queries([fixed_query])
            except Exception:
                pass
        timings["embed_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # 2. Warm BM25 & Dense retrieval
        t0 = time.perf_counter()
        retrieved_chunks = []
        try:
            retrieved_chunks = retriever.retrieve(fixed_query, top_k=8)
        except Exception:
            pass
        timings["retrieve_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        # 3. Warm cross-encoder reranker if not in light mode
        t0 = time.perf_counter()
        if (
            state.mode != ServiceMode.LIGHT
            and hasattr(retriever, "reranker")
            and retriever.reranker
        ):
            try:
                pairs = [(fixed_query, c.get("text", "")) for c in retrieved_chunks[:8]]
                if pairs:
                    retriever.reranker.rerank(pairs)
            except Exception:
                pass
        timings["rerank_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    state.warmup_completed = True
    metrics_registry.record_warmup()

    return WarmupResponse(
        ok=True,
        mode=state.mode.value,
        timings_ms=timings,
        llm_called=False,
    )
