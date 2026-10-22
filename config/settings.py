"""Runtime settings and environment configuration for RegulatorIQ."""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global project settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Crawler & Ingest
    CRAWLER_CONTACT: str = Field(
        default="https://github.com/TAKSSHINAMOORTHY/RegulatorIQ",
        description="Public contact or repo URL sent in User-Agent header",
    )
    REQUEST_DELAY_SECONDS: float = Field(
        default=2.5,
        ge=0.1,
        description="Polite delay between requests to *.rbi.org.in",
    )
    MAX_CONCURRENCY: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Hard cap on concurrent requests to avoid stressing official servers",
    )
    TIMEOUT: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP request timeout in seconds",
    )
    MAX_DOCS: Optional[int] = Field(
        default=None,
        description="Optional limit on number of documents to acquire",
    )
    DRY_RUN: bool = Field(
        default=False,
        description="When true, discovery runs without downloading file payloads",
    )

    # Embedding and Models (defaults for Phase 3+)
    EMBED_MODEL_NAME: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Embedding model name",
    )
    INDEX_MAX_BYTES: int = Field(
        default=1024 * 1024 * 1024,  # 1 GB
        description="Max byte size for local index artifact",
    )
    VECTOR_BACKEND: str = Field(
        default="faiss",
        description="Vector backend: faiss | qdrant | numpy",
    )
    VECTOR_QUANT: str = Field(
        default="fp16",
        description="Vector quantisation: none | fp16 | int8",
    )
    BM25_K1: float = Field(
        default=1.2,
        description="BM25 k1 term frequency saturation parameter",
    )
    BM25_B: float = Field(
        default=0.75,
        description="BM25 b length penalty parameter",
    )
    HF_TOKEN: Optional[str] = Field(
        default=None,
        description="Hugging Face API token for publishing",
    )
    GITHUB_TOKEN: Optional[str] = Field(
        default=None,
        description="GitHub token for publishing releases",
    )

    # LLM & Generation (defaults for Phase 4+)
    LLM_PROVIDER: str = Field(
        default="auto",
        description="LLM provider: auto | gemini | groq | openai_compat | extractive | fake",
    )
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API Key")
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq Cloud API Key")
    LLM_API_KEY: Optional[str] = Field(default=None, description="OpenAI/Compatible API Key")
    LLM_BASE_URL: Optional[str] = Field(
        default=None, description="Base URL for OpenAI-compatible endpoint"
    )
    LLM_MODEL: Optional[str] = Field(default=None, description="Explicit LLM model name")
    LLM_MAX_CALLS: int = Field(default=150, description="Per-run maximum LLM call budget")
    LLM_MAX_TOKENS: int = Field(default=150000, description="Per-run maximum token budget")
    LLM_DAILY_CALL_CAP: int = Field(default=500, description="Daily safety call cap")

    # Logging and Tracing
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    TRACE_REDACT_QUESTIONS: bool = Field(default=True, description="Redact PII in traces")


settings = Settings()
