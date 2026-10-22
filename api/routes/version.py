"""Version Route for RegulatorIQ API.

GET /version returns package release version, Git commit SHA, and active index version.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_current_settings, get_current_state
from api.schemas import VersionResponse
from api.settings import APISettings
from api.state import AppState

router = APIRouter(tags=["Metadata"])


@router.get("/version", response_model=VersionResponse)
def get_version(
    state: AppState = Depends(get_current_state),
    settings: APISettings = Depends(get_current_settings),
) -> VersionResponse:
    """Return version and commit identification."""
    index_ver = "none"
    if state.index_store and hasattr(state.index_store, "manifest"):
        index_ver = state.index_store.manifest.get("version", "unknown")

    return VersionResponse(
        version="0.1.0",
        git_sha=settings.GIT_SHA,
        index_version=index_ver,
        mode=state.mode.value,
        build_time=state.started_at_utc,
    )
