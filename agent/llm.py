"""LLM Adapter Layer with Multi-Provider Support, Budget Guards, and Deterministic Caching.

Supported providers:
1. gemini (GEMINI_API_KEY)
2. groq (GROQ_API_KEY)
3. openai_compat (LLM_BASE_URL + LLM_API_KEY)
4. extractive (no model, deterministic sentence selection)
5. fake (tests only, deterministic seeded output)
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent.types import LLMResult
from config.paths import LLM_CACHE_DIR
from config.settings import settings


def redact_secrets(text: str) -> str:
    """Redact API keys and tokens from strings and error messages."""
    if not text:
        return ""
    # Redact common key patterns
    redacted = re.sub(r"(AIza[0-9A-Za-z\-_]{35})", "[REDACTED_GEMINI_KEY]", text)
    redacted = re.sub(r"(gsk_[0-9A-Za-z]{48,})", "[REDACTED_GROQ_KEY]", redacted)
    redacted = re.sub(r"(sk-[0-9A-Za-z]{20,})", "[REDACTED_API_KEY]", redacted)
    return redacted


def repair_and_parse_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Tolerant JSON parser: strips markdown code fences and fixes trailing commas."""
    if not raw_text:
        return None

    cleaned = raw_text.strip()
    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        pass

    # Fix trailing commas
    try:
        fixed = re.sub(r",\s*([\]}])", r"\1", cleaned)
        data = json.loads(fixed)
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return None


class LLMCache:
    """SQLite-backed deterministic cache for LLM responses."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or (LLM_CACHE_DIR / "llm_cache.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    response_text TEXT,
                    parsed_json TEXT,
                    in_tokens INTEGER,
                    out_tokens INTEGER,
                    provider TEXT,
                    model TEXT,
                    created_at TEXT
                )
                """
            )

    def compute_key(
        self,
        provider: str,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        seed: int,
    ) -> str:
        payload = {
            "provider": provider,
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(self, key: str) -> Optional[LLMResult]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response_text, parsed_json, in_tokens, out_tokens, provider, model FROM llm_cache WHERE cache_key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row:
                resp_text, p_json_str, in_tok, out_tok, prov, mod = row
                p_json = json.loads(p_json_str) if p_json_str else None
                return LLMResult(
                    text=resp_text,
                    parsed_json=p_json,
                    usage={"in": in_tok, "out": out_tok},
                    provider=prov,
                    model=mod,
                    cached=True,
                    latency_s=0.001,
                )
        return None

    def put(self, key: str, result: LLMResult) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_cache (
                    cache_key, response_text, parsed_json, in_tokens, out_tokens, provider, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    result.text,
                    json.dumps(result.parsed_json) if result.parsed_json else None,
                    result.usage.get("in", 0),
                    result.usage.get("out", 0),
                    result.provider,
                    result.model,
                    datetime.utcnow().isoformat(),
                ),
            )


class BaseLLMProvider(ABC):
    """Abstract interface for LLM provider implementations."""

    name: str
    model: str

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_schema: Optional[Dict[str, Any]] = None,
        seed: int = 0,
    ) -> LLMResult:
        pass


class FakeLLMProvider(BaseLLMProvider):
    """Deterministic fake provider for fast unit tests without network."""

    def __init__(self, model: str = "fake-model") -> None:
        self.name = "fake"
        self.model = model

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
        json_schema: Optional[Dict[str, Any]] = None,
        seed: int = 0,
    ) -> LLMResult:
        user_prompt = messages[-1].get("content", "")
        # If refusal requested or out of scope
        if "out of scope" in user_prompt.lower() or "unanswerable" in user_prompt.lower():
            text = "I cannot answer this question as the provided documents do not contain the necessary information."
            parsed = {"answer": text, "citations": [], "refused": True}
        elif json_schema or "json" in user_prompt.lower():
            text = '{"answer": "Under RBI circular RBI/2025-26/90, the exposure limit is 25% for banks [1].", "citations": [1], "refused": false}'
            parsed = repair_and_parse_json(text)
        else:
            text = "Under RBI circular RBI/2025-26/90, the exposure limit is 25% for banks [1]."
            parsed = {"answer": text, "citations": [1], "refused": False}

        return LLMResult(
            text=text,
            parsed_json=parsed,
            usage={"in": len(user_prompt.split()), "out": len(text.split())},
            provider=self.name,
            model=self.model,
            cached=False,
            latency_s=0.005,
        )


