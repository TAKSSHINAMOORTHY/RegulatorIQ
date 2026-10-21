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
