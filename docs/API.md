# RegulatorIQ: Production API Reference (FastAPI)

> **Service Version**: `0.1.0` | **Protocol**: HTTP/1.1 & HTTP/2 | **Default Port**: `8000` (local), `7860` (container)

---

## 1. Endpoints Overview

| Method | Path | Auth Required | Description | Typical Latency |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public | Liveness probe. Touches no models or storage. | < 5ms |
| `GET` | `/ready` | Public | Readiness probe. Returns 200 when ready, 503 during warmup. | < 10ms |
| `POST` | `/warmup` | Bearer (`WARMUP_TOKEN`) | Primes FAISS, BM25, and rerankers. Never calls LLMs. | ~500ms |
| `POST` | `/ask` | Optional (`X-API-Key`) | Regulatory analysis. Supports SSE streaming or JSON mode. | 300ms–2500ms |
| `POST` | `/feedback` | Public | Collects user up/down ratings with PII redaction. | < 20ms |
| `GET` | `/meta` | Public | Engine version, corpus statistics, and legal disclaimers. | < 10ms |
| `GET` | `/version` | Public | Git commit SHA, build timestamp, and index version. | < 5ms |
| `GET` | `/metrics` | Bearer (`METRICS_TOKEN`)| Prometheus-formatted runtime metrics (404 if unset). | < 15ms |

---

## 2. Operational Degradation Ladder

RegulatorIQ guarantees zero 500 crashes during upstream quota exhaustion or hardware constraints:

1. **`FULL` Mode**: Standard production mode. Uses external LLMs (e.g. Gemini 2.0 Flash / Groq LLaMA 3.1) combined with cross-encoder rerankers and FAISS hybrid vector retrieval.
2. **`RULES` Mode**: Triggered automatically when daily LLM budget is exhausted (`GLOBAL_DAILY_LLM_CALLS`) or upstream providers fail 3 consecutive attempts. Answers are synthesized deterministically using the extractive sentence parser and graph traversal. Zero external API calls.
3. **`LIGHT` Mode**: Activated via `RAG_LIGHT_MODE=1`. Strips dense neural rerankers and embedding caches. Answers run exclusively over BM25 inverted indices under ~300MB RAM footprints.

---

## 3. Example `curl` Commands

### A. Liveness & Readiness
```bash
# Check liveness
curl -i http://localhost:8000/health

# Check readiness
curl -i http://localhost:8000/ready
```

### B. Streaming Ask (Server-Sent Events)
```bash
curl -N --no-buffer -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "question": "What are the latest capital adequacy requirements for commercial banks?",
    "options": {
      "as_of": "2026-10-01",
      "interactive": true
    }
  }'
```

### C. Non-Streaming Ask (JSON)
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"question": "What is the penalty for late regulatory submission?"}'
```

### D. Authenticated Cache Warmup
```bash
curl -X POST http://localhost:8000/warmup \
  -H "Authorization: Bearer test_warmup_token_123"
```

### E. User Feedback
```bash
curl -i -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "c9a6331a-0352-45e0-82d2-8be0a597a7e1",
    "rating": "up",
    "reason": null,
    "comment": "Accurately cited Master Direction 2024."
  }'
```

---

## 4. Security Hardening & Rate Limits

- **Security Headers**: Injected automatically on every response (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `CSP: default-src 'none'`, `Strict-Transport-Security` when HTTPS).
- **Output Sanitizer**: Strips file paths, API keys, and external links. Only `*.rbi.org.in` domains are permitted in answers and citations.
- **Payload Limits**: Max 16 KB body size enforced during streaming (`413 Payload Too Large`).
- **Rate Limiting**: Token bucket per client IP (12 RPM, burst 4, 150 daily cap on `/ask`).
