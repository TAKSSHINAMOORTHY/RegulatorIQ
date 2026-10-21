# 🏛️ RegulatorIQ

> **Agentic RAG System over Official Reserve Bank of India (RBI) Regulations.**  
> Sources exclusively from official `*.rbi.org.in` domains. Tracks supersession graphs, temporal validity, circular cross-references, and provides verified regulatory answers with source citations.

---

## ⚠️ Important Disclaimer
**RegulatorIQ is an unofficial open-source research and educational platform.**  
It is **not** affiliated with, endorsed by, or connected to the Reserve Bank of India (RBI).  
All regulatory content, Master Directions, circulars, notifications, and press releases remain the property of the Reserve Bank of India. This application does not constitute legal, financial, or regulatory compliance advice. Always consult the official [RBI website](https://www.rbi.org.in) for legal interpretations.

---

## ⚡ Quick Start

### 1. Bootstrap Environment
```bash
make bootstrap
```

### 2. Acquire Official RBI Corpus
```bash
make data
```

### 3. Run Quality Gates & Tests
```bash
make test-all
make ci
make verify-p1
```

---

## 📂 Repository Architecture
- `config/`: Central paths, environment settings, and schemas.
- `ingest/`: Polite crawler, HTML/PDF acquisition, normalisation, and manifest generator.
- `retrieval/`: Chunking, vector indexing (FAISS), BM25, and hybrid search.
- `agent/`: LangGraph agentic workflow, query decomposition, supersession graph resolution.
- `api/`: FastAPI backend with SSE streaming, rate limiting, and OpenAPI contracts.
- `evals/`: 100-question ground-truth evaluation set and metrics harness.
- `web/`: Next.js frontend with "Ledger Aurora" design system.
- `docs/`: Handoff states (`STATE.json`), architectural decisions (`DECISIONS.md`), and legal records.
- `reports/`: Corpus audit reports, benchmark results, and verification logs.

---

## 📜 Attribution & Fair Use
Every retrieval chunk, citation, and generated answer includes direct links to the canonical source on `rbi.org.in`. No content is mirrored on third-party domains.
