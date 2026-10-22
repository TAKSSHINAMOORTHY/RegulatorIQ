"""Health Liveness Route for RegulatorIQ API.

GET /health provides an ultra-cheap (< 5ms) liveness probe for orchestrators
without touching models, embeddings, or the index store.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_current_state
from api.schemas import HealthResponse
from api.state import AppState

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
def get_health(state: AppState = Depends(get_current_state)) -> HealthResponse:
    """Return service liveness status and uptime."""
    return HealthResponse(
        status="ok",
        uptime_s=state.uptime_seconds,
    )
