"""FastAPI Dependency Injection Providers for RegulatorIQ API.

Supplies singleton instances of configuration, application state, rate limiter,
budget guard, feedback store, and request authentication checkers.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from api.budget import GlobalBudgetGuard
from api.errors import APIError
from api.feedback_store import FeedbackStore
from api.ratelimit import RateLimiter
from api.settings import APISettings, get_settings
from api.state import AppState, get_app_state


def get_current_settings(request: Request) -> APISettings:
    """Return active APISettings singleton."""
    if hasattr(request.app.state, "settings") and request.app.state.settings:
        return request.app.state.settings
    return get_settings()


def get_current_state() -> AppState:
    """Return active AppState singleton."""
    return get_app_state()


def get_current_rate_limiter(state: AppState = Depends(get_current_state)) -> RateLimiter:
    """Return active RateLimiter instance from state."""
    return state.rate_limiter


def get_current_budget_guard(state: AppState = Depends(get_current_state)) -> GlobalBudgetGuard:
    """Return active GlobalBudgetGuard instance from state."""
    return state.budget_guard


def get_current_feedback_store(state: AppState = Depends(get_current_state)) -> FeedbackStore:
    """Return active FeedbackStore instance from state."""
    return state.feedback_store


def get_request_client_ip(
    request: Request,
    settings: APISettings = Depends(get_current_settings),
    limiter: RateLimiter = Depends(get_current_rate_limiter),
) -> str:
    """Extract validated client IP address."""
    if limiter:
        return limiter.get_client_ip(request)
    return request.client.host if request.client else "127.0.0.1"


def verify_api_key(
    request: Request,
    settings: APISettings = Depends(get_current_settings),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """Verify X-API-Key header if API_KEYS is configured."""
    valid_keys = settings.api_keys_list
    if not valid_keys:
        return  # Public access permitted when no keys are configured

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header",
        )

    matched = any(hmac.compare_digest(x_api_key, key) for key in valid_keys)
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def verify_warmup_token(
    authorization: Optional[str] = Header(default=None),
    settings: APISettings = Depends(get_current_settings),
) -> None:
    """Verify Bearer token on POST /warmup."""
    if not settings.WARMUP_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="warmup_disabled",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization Bearer header",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    if not hmac.compare_digest(token, settings.WARMUP_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid warmup bearer token",
        )


def verify_metrics_token(
    authorization: Optional[str] = Header(default=None),
    settings: APISettings = Depends(get_current_settings),
) -> None:
    """Verify Bearer token on GET /metrics."""
    if not settings.METRICS_TOKEN:
        # Prompt 7 C9: Return 404 when METRICS_TOKEN unset
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    if not hmac.compare_digest(token, settings.METRICS_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )
