"""Readiness and Lifecycle State Machine for RegulatorIQ Service.

Manages startup states:
  starting -> fetching_index -> loading_index -> loading_models -> warming -> ready | degraded | failed
Tracks transition durations, active engine references, and operating modes (full, rules, light).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("regulatoriq.state")


class ServiceStage(str, Enum):
    STARTING = "starting"
    FETCHING_INDEX = "fetching_index"
    LOADING_INDEX = "loading_index"
    LOADING_MODELS = "loading_models"
    WARMING = "warming"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


class ServiceMode(str, Enum):
    FULL = "full"
    RULES = "rules"
    LIGHT = "light"


class AppState:
    """Singleton application lifecycle state machine."""

    def __init__(self) -> None:
        self.started_at_utc = datetime.now(timezone.utc).isoformat()
        self.start_perf_time = time.perf_counter()
        self.current_stage: ServiceStage = ServiceStage.STARTING
        self.stage_timestamps: Dict[str, float] = {
            ServiceStage.STARTING.value: self.start_perf_time
        }
        self.stage_durations: Dict[str, float] = {}

        # Mode & Fallback tracking
        self.mode: ServiceMode = ServiceMode.RULES
        self.configured_mode: ServiceMode = ServiceMode.FULL
        self.degraded_reasons: List[str] = []
        self.degraded_notice: Optional[str] = None
        self.failure_hint: Optional[str] = None

        # Engine handles (injected upon successful bootstrap)
        self.index_store: Any = None
        self.retriever: Any = None
        self.agent_runner: Any = None
        self.tracer: Any = None
        self.rate_limiter: Any = None
        self.budget_guard: Any = None
        self.feedback_store: Any = None

        # Metric flags
        self.warmup_completed: bool = False
        self.consecutive_provider_failures: int = 0
        self.is_shutting_down: bool = False

    @property
    def uptime_seconds(self) -> float:
        """Uptime in seconds since process start."""
        return round(time.perf_counter() - self.start_perf_time, 3)

    @property
    def stage_elapsed_seconds(self) -> float:
        """Elapsed seconds in current stage."""
        stage_start = self.stage_timestamps.get(self.current_stage.value, self.start_perf_time)
        return round(time.perf_counter() - stage_start, 3)

    @property
    def is_ready(self) -> bool:
        """Whether the application is ready to serve /ask requests."""
        return (
            self.current_stage in (ServiceStage.READY, ServiceStage.DEGRADED)
            and self.agent_runner is not None
            and not self.is_shutting_down
        )

    def transition_to(self, new_stage: ServiceStage, hint: Optional[str] = None) -> None:
        """Record stage transition with duration tracking."""
        now = time.perf_counter()
        prev_stage = self.current_stage
        prev_start = self.stage_timestamps.get(prev_stage.value, now)
        duration = round(now - prev_start, 3)
        self.stage_durations[prev_stage.value] = duration

        self.current_stage = new_stage
        self.stage_timestamps[new_stage.value] = now
        if hint:
            self.failure_hint = hint
        logger.info(
            f"State transition: {prev_stage.value} -> {new_stage.value} "
            f"(prev duration={duration}s, hint={hint})"
        )

    def set_mode(self, mode: ServiceMode, reason: Optional[str] = None) -> None:
        """Update operational mode and record degraded reason if applicable."""
        old_mode = self.mode
        self.mode = mode
        if reason and reason not in self.degraded_reasons:
            self.degraded_reasons.append(reason)
            self.degraded_notice = "; ".join(self.degraded_reasons)
        logger.info(
            f"Operating mode transition: {old_mode.value} -> {mode.value} (reason={reason})"
        )

    def register_provider_failure(self, error_str: str) -> None:
        """Track consecutive provider failures; downgrade to RULES on threshold."""
        self.consecutive_provider_failures += 1
        if self.consecutive_provider_failures >= 3 and self.mode == ServiceMode.FULL:
            self.set_mode(
                ServiceMode.RULES,
                f"LLM provider failed {self.consecutive_provider_failures} consecutive times ({error_str})",
            )

    def register_provider_success(self) -> None:
        """Reset consecutive failures; re-upgrade if budget allows."""
        self.consecutive_provider_failures = 0
        if self.configured_mode == ServiceMode.FULL and self.mode == ServiceMode.RULES:
            # Check if budget is not exhausted
            if self.budget_guard and not self.budget_guard.is_exhausted:
                self.mode = ServiceMode.FULL
                self.degraded_reasons = [
                    r for r in self.degraded_reasons if "LLM provider failed" not in r
                ]
                self.degraded_notice = (
                    "; ".join(self.degraded_reasons) if self.degraded_reasons else None
                )
                logger.info(
                    "Operating mode restored to FULL following successful provider operation"
                )

    def get_corpus_stats(self) -> Dict[str, Any]:
        """Fetch indexed corpus statistics from active index_store."""
        if not self.index_store or not hasattr(self.index_store, "manifest"):
            return {
                "documents": 0,
                "chunks": 0,
                "as_of_crawl_date": "unknown",
                "doc_types": {},
            }
        manifest = self.index_store.manifest
        counts = manifest.get("counts", {})
        metadata = manifest.get("metadata", {})
        return {
            "documents": counts.get("documents", 0),
            "chunks": counts.get("chunks", 0),
            "as_of_crawl_date": metadata.get("as_of_crawl_date", "2026-10-22"),
            "doc_types": manifest.get("doc_types", {}),
        }


# Global app state singleton
state = AppState()


def get_app_state() -> AppState:
    """Dependency provider for global AppState."""
    return state
