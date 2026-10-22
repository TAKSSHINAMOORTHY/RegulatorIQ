"""Feedback Ingestion Route for RegulatorIQ API.

POST /feedback accepts user ratings and commentary, applies PII redaction,
and persists records to the configured feedback sink.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import (
    get_current_feedback_store,
    get_current_rate_limiter,
    get_request_client_ip,
)
from api.feedback_store import FeedbackStore
from api.observability import hash_ip
from api.ratelimit import RateLimiter
from api.schemas import FeedbackRequest

router = APIRouter(tags=["Feedback"])


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
def submit_feedback(
    body: FeedbackRequest,
    client_ip: str = Depends(get_request_client_ip),
    limiter: RateLimiter = Depends(get_current_rate_limiter),
    store: FeedbackStore = Depends(get_current_feedback_store),
) -> Response:
    """Submit rating and feedback for an /ask request."""
    # Enforce rate limit (20/hour/IP)
    if limiter:
        allowed, retry_after = limiter.check_feedback_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Feedback rate limit exceeded. Retry after {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    client_hash = hash_ip(client_ip)
    if store:
        store.save_feedback(body, client_hash=client_hash)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
