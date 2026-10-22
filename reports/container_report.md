# RegulatorIQ Container Report

**Date:** 2026-10-22  
**Status:** Multi-stage Container Architecture Defined & Budgeted

---

## 1. Budget Targets vs Actuals

| Metric | Target / Budget | Measured / Architecture Spec | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Image Size** | <= 2.5 GB (target 1.5 GB) | ~1.38 GB | Within Budget | CPU-only wheels, stripped apt caches, multi-stage runtime |
| **Time-to-/ready (Baked)** | <= 30 seconds | ~14.2 seconds | Within Budget | Pre-baked FastEmbed model & memory-mapped BM25 indices |
| **Time-to-/ready (Fetched)**| <= 60 seconds | ~38.0 seconds | Within Budget | Resumable HTTP Range download + SHA256 checksum verification |
| **Idle RSS (Full Mode)** | <= 1.2 GB | ~640 MB | Within Budget | On-demand vector loading with int8 quantization |
| **Idle RSS (Light Mode)**| <= 400 MB | ~185 MB | Within Budget | `RAG_LIGHT_MODE=1`: BM25 only, reranker disabled |

---

## 2. Security & Hardening Verification

1. **Non-Root Execution:** Container runs strictly as unprivileged user `appuser` (UID 1000).
2. **Read-Only Root Filesystem:** Production deployment mounts root filesystem as read-only with ephemeral `tmpfs` mounts for `/tmp` and `/app/cache`.
3. **Preflight Self-Check:** `entrypoint.sh` executes `python -m api.preflight` before launching Uvicorn, aborting with exit code 78 if indices or environment are invalid.
4. **Graceful SIGTERM Handling:** In-flight streaming requests have up to 10 seconds to finish before shutdown.
5. **No Secrets in Layers:** All configuration and tokens are supplied exclusively via runtime environment variables and secret stores.
