"""Token-Bucket Rate Limiter with Daily Caps and LRU Memory Bounds.

Protects RegulatorIQ endpoints against abusive traffic, denial of service,
and quota exhaustion. Keyed by client IP derived safely through trusted proxies.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Set, Tuple

from starlette.requests import Request

logger = logging.getLogger("regulatoriq.ratelimit")


class TokenBucket:
    """Token bucket for bursty rate limiting."""

    def __init__(self, rate_per_second: float, capacity: float, time_fn: Callable[[], float]):
        self.rate = rate_per_second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time_fn()
        self.time_fn = time_fn

    def consume(self, amount: float = 1.0) -> Tuple[bool, int]:
        """Try to consume tokens. Returns (allowed, retry_after_seconds)."""
        now = self.time_fn()
        elapsed = max(0.0, now - self.last_update)
        self.last_update = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0
        else:
            missing = amount - self.tokens
            retry_after = int(missing / self.rate) + 1
            return False, retry_after


class DailyTracker:
    """Tracks daily usage per IP resetting on UTC midnight."""

    def __init__(self, max_per_day: int, time_fn: Callable[[], float]):
        self.max_per_day = max_per_day
        self.time_fn = time_fn
        self.count = 0
        self.day_key = self._get_day_key()

    def _get_day_key(self) -> str:
        dt = datetime.fromtimestamp(self.time_fn(), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")

    def increment(self) -> Tuple[bool, int]:
        """Increment count if below cap. Returns (allowed, retry_after_seconds)."""
        curr_day = self._get_day_key()
        if curr_day != self.day_key:
            self.day_key = curr_day
            self.count = 0

        if self.count >= self.max_per_day:
            # Seconds until next midnight UTC
            dt = datetime.fromtimestamp(self.time_fn(), tz=timezone.utc)
            seconds_in_day = dt.hour * 3600 + dt.minute * 60 + dt.second
            retry_after = 86400 - seconds_in_day
            return False, max(1, retry_after)

        self.count += 1
        return True, 0


class RateLimiter:
    """Thread-safe, LRU-bounded token bucket rate limiter."""

    def __init__(
        self,
        ask_rpm: int = 12,
        ask_burst: int = 4,
        ask_daily_cap: int = 150,
        feedback_rph: int = 20,
        warmup_daily_cap: int = 24,
        trusted_proxies: Optional[Set[str]] = None,
        max_keys: int = 50000,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.ask_rpm = ask_rpm
        self.ask_burst = ask_burst
        self.ask_daily_cap = ask_daily_cap
        self.feedback_rph = feedback_rph
        self.warmup_daily_cap = warmup_daily_cap
        self.trusted_proxies = trusted_proxies or set()
        self.max_keys = max_keys
        self.time_fn = time_fn or time.time

        self.lock = threading.Lock()
        # LRU caches: IP -> Bucket/Tracker
        self.ask_buckets: collections.OrderedDict[str, TokenBucket] = collections.OrderedDict()
        self.ask_daily: collections.OrderedDict[str, DailyTracker] = collections.OrderedDict()
        self.feedback_buckets: collections.OrderedDict[str, TokenBucket] = collections.OrderedDict()
        self.warmup_daily: collections.OrderedDict[str, DailyTracker] = collections.OrderedDict()

    def get_client_ip(self, request: Request) -> str:
        """Safely extract client IP respecting trusted proxy chain."""
        client_host = request.client.host if request.client else "127.0.0.1"

        # Only trust X-Forwarded-For if client_host is in trusted_proxies
        if client_host in self.trusted_proxies:
            xff = request.headers.get("X-Forwarded-For")
            if xff:
                # Find first untrusted IP from right to left
                ips = [ip.strip() for ip in xff.split(",")]
                for ip in reversed(ips):
                    if ip not in self.trusted_proxies:
                        return ip
                return ips[0]

        return client_host

    def _evict_lru(self, d: collections.OrderedDict) -> None:
        """Keep dictionary size bounded below max_keys."""
        while len(d) >= self.max_keys:
            d.popitem(last=False)

    def check_ask_rate_limit(self, client_ip: str) -> Tuple[bool, int]:
        """Check rate limit for /ask. Returns (allowed, retry_after_seconds)."""
        with self.lock:
            # 1. Daily cap check
            if client_ip not in self.ask_daily:
                self._evict_lru(self.ask_daily)
                self.ask_daily[client_ip] = DailyTracker(self.ask_daily_cap, self.time_fn)
            else:
                self.ask_daily.move_to_end(client_ip)

            daily_ok, daily_retry = self.ask_daily[client_ip].increment()
            if not daily_ok:
                return False, daily_retry

            # 2. Token bucket burst check
            if client_ip not in self.ask_buckets:
                self._evict_lru(self.ask_buckets)
                rate_sec = max(0.01, self.ask_rpm / 60.0)
                self.ask_buckets[client_ip] = TokenBucket(rate_sec, float(self.ask_burst), self.time_fn)
            else:
                self.ask_buckets.move_to_end(client_ip)

            allowed, retry_after = self.ask_buckets[client_ip].consume(1.0)
            if not allowed:
                # Rollback daily count if bucket blocked it
                self.ask_daily[client_ip].count -= 1
            return allowed, retry_after

    def check_feedback_rate_limit(self, client_ip: str) -> Tuple[bool, int]:
        """Check rate limit for /feedback (20/hour)."""
        with self.lock:
            if client_ip not in self.feedback_buckets:
                self._evict_lru(self.feedback_buckets)
                rate_sec = max(0.001, self.feedback_rph / 3600.0)
                self.feedback_buckets[client_ip] = TokenBucket(rate_sec, 5.0, self.time_fn)
            else:
                self.feedback_buckets.move_to_end(client_ip)

            return self.feedback_buckets[client_ip].consume(1.0)

    def check_warmup_rate_limit(self, client_ip: str) -> Tuple[bool, int]:
        """Check rate limit for /warmup (24/day)."""
        with self.lock:
            if client_ip not in self.warmup_daily:
                self._evict_lru(self.warmup_daily)
                self.warmup_daily[client_ip] = DailyTracker(self.warmup_daily_cap, self.time_fn)
            else:
                self.warmup_daily.move_to_end(client_ip)

            return self.warmup_daily[client_ip].increment()
