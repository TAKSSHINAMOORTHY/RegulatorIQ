"""Application Settings for RegulatorIQ FastAPI Service.

Uses pydantic-settings to load and validate environment variables with strict typing
and explicit production safeguards.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.paths import (
    AGENT_CONFIG,
    INDEX_DIR,
)
from config.paths import (
    FEEDBACK_PATH as DEFAULT_FEEDBACK_PATH,
)


class APISettings(BaseSettings):
    """Central configuration for the production FastAPI service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment & Network
    ENV: str = Field(default="prod", description="Execution environment: prod, dev, or test")
    HOST: str = Field(default="0.0.0.0", description="Bind host")
    PORT: int = Field(default=8000, description="Bind port")
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # Documentation & Access
    DOCS_ENABLED: int = Field(
        default=0, description="Enable /docs, /redoc and /openapi.json (0 or 1)"
    )
    ALLOW_DOCS_IN_PROD: int = Field(
        default=0, description="Explicit override to allow docs in prod"
    )
    CORS_ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated allow-list of CORS origins",
    )
    WARMUP_TOKEN: str = Field(default="", description="Bearer token for /warmup")
    METRICS_TOKEN: str = Field(default="", description="Bearer token for /metrics")
    API_KEYS: str = Field(default="", description="Optional comma-separated API keys for /ask")

    # Engine & Models
    INDEX_DIR: str = Field(default=str(INDEX_DIR), description="Path to IndexStore directory")
    INDEX_URL: str = Field(default="", description="Remote archive URL to fetch index if missing")
    INDEX_SHA256: str = Field(
        default="", description="Expected SHA256 checksum of remote index archive"
    )
    VECTOR_BACKEND: str = Field(default="faiss", description="Dense index backend (faiss or numpy)")
    RAG_LIGHT_MODE: int = Field(
        default=0, description="1 to force BM25-only light mode without reranker"
    )
    LLM_PROVIDER: str = Field(
        default="auto", description="LLM provider: auto, gemini, groq, openai, extractive, rules"
    )
    GEMINI_API_KEY: str = Field(default="", description="API key for Gemini provider")
    GROQ_API_KEY: str = Field(default="", description="API key for Groq provider")
    OPENAI_API_KEY: str = Field(default="", description="API key for OpenAI provider")
    LLM_BASE_URL: str = Field(
        default="", description="Custom base URL for OpenAI-compatible endpoints"
    )
    AGENT_CONFIG_PATH: str = Field(
        default=str(AGENT_CONFIG), description="Path to agent configuration YAML"
    )

    # Request Caps & Quotas
    MAX_BODY_BYTES: int = Field(
        default=16384, description="Max allowed request payload size in bytes"
    )
    MAX_QUESTION_CHARS: int = Field(default=1000, description="Max question length in characters")
    MAX_HISTORY_TURNS: int = Field(default=4, description="Max conversation history turns")
    MAX_CONCURRENT_ASKS: int = Field(
        default=2, description="Max concurrent in-flight /ask executions"
    )
    ASK_QUEUE_TIMEOUT_S: float = Field(
        default=5.0, description="Timeout waiting for concurrency slot"
    )
    REQUEST_TIMEOUT_S: float = Field(
        default=45.0, description="Max execution time for /ask request"
    )

    # Rate Limiting & Budgets
    ASK_RPM: int = Field(default=12, description="Requests per minute per IP on /ask")
    ASK_BURST: int = Field(default=4, description="Token bucket burst capacity on /ask")
    ASK_DAILY_PER_IP: int = Field(default=150, description="Daily ask request cap per IP")
    GLOBAL_DAILY_LLM_CALLS: int = Field(
        default=800, description="Daily system-wide LLM call ceiling"
    )
    WARMUP_DAILY_CAP: int = Field(default=24, description="Daily warmup request cap")
    TRUSTED_PROXIES: str = Field(
        default="", description="Comma-separated list of trusted proxy IPs"
    )

    # Observability & Tracing
    TRACE_SAMPLE_RATE: float = Field(default=1.0, description="Trace sample rate (0.0 to 1.0)")
    TRACE_REDACT_QUESTIONS: bool = Field(
        default=True, description="Redact raw query text in exported traces"
    )
    LANGFUSE_PUBLIC_KEY: str = Field(default="", description="Langfuse public key")
    LANGFUSE_SECRET_KEY: str = Field(default="", description="Langfuse secret key")
    LANGFUSE_HOST: str = Field(
        default="https://cloud.langfuse.com", description="Langfuse server host"
    )

    # Feedback & Runtime
    FEEDBACK_SINK: str = Field(default="jsonl", description="Feedback sink: jsonl, sqlite, or none")
    FEEDBACK_PATH: str = Field(
        default=str(DEFAULT_FEEDBACK_PATH), description="Path to feedback storage file"
    )
    THREADS: int = Field(
        default_factory=lambda: max(1, os.cpu_count() or 4), description="Worker threads"
    )
    GIT_SHA: str = Field(default="unknown", description="Build git commit SHA")

    @field_validator("ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in {"prod", "dev", "test", "development", "production"}:
            raise ValueError(f"ENV must be one of: prod, dev, test (got '{v}')")
        return (
            "prod" if v_clean == "production" else ("dev" if v_clean == "development" else v_clean)
        )

    @field_validator("FEEDBACK_SINK")
    @classmethod
    def validate_feedback_sink(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in {"jsonl", "sqlite", "none"}:
            raise ValueError(f"FEEDBACK_SINK must be one of: jsonl, sqlite, none (got '{v}')")
        return v_clean

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated origins into a clean list."""
        if not self.CORS_ALLOWED_ORIGINS:
            return []
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_proxies_list(self) -> List[str]:
        """Parse trusted proxies into a list."""
        if not self.TRUSTED_PROXIES:
            return []
        return [p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip()]

    @property
    def api_keys_list(self) -> List[str]:
        """Parse API keys into a list."""
        if not self.API_KEYS:
            return []
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    @model_validator(mode="after")
    def validate_production_safeguards(self) -> APISettings:
        """Enforce strict production configuration rules."""
        if self.ENV == "prod":
            origins = self.cors_origins_list
            if "*" in origins:
                print(
                    "❌ Configuration Error: CORS_ALLOWED_ORIGINS cannot contain '*' in prod mode.",
                    file=sys.stderr,
                )
                raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*' in prod mode")
            if self.DOCS_ENABLED == 1 and self.ALLOW_DOCS_IN_PROD != 1:
                print(
                    "❌ Configuration Error: DOCS_ENABLED=1 is forbidden in prod without ALLOW_DOCS_IN_PROD=1.",
                    file=sys.stderr,
                )
                raise ValueError("DOCS_ENABLED=1 requires ALLOW_DOCS_IN_PROD=1 in prod mode")
        return self


_settings_instance: Optional[APISettings] = None


def get_settings() -> APISettings:
    """Load settings singleton instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = APISettings()
    return _settings_instance


def set_settings(s: APISettings) -> None:
    """Explicitly override global settings (useful for tests and custom factories)."""
    global _settings_instance
    _settings_instance = s
