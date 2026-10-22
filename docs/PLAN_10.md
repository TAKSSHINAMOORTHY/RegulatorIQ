# Plan 10: End-to-End Verification, Claims Audit, and Release Gate

## Overview
Perform comprehensive end-to-end audit and release validation across the entire RegulatorIQ project. Verify all phase contracts (Phases 1 through 9), audit every documented claim against raw metric artifacts, execute the full test matrix (unit, integration, property, frontend, CI), and produce the final status report with actionable manual handoffs.

---

## Part A: Verification Gates Audit (Phases 1-9)
- [ ] Verify Phase 1: Corpus acquisition and manifest integrity (`make verify-p1`).
- [ ] Verify Phase 2: PDF/HTML parsing, cleaning, linking, chunking (`make verify-p2`).
- [ ] Verify Phase 3: FastEmbed, BM25, and vector index store (`make verify-p3`).
- [ ] Verify Phase 4: Benchmark eval set, naive baseline, metrics harness (`make verify-p4`).
- [ ] Verify Phase 5: Hybrid search, reranking, ablation study (`make verify-p5`).
- [ ] Verify Phase 6: LangGraph agentic RAG, routing, self-check guard (`make verify-p6`).
- [ ] Verify Phase 7: FastAPI service, SSE streaming, security headers (`make verify-p7`).
- [ ] Verify Phase 8: Next.js frontend, Ledger Aurora theme, live background (`make verify-p8`).
- [ ] Verify Phase 9: Multi-provider deployment, keep-warm, CI/CD (`make verify-p9`).

## Part B: Claims & Metric Integrity Audit
- [ ] Verify documented performance claims in `reports/claims.md` match frozen evaluations.
- [ ] Verify state consistency in `docs/STATE.json` across all phases.
- [ ] Check no unverified secrets, tokens, or private data exist in repository.

## Part C: Full Test Matrix Execution
- [ ] Python unit & property test suite (`pytest tests/`).
- [ ] Frontend Vitest test suite (`npm test` in `web/`).
- [ ] Frontend strict TypeScript check (`npm run types:check` in `web/`).
- [ ] Linting & formatting check (`make lint`).
- [ ] Static type analysis (`make typecheck`).
- [ ] Full CI pipeline validation (`make ci`).

## Part D: Release Deliverables & Final Report
- [ ] Implementation of `scripts/verify_p10.py`.
- [ ] Makefile target `verify-p10` and `test-all`.
- [ ] Generation of `reports/FINAL_REPORT.md` featuring status banner, degraded modes, and manual steps.
- [ ] Final commit and push to remote repository.
