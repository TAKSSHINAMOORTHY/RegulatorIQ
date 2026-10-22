"""Unit tests for agent/llm.py with respx HTTP mocks and budget guards."""

from __future__ import annotations

import httpx
import respx

from agent.llm import (
    LLM,
    ExtractiveLLMProvider,
    FakeLLMProvider,
    LLMCache,
    OpenAICompatProvider,
    redact_secrets,
    repair_and_parse_json,
)


def test_redact_secrets():
    raw = "Error calling API with AIzaSyD12345678901234567890123456789012 and gsk_1234567890abcdef1234567890abcdef1234567890abcdef"
    redacted = redact_secrets(raw)
    assert "[REDACTED_GEMINI_KEY]" in redacted
    assert "[REDACTED_GROQ_KEY]" in redacted
    assert "AIzaSyD" not in redacted


def test_repair_and_parse_json():
    # Markdown code fence stripping
    raw_markdown = '```json\n{"answer": "Test answer", "refused": false}\n```'
    parsed = repair_and_parse_json(raw_markdown)
    assert parsed == {"answer": "Test answer", "refused": False}

    # Trailing commas fix
    raw_trailing = '{"answer": "Test", "citations": [1, 2, ], "refused": false, }'
    parsed2 = repair_and_parse_json(raw_trailing)
    assert parsed2 is not None
    assert parsed2["answer"] == "Test"
    assert parsed2["citations"] == [1, 2]


def test_llm_cache_hit_and_miss(tmp_path):
    cache_db = tmp_path / "test_cache.sqlite"
    cache = LLMCache(db_path=cache_db)

    prov = FakeLLMProvider()
    llm = LLM(provider=prov, cache=cache)

    messages = [{"role": "user", "content": "What is the exposure limit?"}]

    # Call 1: Cache Miss
    res1 = llm.generate(messages=messages, seed=1)
    assert not res1.cached
    assert "Under RBI circular" in res1.text

    # Call 2: Cache Hit
    res2 = llm.generate(messages=messages, seed=1)
    assert res2.cached
    assert res2.text == res1.text


def test_budget_guard_fallback(tmp_path):
    prov = FakeLLMProvider()
    cache = LLMCache(db_path=tmp_path / "b_cache.sqlite")
    # Cap at 2 calls
    llm = LLM(provider=prov, cache=cache, max_calls=2)

    messages = [
        {
            "role": "user",
            "content": "Question: What is the bank rate?\nContext:\n[1] The bank rate is 6.5%. [1]",
        }
    ]

    # Call 1 (within budget)
    res1 = llm.generate(messages=messages, seed=1)
    assert res1.error is None

    # Call 2 (within budget)
    res2 = llm.generate(messages=messages, seed=2)
    assert res2.error is None

    # Call 3 (budget exceeded -> degrades to ExtractiveLLMProvider)
    res3 = llm.generate(messages=messages, seed=3)
    assert res3.error is not None
    assert "Budget exceeded" in res3.error


@respx.mock
def test_openai_compat_success():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"answer": "Mocked response", "refused": false}'}}
                ],
                "usage": {"prompt_tokens": 15, "completion_tokens": 8},
            },
        )
    )

    provider = OpenAICompatProvider(
        api_key="gsk_test1234567890abcdef1234567890abcdef1234567890abcdef"
    )
    res = provider.generate([{"role": "user", "content": "Test"}])
    assert res.text == '{"answer": "Mocked response", "refused": false}'
    assert res.parsed_json == {"answer": "Mocked response", "refused": False}
    assert res.usage["in"] == 15


@respx.mock
def test_retry_on_500_then_success(tmp_path):
    route = respx.post("https://api.groq.com/openai/v1/chat/completions")
    # First attempt fails with 500, second succeeds with 200
    route.side_effect = [
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer": "Recovered response"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        ),
    ]

    provider = OpenAICompatProvider(api_key="gsk_mock_key")
    cache = LLMCache(db_path=tmp_path / "r_cache.sqlite")
    llm = LLM(provider=provider, cache=cache)

    res = llm.generate([{"role": "user", "content": "Test"}])
    assert "Recovered response" in res.text
    assert route.call_count == 2


@respx.mock
def test_gemini_provider_success():
    respx.post(url__regex=r"https://generativelanguage\.googleapis\.com/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"answer": "Gemini answer", "refused": false}'}]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 10},
            },
        )
    )
    from agent.llm import GeminiProvider

    gemini = GeminiProvider(api_key="AIzaSyD_test_key_12345")
    res = gemini.generate([{"role": "user", "content": "Test query"}])
    assert res.provider == "gemini"
    assert res.parsed_json == {"answer": "Gemini answer", "refused": False}


def test_provider_exception_falls_back_to_extractive(tmp_path):
    class FailingProvider:
        name = "failing"
        model = "fail-model"

        def generate(self, *args, **kwargs):
            raise httpx.RequestError("API endpoint unavailable")

    cache = LLMCache(db_path=tmp_path / "f_cache.sqlite")
    llm = LLM(provider=FailingProvider(), cache=cache)

    res = llm.generate(
        [
            {
                "role": "user",
                "content": "Context:\n[1] The repo rate is 6.5%. [1]\n\nQuestion: What is the repo rate?",
            }
        ]
    )
    assert res.error is not None
    assert "degraded to extractive" in res.error
    assert res.text != ""


def test_fake_provider_json_and_refusal():
    fake = FakeLLMProvider()
    res_json = fake.generate(
        [{"role": "user", "content": "Return json answer"}], json_schema={"type": "object"}
    )
    assert res_json.parsed_json is not None

    res_refusal = fake.generate([{"role": "user", "content": "This is out of scope"}])
    assert res_refusal.parsed_json["refused"] is True


def test_extractive_provider_no_context():
    ext = ExtractiveLLMProvider()
    res = ext.generate([{"role": "user", "content": "No context here"}])
    assert res.parsed_json["refused"] is True
