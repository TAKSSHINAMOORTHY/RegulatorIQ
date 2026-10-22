"""Readiness Route for RegulatorIQ API.

GET /ready returns HTTP 200 once background initialization and engine warmup
complete, or HTTP 503 with retry information while the service is bootstrapping.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.deps import get_current_settings, get_current_state
from api.schemas import ReadyResponse
from api.settings import APISettings
from api.state import AppState, ServiceStage

router = APIRouter(tags=["System"])


@router.get("/ready", response_model=ReadyResponse)
def get_ready(
    response: Response,
    state: AppState = Depends(get_current_state),
    settings: APISettings = Depends(get_current_settings),
) -> ReadyResponse:
    """Return service readiness and loaded engine metadata."""
    is_ready = state.is_ready

    index_ver = "none"
    chunk_count = 0
    if state.index_store and hasattr(state.index_store, "manifest"):
        manifest = state.index_store.manifest
        index_ver = manifest.get("version", "unknown")
        chunk_count = manifest.get("counts", {}).get("chunks", 0)

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Retry-After"] = "5"
        return ReadyResponse(
            status=state.current_stage.value,
            mode=state.mode.value,
            index_version=index_ver,
            chunk_count=chunk_count,
            degraded=state.degraded_reasons,
            warmup_enabled=bool(settings.WARMUP_TOKEN),
            version="0.1.0",
            started_at=state.started_at_utc,
            stage=state.current_stage.value,
            elapsed_s=state.stage_elapsed_seconds,
            hint=state.failure_hint or "Service is initializing models and index in background.",
        )

    response.status_code = status.HTTP_200_OK
    return ReadyResponse(
        status="ready" if state.current_stage == ServiceStage.READY else "degraded",
        mode=state.mode.value,
        index_version=index_ver,
        chunk_count=chunk_count,
        degraded=state.degraded_reasons,
        warmup_enabled=bool(settings.WARMUP_TOKEN),
        version="0.1.0",
        started_at=state.started_at_utc,
    )
