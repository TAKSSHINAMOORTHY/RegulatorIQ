"""Metadata Route for RegulatorIQ API.

GET /meta returns public service metadata, corpus statistics, feature capabilities,
and statutory regulatory disclaimers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api.deps import get_current_settings, get_current_state
from api.schemas import MetaCorpus, MetaLimits, MetaResponse
from api.settings import APISettings
from api.state import AppState

router = APIRouter(tags=["Metadata"])

OFFICIAL_DISCLAIMER = (
    "Unofficial tool, not affiliated with the Reserve Bank of India. "
    "Not legal or financial advice. Verify answers at the cited rbi.org.in source."
)


@router.get("/meta", response_model=MetaResponse)
def get_metadata(
    response: Response,
    state: AppState = Depends(get_current_state),
    settings: APISettings = Depends(get_current_settings),
) -> MetaResponse:
    """Return public engine metadata and corpus statistics with 60s cache header."""
    response.headers["Cache-Control"] = "public, max-age=60"

    corpus_data = state.get_corpus_stats()
    index_ver = "none"
    if state.index_store and hasattr(state.index_store, "manifest"):
        index_ver = state.index_store.manifest.get("version", "unknown")

    return MetaResponse(
        app="RegulatorIQ",
        version="0.1.0",
        mode=state.mode.value,
        index_version=index_ver,
        corpus=MetaCorpus(
            documents=corpus_data.get("documents", 0),
            chunks=corpus_data.get("chunks", 0),
            as_of_crawl_date=corpus_data.get("as_of_crawl_date", "2026-10-22"),
            doc_types=corpus_data.get("doc_types", {}),
        ),
        capabilities=["stream", "as_of", "include_superseded", "feedback"],
        limits=MetaLimits(
            max_question_chars=settings.MAX_QUESTION_CHARS,
            max_history_turns=settings.MAX_HISTORY_TURNS,
        ),
        disclaimer_key="regulatory_disclaimer",
        disclaimer=OFFICIAL_DISCLAIMER,
        degraded_notice=state.degraded_notice,
    )