class ExtractiveLLMProvider(BaseLLMProvider):
    """Deterministic sentence extraction fallback when no LLM key is available (Part D5)."""

    def __init__(self) -> None:
        self.name = "extractive"
        self.model = "bm25-sentence-extractor"

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
        json_schema: Optional[Dict[str, Any]] = None,
        seed: int = 0,
    ) -> LLMResult:
        user_prompt = messages[-1].get("content", "")
        # Extract query and context if present in prompt
        query_m = re.search(r"Question:\s*(.*?)(?:\n|$)", user_prompt, re.IGNORECASE)
        query = query_m.group(1).strip() if query_m else user_prompt[:80]

        # Extract context block exclusively to prevent prompt instructions leaking into chunks
        context_match = re.search(
            r"Context:\s*(.*?)(?=\n\s*Question:|\Z)", user_prompt, re.DOTALL | re.IGNORECASE
        )
        context_text = context_match.group(1) if context_match else user_prompt
        chunks_blocks = re.findall(r"\[(\d+)\]\s*(.*?)(?=\[\d+\]|\Z)", context_text, re.DOTALL)
        if not chunks_blocks:
            # Fallback to simple refusal
            text = "The requested information is not available in the provided documents."
            parsed = {"answer": text, "citations": [], "refused": True}
            return LLMResult(
                text=text,
                parsed_json=parsed,
                usage={"in": len(user_prompt.split()), "out": 12},
                provider=self.name,
                model=self.model,
                cached=False,
                latency_s=0.002,
            )

        # Word overlap scoring between query and context sentences (excluding stopwords)
        stops = {
            "who",
            "what",
            "where",
            "when",
            "why",
            "how",
            "is",
            "was",
            "are",
            "were",
            "the",
            "a",
            "an",
            "in",
            "on",
            "at",
            "for",
            "of",
            "to",
        }
        query_words = set(re.findall(r"\w+", query.lower())) - stops
        best_sentence = ""
        best_ref = 1
        best_score = 0

        for ref_str, text_block in chunks_blocks:
            ref_num = int(ref_str)
            sentences = [s.strip() for s in text_block.split(".") if len(s.strip()) > 10]
            for s in sentences:
                s_words = set(re.findall(r"\w+", s.lower()))
                overlap = len(query_words.intersection(s_words))
                if overlap > best_score:
                    best_score = overlap
                    best_sentence = s
                    best_ref = ref_num

        if best_score < 2 or not best_sentence:
            text = "The requested information cannot be found in the provided regulatory context."
            parsed = {"answer": text, "citations": [], "refused": True}
        else:
            text = f"{best_sentence}. [{best_ref}]"
            parsed = {"answer": text, "citations": [best_ref], "refused": False}

        return LLMResult(
            text=text,
            parsed_json=parsed,
            usage={"in": len(user_prompt.split()), "out": len(text.split())},
            provider=self.name,
            model=self.model,
            cached=False,
            latency_s=0.002,
        )


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.name = "gemini"
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
        json_schema: Optional[Dict[str, Any]] = None,
        seed: int = 0,
    ) -> LLMResult:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if json_schema:
            body["generationConfig"]["responseMimeType"] = "application/json"

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()

        text = ""
        cands = data.get("candidates", [])
        if cands:
            parts = cands[0].get("content", {}).get("parts", [])
            if parts:
                text = parts[0].get("text", "")

        parsed = repair_and_parse_json(text)
        usage_meta = data.get("usageMetadata", {})
        return LLMResult(
            text=text,
            parsed_json=parsed,
            usage={
                "in": usage_meta.get("promptTokenCount", 0),
                "out": usage_meta.get("candidatesTokenCount", 0),
            },
            provider=self.name,
            model=self.model,
            cached=False,
        )


