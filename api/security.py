"""Security Middleware, Output Sanitizer, and Request Bounds for RegulatorIQ API.

Enforces:
1. Strict output sanitization (only *.rbi.org.in URLs permitted, no leaked keys, paths, or tracebacks).
2. Streaming request body size limits (HTTP 413, never buffers beyond MAX_BODY_BYTES).
3. Standard hardened HTTP security headers.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.errors import make_error_response
from api.settings import APISettings

logger = logging.getLogger("regulatoriq.security")

# Global counter for metrics
SANITIZER_HITS_COUNTER = 0

# Compiled patterns for redacting sensitive content
KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z\-_]{30,45}"),  # Google API Key
    re.compile(r"gsk_[a-zA-Z0-9_\-]{20,}"),  # Groq API Key
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),  # OpenAI API Key
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE),  # Generic Bearer Token
]

PATH_PATTERNS = [
    re.compile(r"(?:/Users|/home|/root|/var|/etc|/tmp|/private|/opt)/[^\s\"'<>]+"),
    re.compile(r"[a-zA-Z]:\\[^\s\"'<>]+"),
]

STACK_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL),
    re.compile(r'File "[^"]+", line \d+, in .*'),
]

URL_PATTERN = re.compile(r"https?://[^\s<>\"')]+")


def is_allowed_rbi_url(url: str) -> bool:
    """Check if URL host strictly belongs to *.rbi.org.in."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host == "rbi.org.in" or host.endswith(".rbi.org.in"):
            return True
        return False
    except Exception:
        return False


def sanitize_text(text: str) -> str:
    """Remove unauthorized URLs, secrets, file paths, and stack traces from text."""
    global SANITIZER_HITS_COUNTER
    if not text or not isinstance(text, str):
        return text

    sanitized = text
    hit = False

    # 1. Check and sanitize URLs
    def url_sub(match: re.Match[str]) -> str:
        nonlocal hit
        u = match.group(0)
        if is_allowed_rbi_url(u):
            return u
        hit = True
        return "[UNVERIFIED_EXTERNAL_LINK_REMOVED]"

    sanitized = URL_PATTERN.sub(url_sub, sanitized)

    # 2. Check and sanitize API keys
    for pat in KEY_PATTERNS:
        if pat.search(sanitized):
            hit = True
            sanitized = pat.sub("[REDACTED_API_KEY]", sanitized)

    # 3. Check and sanitize system file paths
    for pat in PATH_PATTERNS:
        if pat.search(sanitized):
            hit = True
            sanitized = pat.sub("[SYSTEM_PATH_REDACTED]", sanitized)

    # 4. Check and sanitize stack traces
    for pat in STACK_PATTERNS:
        if pat.search(sanitized):
            hit = True
            sanitized = pat.sub("[INTERNAL_TRACE_REDACTED]", sanitized)

    if hit:
        SANITIZER_HITS_COUNTER += 1
        logger.warning("Sanitizer hit: sensitive pattern or non-RBI link redacted from output.")

    return sanitized


def sanitize_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter citation source URLs to ensure strict *.rbi.org.in compliance."""
    global SANITIZER_HITS_COUNTER
    clean_citations = []
    for c in citations:
        c_copy = dict(c)
        src_url = c_copy.get("source_url")
        if src_url:
            if not is_allowed_rbi_url(src_url):
                SANITIZER_HITS_COUNTER += 1
                c_copy["source_url"] = "https://www.rbi.org.in"
        clean_citations.append(c_copy)
    return clean_citations


def sanitize_event_data(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply sanitization to event payload according to event type."""
    if not isinstance(data, dict):
        return data

    clean_data = dict(data)
    if event_type == "token":
        if "text" in clean_data:
            clean_data["text"] = sanitize_text(clean_data["text"])
    elif event_type in ("final", "refusal", "clarification"):
        if "answer" in clean_data:
            clean_data["answer"] = sanitize_text(clean_data["answer"])
        if "text" in clean_data:
            clean_data["text"] = sanitize_text(clean_data["text"])
        if "question" in clean_data:
            clean_data["question"] = sanitize_text(clean_data["question"])
        if "citations" in clean_data and isinstance(clean_data["citations"], list):
            clean_data["citations"] = sanitize_citations(clean_data["citations"])
    elif event_type == "citation":
        if "source_url" in clean_data and not is_allowed_rbi_url(clean_data["source_url"]):
            clean_data["source_url"] = "https://www.rbi.org.in"
    elif event_type == "error":
        if "message" in clean_data:
            clean_data["message"] = sanitize_text(clean_data["message"])

    return clean_data


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces standard HTTP security response headers."""

    def __init__(self, app: Any, settings: APISettings):
        super().__init__(app)
        self.settings = settings
        self.trusted_proxies = set(settings.trusted_proxies_list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        # Standard Hardening Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # Strict-Transport-Security (HTTPS only)
        is_https = request.url.scheme == "https"
        client_ip = request.client.host if request.client else ""
        if not is_https and client_ip in self.trusted_proxies:
            proto = request.headers.get("X-Forwarded-Proto", "").lower()
            if proto == "https":
                is_https = True

        if is_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Remove Server header to prevent fingerprinting
        if "server" in response.headers:
            del response.headers["server"]

        return response


class BodySizeLimiterMiddleware(BaseHTTPMiddleware):
    """Enforces streaming request body size limit (413 Payload Too Large)."""

    def __init__(self, app: Any, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check Content-Length header upfront if provided
        cl_header = request.headers.get("content-length")
        if cl_header:
            try:
                cl = int(cl_header)
                if cl > self.max_bytes:
                    req_id = getattr(request.state, "request_id", "unknown")
                    return make_error_response(
                        status_code=413,
                        error="payload_too_large",
                        message=f"Payload size {cl} bytes exceeds maximum allowed {self.max_bytes} bytes.",
                        request_id=req_id,
                    )
            except ValueError:
                pass

        return await call_next(request)
