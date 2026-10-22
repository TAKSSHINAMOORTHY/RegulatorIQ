"""Global Daily LLM Budget Guard for RegulatorIQ API.

Protects external LLM API quotas by capping daily calls. Transitions system
to deterministic RULES mode upon budget exhaustion instead of failing requests.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from api.state import AppState, ServiceMode

logger = logging.getLogger("regulatoriq.budget")


class GlobalBudgetGuard:
    """System-wide daily LLM usage tracker."""

    def __init__(
        self,
        app_state: AppState,
        daily_call_limit: int = 800,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.app_state = app_state
        self.daily_limit = daily_call_limit
        self.time_fn = time_fn or time.time
        self.lock = threading.Lock()

        self.calls_today = 0
        self.day_key = self._get_day_key()
        self.warned_at_80 = False

    def _get_day_key(self) -> str:
        dt = datetime.fromtimestamp(self.time_fn(), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")

    def _check_and_reset_day(self) -> None:
        curr_day = self._get_day_key()
        if curr_day != self.day_key:
            logger.info(f"New UTC day detected ({curr_day}). Resetting daily LLM call count.")
            self.day_key = curr_day
            self.calls_today = 0
            self.warned_at_80 = False
            # If was degraded due to budget, restore mode
            if any("Daily LLM call budget" in r for r in self.app_state.degraded_reasons):
                self.app_state.degraded_reasons = [
                    r for r in self.app_state.degraded_reasons if "Daily LLM call budget" not in r
                ]
                self.app_state.degraded_notice = (
                    "; ".join(self.app_state.degraded_reasons)
                    if self.app_state.degraded_reasons
                    else None
                )
                if self.app_state.configured_mode == ServiceMode.FULL:
                    self.app_state.mode = ServiceMode.FULL
                    logger.info("Restored FULL operating mode following UTC budget reset")

    @property
    def is_exhausted(self) -> bool:
        """Check whether budget ceiling has been reached."""
        with self.lock:
            self._check_and_reset_day()
            return self.calls_today >= self.daily_limit

    @property
    def percent_used(self) -> float:
        """Percentage of daily budget consumed."""
        with self.lock:
            self._check_and_reset_day()
            if self.daily_limit <= 0:
                return 100.0
            return round((self.calls_today / self.daily_limit) * 100.0, 1)

    def record_llm_calls(self, num_calls: int) -> None:
        """Register consumed LLM calls and trigger threshold transitions."""
        if num_calls <= 0:
            return

        with self.lock:
            self._check_and_reset_day()
            self.calls_today += num_calls
            ratio = self.calls_today / self.daily_limit if self.daily_limit > 0 else 1.0

            # 80% threshold warning
            if ratio >= 0.80 and not self.warned_at_80:
                self.warned_at_80 = True
                notice = f"Global LLM budget at {int(ratio * 100)}% ({self.calls_today}/{self.daily_limit})"
                logger.warning(notice)
                if not self.app_state.degraded_notice:
                    self.app_state.degraded_notice = notice

            # 100% threshold: downgrade to RULES
            if self.calls_today >= self.daily_limit:
                reason = f"Daily LLM call budget exhausted ({self.calls_today}/{self.daily_limit})"
                logger.warning(f"{reason}. Switching to RULES mode.")
                self.app_state.set_mode(ServiceMode.RULES, reason)
