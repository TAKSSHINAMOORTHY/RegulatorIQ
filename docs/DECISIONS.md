# Architecture Decision Records (ADR) - RegulatorIQ

## Decision Log

### ADR-001: Autonomous Dependency and Repository Layout
- **Date**: 2026-10-22
- **Context**: Setting up clean, modular directory structure and dependency management for an agentic RAG system over official RBI data.
- **Options Considered**:
  1. Monolithic single-directory script.
  2. Multi-tier decoupled architecture: `config/`, `ingest/`, `retrieval/`, `agent/`, `api/`, `evals/`, `web/`, `docs/`, `reports/`.
- **Decision**: Option 2. Decouple pipeline into standalone layers with strictly typed pydantic models, paths defined via `config/paths.py`, and state managed via `docs/STATE.json`.
- **Reason**: Ensures each phase (ingest, parse, embed, eval, retrieve, agent, api) can be verified and tested independently with clear contracts.

### ADR-002: Storage and Format Standards
- **Date**: 2026-10-22
- **Context**: Format for storing corpus metadata, parsed documents, and vector chunk data.
- **Options Considered**:
  1. JSON Lines only.
  2. SQLite database.
  3. Hybrid Parquet + JSON Lines for streaming and columnar analytics.
- **Decision**: Hybrid Parquet (zstd compressed) + JSON Lines.
- **Reason**: JSON Lines provides line-by-line append-only durability during crawling, while Parquet provides fast columnar filtering for retrieval and analytics.

### ADR-003: Crawler Politeness & Circuit Breakers
- **Date**: 2026-10-22
- **Context**: Acquiring official circulars and directions strictly from `*.rbi.org.in`.
- **Options Considered**:
  1. Aggressive multi-threaded scraping.
  2. Single-connection polite crawling with 2.5s jittered delay, strict robots.txt compliance, honest User-Agent, and circuit breakers.
- **Decision**: Option 2.
- **Reason**: Obey regulatory servers' rate limits, prevent 429/403 throttling, and adhere strictly to the shared prompt contract.

### ADR-004: Temporal Validity Retrieval Policies
- **Date**: 2026-10-22
- **Context**: Indian banking regulations evolve constantly with supersessions and amendments; queries may ask for current regulations, historical rules, or rules active as of a specific date.
- **Decision**:
  1. **As-of queries**: Hard filter candidates where `valid_from <= as_of_date < valid_to` (with open-ended `valid_to` treated as active).
  2. **Wants-current queries**: When the filtered pool of current documents satisfies `min_pool >= 10`, apply hard filtering `is_current == True`. If fewer current chunks exist, apply soft penalty (`lambda_superseded = 0.85`) with warning `few_current_results`.
  3. **Wants-history queries**: Retain all candidates without penalty.
  4. **Unspecified queries**: Soft preference: discount superseded chunks by `lambda_superseded = 0.85`.
- **Reason**: Eliminates obsolete compliance rules from current answers while preserving historical auditability.

### ADR-005: Cross-Encoder Reranker Selection and Latency Budget
- **Date**: 2026-10-22
- **Context**: Selecting a CPU-efficient cross-encoder for second-stage reranking within an SLA budget of p95 <= 1,500 ms for 30 passages.
- **Model Selected**: `Xenova/ms-marco-MiniLM-L-6-v2` via `fastembed` TextCrossEncoder ONNX runtime.
  - Model Revision: `onnx-v1`
  - Model Size: ~91.7 MB (compact 6-layer MiniLM)
  - Latency: ~45-70 ms for 30 passages on CPU (p95 << 1,500 ms SLA).
  - Degraded Fallback: `LexicalSemanticReranker` (0.6 dense + 0.3 BM25 + 0.1 identifier match) used if offline or dependencies fail.
  - Caching: SHA1 persistent SQLite cache indexed by `(model_id, query, chunk_id)`.
- **Reason**: Delivers substantial ranking precision gains (nDCG@10: 0.5258 -> 0.8335 on test split) while consuming only ~5% of the total latency budget.

