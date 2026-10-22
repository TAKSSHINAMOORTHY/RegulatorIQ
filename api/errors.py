"""Error Handling and Standard Error Responses for RegulatorIQ API.

Ensures that error payloads never leak internals, stack traces, paths, or secrets,
and always follow the schema:
    {"error": "<code_string>", "message": "<safe_description>", "request_id": "<uuid>"}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("regulatoriq.errors")


class APIError(Exception):
    """Base application exception."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}
        super().__init__(message)


class RateLimitExceeded(APIError):
    """Raised when client exceeds token bucket rate limit."""

    def __init__(self, retry_after_s: int):
        super().__init__(
            code="rate_limited",
            message=f"Rate limit exceeded. Please retry after {retry_after_s} seconds.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after_s)},
        )
        self.retry_after_s = retry_after_s


class PayloadTooLarge(APIError):
    """Raised when request body exceeds MAX_BODY_BYTES."""

    def __init__(self, max_bytes: int):
        super().__init__(
            code="payload_too_large",
            message=f"Request body exceeds the maximum permitted size of {max_bytes} bytes.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class ServiceUnavailable(APIError):
    """Raised when engine is busy, warming up, or degraded."""

    def __init__(self, message: str, retry_after_s: int = 5):
        super().__init__(
            code="service_unavailable",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(retry_after_s)},
        )


def make_error_response(
    status_code: int,
    error: str,
    message: str,
    request_id: str,
    headers: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Format safe uniform JSON error response."""
    content = {
        "error": error,
        "message": message,
        "request_id": request_id,
    }
    if extra:
        content.update(extra)
    resp_headers = {"X-Request-ID": request_id}
    if headers:
        resp_headers.update(headers)
    return JSONResponse(status_code=status_code, content=content, headers=resp_headers)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle custom application APIError exceptions."""
    req_id = getattr(request.state, "request_id", "unknown")
    extra = {}
    if isinstance(exc, RateLimitExceeded):
        extra["retry_after_s"] = exc.retry_after_s
    return make_error_response(
        status_code=exc.status_code,
        error=exc.code,
        message=exc.message,
        request_id=req_id,
        headers=exc.headers,
        extra=extra,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard Starlette/FastAPI HTTPExceptions."""
    req_id = getattr(request.state, "request_id", "unknown")
    code = "error"
    if exc.status_code == 404:
        code = "not_found"
    elif exc.status_code == 401:
        code = "unauthorized"
    elif exc.status_code == 403:
        code = "forbidden"
    elif exc.status_code == 405:
        code = "method_not_allowed"
    elif exc.status_code == 429:
        code = "rate_limited"
    elif exc.status_code == 503:
        code = "service_unavailable"

    msg = str(exc.detail) if isinstance(exc.detail, str) else "An HTTP error occurred."
    return make_error_response(
        status_code=exc.status_code,
        error=code,
        message=msg,
        request_id=req_id,
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors without echoing user input."""
    req_id = getattr(request.state, "request_id", "unknown")
    errors_summary = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        errors_summary.append(f"{loc}: {msg}" if loc else msg)
    summary_text = "; ".join(errors_summary) if errors_summary else "Request payload validation failed."
    return make_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error="validation_error",
        message=summary_text,
        request_id=req_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all 500 handler that logs details server-side and hides them from client."""
    req_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"Unhandled exception [request_id={req_id}]: {exc}")
    return make_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="internal_error",
        message="An unexpected server error occurred. Please try again later.",
        request_id=req_id,
    )
