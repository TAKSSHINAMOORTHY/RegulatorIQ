"""RegulatorIQ FastAPI Main Application.

Exposes create_app() factory and module-level `app` instance with production
middleware, lifecycle state management, and strict security guards.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from api.lifespan import lifespan
from api.observability import JsonAccessLoggerMiddleware
from api.routes import ask, feedback, health, meta, metrics, ready, version, warmup
from api.security import BodySizeLimiterMiddleware, SecurityHeadersMiddleware
from api.settings import APISettings, get_settings, set_settings

logger = logging.getLogger("regulatoriq.api")


def create_app(settings: Optional[APISettings] = None) -> FastAPI:
    """Application factory for RegulatorIQ FastAPI service."""
    cfg = settings or get_settings()
    set_settings(cfg)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, cfg.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Documentation toggle
    docs_enabled = bool(cfg.DOCS_ENABLED == 1)
    openapi_url = "/openapi.json" if docs_enabled else None
    docs_url = "/docs" if docs_enabled else None
    redoc_url = "/redoc" if docs_enabled else None

    app = FastAPI(
        title="RegulatorIQ API",
        version="0.1.0",
        description="Production Agentic RAG API over Official Reserve Bank of India (RBI) Regulations",
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    app.state.settings = cfg

    # 1. Custom Exception Handlers (safe error responses)
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 2. CORS Middleware
    allowed_origins = list(cfg.cors_origins_list)
    if cfg.ENV != "prod":
        # Allow localhost on any port for local development and testing
        allowed_origins.extend(["http://localhost", "http://127.0.0.1"])

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins else ["http://localhost:3000"],
        allow_origin_regex=r"^http://localhost(:\d+)?$" if cfg.ENV != "prod" else None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-API-Key",
            "X-Warmup",
            "X-Request-ID",
            "Accept",
        ],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )

    # 3. Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware, settings=cfg)

    # 4. Body Size Limiter Middleware
    app.add_middleware(BodySizeLimiterMiddleware, max_bytes=cfg.MAX_BODY_BYTES)

    # 5. JSON Access Logger Middleware
    app.add_middleware(
        JsonAccessLoggerMiddleware,
        settings=cfg,
        trusted_proxies=cfg.trusted_proxies_list,
    )

    # 6. Mount Routers
    app.include_router(health.router)
    app.include_router(ready.router)
    app.include_router(warmup.router)
    app.include_router(ask.router)
    app.include_router(feedback.router)
    app.include_router(meta.router)
    app.include_router(version.router)
    app.include_router(metrics.router)

    return app


# Module-level instance for uvicorn
app = create_app()
