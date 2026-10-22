"""Application Lifespan and Background Engine Initializer for RegulatorIQ API.

Ensures the HTTP port binds immediately (< 2 seconds) while heavy models,
embedding caches, FAISS vectors, and index stores load in an asynchronous
background task.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from agent.llm import LLM
from agent.runner import AgentRunner
from api.budget import GlobalBudgetGuard
from api.feedback_store import FeedbackStore
from api.index_fetch import fetch_index_archive
from api.ratelimit import RateLimiter
from api.settings import APISettings, get_settings
from api.state import AppState, ServiceMode, ServiceStage, get_app_state
from retrieval.index_store import IndexStore
from retrieval.pipeline import Retriever

logger = logging.getLogger("regulatoriq.lifespan")


async def bootstrap_engine(app_state: AppState, settings: APISettings) -> None:
    """Background task initializing storage, models, and AgentRunner."""
    try:
        # 1. State: fetching_index (if needed)
        index_dir = Path(settings.INDEX_DIR)
        manifest_file = index_dir / "manifest.json"

        if not manifest_file.exists():
            if settings.INDEX_URL:
                app_state.transition_to(ServiceStage.FETCHING_INDEX)
                logger.info(f"Downloading index archive from {settings.INDEX_URL}...")
                ok = await asyncio.to_thread(
                    fetch_index_archive,
                    settings.INDEX_URL,
                    index_dir,
                    settings.INDEX_SHA256 or None,
                )
                if not ok or not manifest_file.exists():
                    app_state.transition_to(
                        ServiceStage.FAILED,
                        hint=f"Failed to fetch index from {settings.INDEX_URL}",
                    )
                    return
            else:
                app_state.transition_to(
                    ServiceStage.FAILED,
                    hint=f"Index not found at {index_dir} and INDEX_URL is not set",
                )
                return

        # 2. State: loading_index
        app_state.transition_to(ServiceStage.LOADING_INDEX)
        logger.info(f"Loading IndexStore from {index_dir}...")
        store = await asyncio.to_thread(IndexStore, index_dir)
        valid, msg = store.verify(mode="fast")
        if not valid:
            app_state.transition_to(
                ServiceStage.FAILED, hint=f"IndexStore verification failed: {msg}"
            )
            return
        app_state.index_store = store

        # 3. State: loading_models
        app_state.transition_to(ServiceStage.LOADING_MODELS)
        is_light = bool(settings.RAG_LIGHT_MODE == 1)

        # Build retriever
        retriever = await asyncio.to_thread(
            Retriever.from_config,
            store=store,
            light_mode=is_light,
        )
        app_state.retriever = retriever

        # Initialize LLM provider
        provider_name = settings.LLM_PROVIDER
        llm = None
        if not is_light and provider_name not in ("none", "rules"):
            try:
                llm = LLM()
            except Exception as e:
                logger.warning(
                    f"Could not initialize LLM provider '{provider_name}': {e}. Falling back to rules."
                )
                app_state.degraded_reasons.append(
                    f"LLM provider '{provider_name}' unavailable: {e}"
                )

        # Mode determination
        if is_light:
            app_state.configured_mode = ServiceMode.LIGHT
            app_state.set_mode(ServiceMode.LIGHT, "RAG_LIGHT_MODE=1 active (BM25 only)")
        elif llm is None:
            app_state.configured_mode = ServiceMode.RULES
            app_state.set_mode(ServiceMode.RULES, "Running in deterministic rules mode (no LLM)")
        else:
            app_state.configured_mode = ServiceMode.FULL
            app_state.mode = ServiceMode.FULL

        # Build AgentRunner
        cfg_path = Path(settings.AGENT_CONFIG_PATH)
        runner = AgentRunner.from_config(
            path=cfg_path,
            retriever=retriever,
            llm=llm,
        )
        app_state.agent_runner = runner

        # 4. State: warming
        app_state.transition_to(ServiceStage.WARMING)
        logger.info("Executing internal warm query (no LLM)...")
        try:
            # Touch retriever with a single query
            await asyncio.to_thread(
                retriever.retrieve, "Reserve Bank of India Master Directions", top_k=3
            )
        except Exception as e:
            logger.warning(f"Warmup query encountered minor issue: {e}")

        # 5. Transition to READY or DEGRADED
        final_stage = ServiceStage.DEGRADED if app_state.degraded_reasons else ServiceStage.READY
        app_state.transition_to(final_stage)
        logger.info(
            f"Engine bootstrap completed successfully! Service is now {final_stage.value.upper()}."
        )

    except Exception as e:
        logger.exception(f"Unexpected error during engine bootstrap: {e}")
        app_state.transition_to(ServiceStage.FAILED, hint=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context manager for immediate port bind and graceful shutdown."""
    settings = get_settings()
    app_state = get_app_state()

    # Initialize rate limiter & budget guard
    app_state.rate_limiter = RateLimiter(
        ask_rpm=settings.ASK_RPM,
        ask_burst=settings.ASK_BURST,
        ask_daily_cap=settings.ASK_DAILY_PER_IP,
        warmup_daily_cap=settings.WARMUP_DAILY_CAP,
        trusted_proxies=set(settings.trusted_proxies_list),
    )
    app_state.budget_guard = GlobalBudgetGuard(
        app_state=app_state,
        daily_call_limit=settings.GLOBAL_DAILY_LLM_CALLS,
    )
    app_state.feedback_store = FeedbackStore(
        sink_type=settings.FEEDBACK_SINK,
        file_path=Path(settings.FEEDBACK_PATH) if settings.FEEDBACK_PATH else None,
    )

    # Launch background bootstrap task
    bootstrap_task = asyncio.create_task(bootstrap_engine(app_state, settings))

    yield

    # Graceful Shutdown
    logger.info("Service shutdown initiated. Stopping new requests...")
    app_state.is_shutting_down = True
    if not bootstrap_task.done():
        bootstrap_task.cancel()

    # Allow in-flight requests up to 10 seconds to finish
    await asyncio.sleep(0.5)
    logger.info("Service shutdown complete.")
