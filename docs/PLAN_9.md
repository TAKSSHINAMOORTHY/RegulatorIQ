# Plan 9: Containerisation, CI/CD, Multi-Provider Deployment, Keep-Warm

## Overview
Package the API and frontend into standard containers, automate CI/CD workflows, configure multi-provider free hosting targets with credential-driven fallback (PENDING files), implement an irregular keep-warm schedule (capped at 10 runs/day), and provide complete operational runbooks and cold-start reports.

---

## Part A: Container Image (docker/Dockerfile)
- [x] Multi-stage build with pinned dependencies, CPU-only wheels, python:3.11-slim, non-root user UID 1000.
- [x] Bake FastEmbed and reranker models at build time for offline verification (`HF_HUB_OFFLINE=1`).
- [x] Index delivery modes: baked (<= 700MB), fetched (HTTP Range resume, sha256 check), external (Qdrant).
- [x] `docker/entrypoint.sh` with preflight checks, index fetch, graceful SIGTERM handling (10s).
- [x] Light mode support (`RAG_LIGHT_MODE=1`) for 512MB RAM hosts.
- [x] Budgets documented in `reports/container_report.md` (image <= 2.5GB, cold start <= 30s/60s).
- [x] Local compose (`docker/compose.yaml`) and production Caddy TLS proxy (`docker/compose.prod.yaml`).
- [x] Docker availability handling: fallback to `docker_unverified: true` when Docker is missing locally.

## Part B: Provider Targets (deploy/<provider>/)
- [x] Oracle Cloud Always-Free Terraform config (`deploy/oracle/`).
- [x] Google Cloud Run config (`deploy/cloudrun/`).
- [x] Hugging Face Spaces Docker SDK config (`deploy/hfspace/`).
- [x] AWS EC2 Free Plan Terraform config (`deploy/aws/`).
- [x] Light tier configs (Render blueprint `render.yaml`, Koyeb script in `deploy/light/`).
- [x] Vercel frontend configuration (`deploy/vercel/`).
- [x] Web client failover implementation (`web/lib/apiClient.ts`).
- [x] Ordering and circular dependency resolution in `scripts/deploy.py`.
- [x] PENDING files generated for missing credentials (`deploy/PENDING_*.md`).

## Part C: Deployment Orchestrator
- [x] Credential detection table and plan generation (`scripts/deploy.py`).
- [x] Dry-run and apply modes (`--apply` flag).
- [x] Tracking in `deploy/deployments.json` and reporting in `reports/deploy_report.md`.

## Part D: Post-Deploy Smoke & Cold-Start Measurement
- [x] Smoke test suite (`scripts/smoke.py`) testing health, ready, security headers, warmup, streaming SSE, refusals.
- [x] Cold-start measurement script (`scripts/measure_coldstart.py`) and report (`reports/coldstart.md`).

## Part E: Keep-Warm Automation
- [x] Keep-warm script (`scripts/warmup.py`) with 10 runs/day rolling 24h cap, retries, jitter.
- [x] GitHub Actions workflow (`.github/workflows/warmup.yml`) with 10 exact irregular UTC schedules.
- [x] Documentation in `docs/keepwarm.md` detailing provider cold starts and limitations.

## Part F: Security, Secrets & Cost Guards
- [x] Token generator (`scripts/gen_token.py`).
- [x] Cost guard script (`scripts/cost_guard.py`) and weekly workflow (`.github/workflows/cost-guard.yml`).
- [x] Security scanners in CI (`.github/workflows/ci.yml`).

## Part G: CI/CD Workflows & Dependabot
- [x] `ci.yml`, `deploy.yml`, `eval-gate.yml`, `warmup.yml`, `cost-guard.yml`.
- [x] Dependabot configuration (`.github/dependabot.yml`).

## Part H: Documentation
- [x] `docs/DEPLOYMENT.md`, `docs/RUNBOOK.md`, `docs/keepwarm.md`, `docs/INDEX_DELIVERY.md`, `docs/SECURITY.md`.

## Part I: Tests & Verification
- [ ] Comprehensive unit and property tests in `tests/unit/test_phase9.py`.
- [ ] Verification script `scripts/verify_p9.py`.
- [ ] Makefile targets added and verified (`make verify-p9`).
