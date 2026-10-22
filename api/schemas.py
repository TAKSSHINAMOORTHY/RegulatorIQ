"""Pydantic Request and Response Schemas for RegulatorIQ API.

Enforces strict field forbidding (`extra="forbid"`), Unicode NFKC normalization,
control character removal, and input length bounds.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def clean_text_input(v: str) -> str:
    """Normalize unicode to NFKC and strip invisible/control characters."""
    if not isinstance(v, str):
        return v
    # Normalize Unicode NFKC
    normalized = unicodedata.normalize("NFKC", v)
    # Strip control characters (allow normal whitespace: \n, \r, \t)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", normalized)
    return cleaned.strip()


class AskOptions(BaseModel):
    """Execution options for regulatory search and generation."""

    model_config = ConfigDict(extra="forbid")

    as_of: Optional[date] = Field(default=None, description="Regulatory point-in-time date constraint (YYYY-MM-DD)")
    doc_types: Optional[List[str]] = Field(default=None, description="Filter documents by category/type")
    include_superseded: bool = Field(default=False, description="Whether to include superseded documents")
    interactive: bool = Field(default=True, description="Allow clarification request vs emit assumption")


class ConversationTurn(BaseModel):
    """Single turn in previous conversation context."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"] = Field(..., description="Speaker role")
    content: str = Field(..., min_length=1, max_length=2000, description="Turn content")

    @field_validator("content")
    @classmethod
    def clean_content(cls, v: str) -> str:
        cleaned = clean_text_input(v)
        if not cleaned:
            raise ValueError("Turn content cannot be empty after sanitization")
        return cleaned


class AskRequest(BaseModel):
    """Input payload for POST /ask."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=1000, description="Regulatory question")
    history: List[ConversationTurn] = Field(default_factory=list, max_length=8, description="Recent conversation turns (max 4 round-trips)")
    options: AskOptions = Field(default_factory=AskOptions, description="Search and generation options")

    @field_validator("question")
    @classmethod
    def clean_question(cls, v: str) -> str:
        cleaned = clean_text_input(v)
        if not cleaned:
            raise ValueError("Question cannot be empty after sanitization")
        return cleaned


class FeedbackRequest(BaseModel):
    """Input payload for POST /feedback."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., description="UUID of the /ask request being rated")
    rating: Literal["up", "down"] = Field(..., description="User rating")
    reason: Optional[Literal["wrong_fact", "outdated", "missing_citation", "unhelpful", "other"]] = Field(
        default=None, description="Category reason for rating"
    )
    comment: Optional[str] = Field(default=None, max_length=500, description="Optional user comment")

    @field_validator("request_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError:
            raise ValueError("request_id must be a valid UUID string")
        return v

    @field_validator("comment")
    @classmethod
    def clean_comment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return clean_text_input(v)


class HealthResponse(BaseModel):
    """Output payload for GET /health."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    uptime_s: float


class ReadyResponse(BaseModel):
    """Output payload for GET /ready."""

    model_config = ConfigDict(extra="forbid")

    status: str
    mode: str
    index_version: str
    chunk_count: int
    degraded: List[str]
    warmup_enabled: bool
    version: str
    started_at: str
    stage: Optional[str] = None
    elapsed_s: Optional[float] = None
    hint: Optional[str] = None


class WarmupResponse(BaseModel):
    """Output payload for POST /warmup."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    mode: str
    timings_ms: Dict[str, float]
    llm_called: bool = False


class MetaCorpus(BaseModel):
    """Corpus summary stats for GET /meta."""

    model_config = ConfigDict(extra="forbid")

    documents: int
    chunks: int
    as_of_crawl_date: str
    doc_types: Dict[str, int]


class MetaLimits(BaseModel):
    """Request quotas and bounds for GET /meta."""

    model_config = ConfigDict(extra="forbid")

    max_question_chars: int
    max_history_turns: int


class MetaResponse(BaseModel):
    """Output payload for GET /meta."""

    model_config = ConfigDict(extra="forbid")

    app: str = "RegulatorIQ"
    version: str
    mode: str
    index_version: str
    corpus: MetaCorpus
    capabilities: List[str]
    limits: MetaLimits
    disclaimer_key: str = "regulatory_disclaimer"
    disclaimer: str
    degraded_notice: Optional[str] = None


class VersionResponse(BaseModel):
    """Output payload for GET /version."""

    model_config = ConfigDict(extra="forbid")

    version: str
    git_sha: str
    index_version: str
    mode: str
    build_time: str