class OpenAICompatProvider(BaseLLMProvider):
    """OpenAI compatible provider (Groq, Together, Ollama, OpenAI)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "llama-3.1-8b-instant",
        name: str = "groq",
    ) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
        json_schema: Optional[Dict[str, Any]] = None,
        seed: int = 0,
    ) -> LLMResult:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
        }
        if json_schema:
            body["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "")
        parsed = repair_and_parse_json(text)
        usage = data.get("usage", {})

        return LLMResult(
            text=text,
            parsed_json=parsed,
            usage={"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0)},
            provider=self.name,
            model=self.model,
            cached=False,
        )


class LLM:
    """Unified LLM facade with budget tracking, caching, retries, and fallbacks."""

    def __init__(
        self,
        provider: Optional[BaseLLMProvider] = None,
        cache: Optional[LLMCache] = None,
        max_calls: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.cache = cache or LLMCache()
        self.max_calls = max_calls or settings.LLM_MAX_CALLS
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        self.call_count = 0
        self.tokens_used = 0
        self.provider = provider or self._resolve_provider()

    def _resolve_provider(self) -> BaseLLMProvider:
        mode = settings.LLM_PROVIDER.lower()

        if mode == "fake":
            return FakeLLMProvider()
        if mode == "extractive":
            return ExtractiveLLMProvider()

        # Check API Keys
        if mode == "gemini" or (mode == "auto" and settings.GEMINI_API_KEY):
            if settings.GEMINI_API_KEY:
                return GeminiProvider(
                    api_key=settings.GEMINI_API_KEY,
                    model=settings.LLM_MODEL or "gemini-2.0-flash",
                )

        if mode == "groq" or (mode == "auto" and settings.GROQ_API_KEY):
            if settings.GROQ_API_KEY:
                return OpenAICompatProvider(
                    api_key=settings.GROQ_API_KEY,
                    base_url="https://api.groq.com/openai/v1",
                    model=settings.LLM_MODEL or "llama-3.1-8b-instant",
                    name="groq",
                )

        if mode == "openai_compat" or (
            mode == "auto" and settings.LLM_API_KEY and settings.LLM_BASE_URL
        ):
            if settings.LLM_API_KEY and settings.LLM_BASE_URL:
                return OpenAICompatProvider(
                    api_key=settings.LLM_API_KEY,
                    base_url=settings.LLM_BASE_URL,
                    model=settings.LLM_MODEL or "default",
                    name="openai_compat",
                )

        # Default fallback: Extractive Sentence Extractor
        return ExtractiveLLMProvider()

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
        json_schema: Optional[Dict[str, Any]] = None,
        seed: int = 0,
    ) -> LLMResult:
        """Call LLM with budget guard, deterministic caching, and error safety."""
        # 1. Check cache first
        cache_key = self.cache.compute_key(
            provider=self.provider.name,
            model=self.provider.model,
            messages=messages,
            temperature=temperature,
            seed=seed,
        )
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # 2. Budget Guard check
        if self.call_count >= self.max_calls or self.tokens_used >= self.max_tokens:
            # Fall back to extractive
            if not isinstance(self.provider, ExtractiveLLMProvider):
                extractive = ExtractiveLLMProvider()
                res = extractive.generate(messages, max_tokens, temperature, json_schema, seed)
                res.error = "Budget exceeded; degraded to extractive provider"
                return res

        # 3. Call Provider with tenacity retry
        t0 = time.perf_counter()
        try:
            res = self._call_with_retry(messages, max_tokens, temperature, json_schema, seed)
            res.latency_s = round(time.perf_counter() - t0, 3)

            # Update budget counters
            self.call_count += 1
            self.tokens_used += res.usage.get("in", 0) + res.usage.get("out", 0)

            # Store in cache
            self.cache.put(cache_key, res)
            return res

        except Exception as e:
            err_msg = redact_secrets(str(e))
            # Fallback to extractive on provider failure
            extractive = ExtractiveLLMProvider()
            res = extractive.generate(messages, max_tokens, temperature, json_schema, seed)
            res.error = f"Provider failure ({err_msg}); degraded to extractive provider"
            res.latency_s = round(time.perf_counter() - t0, 3)
            return res

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _call_with_retry(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_schema: Optional[Dict[str, Any]],
        seed: int,
    ) -> LLMResult:
        return self.provider.generate(messages, max_tokens, temperature, json_schema, seed)
