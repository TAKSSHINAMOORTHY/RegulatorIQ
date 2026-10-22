# Prompt Changes and Impact Analysis

> Generated: 2026-10-22  
> Baseline: Initial Prompts Repository

---

## 1. Summary of Changed Files and Classifications

### `shared_prompt.txt`
- **Added: FILE HANDLING protocol**
  > `- This file is shared_prompt.txt in the repo root. Read it completely at the start of every prompt before doing anything else.`  
  > `- Prompt 1 also saves a copy to docs/shared_prompt.txt. If the root copy is missing in a later prompt, restore it from docs/shared_prompt.txt and log the repair in docs/DECISIONS.md.`
  - **Classification**: `new requirement`
- **Added: PLAN FILE, DRY-RUN AND RESUME RULES**
  > `- Plan file: before any work, write docs/PLAN_<N>.md containing a checklist of EVERY Part and step in the prompt...`  
  > `- Dry-run first: any long-running or external-facing operation must first run on a small sample...`  
  > `- Resume: after each Part, write docs/STATE.json phases[N].resume_point = "<Part letter>" and commit locally...`  
  > `- Time and quota awareness: respect free-tier quotas and record any quota-driven degradation.`
  - **Classification**: `new requirement`

---

### `prompts/7.txt`
- **Modified: Lifecycle and Port Binding**
  > `The process must bind the port within 2 seconds. Heavy work runs in a background task started by lifespan...`
  - **Classification**: `new requirement`
- **Added: Standalone Index Fetch and Preflight CLI**
  > `api/index_fetch.py (Range resume, sha256 verification, safe extraction, atomic swap)`  
  > `api/preflight.py (config validation, model load check, disk/RAM check, port bindability)`
  - **Classification**: `changed path/name/interface`
- **Added: Mock API Server for Frontend/Playwright**
  > `scripts/mock_api.py: a tiny standalone server implementing the same endpoints with scripted scenario streams (no index, no LLM), used by Prompt 8 for frontend development and Playwright tests.`
  - **Classification**: `new requirement`
- **Changed Paths**:
  > `API_DIR=api`, `OPENAPI_PATH=docs/openapi.json`, `TRACE_LOG_DIR=reports/logs/traces`  
  > `make openapi` -> `docs/openapi.json`, `make events-doc` -> `docs/events.md`, `docs/API.md`
  - **Classification**: `changed path/name/interface`

---

### `prompts/8.txt`
- **Modified: Design Language & Typography**
  > `Concept: an editorial, trustworthy regulatory "ledger" meets a calm aurora. Warm paper and ink in light mode; midnight ink with teal and violet glow in dark mode.`  
  > `Headings serif "Fraunces", UI "Inter", identifiers "JetBrains Mono".`
  - **Classification**: `new requirement`
- **Added: Live Animated Background with 3-Tier Fallback**
  > `<LiveBackground /> with WebGL2 flow-field ledger lines, Canvas2D particle fallback, static SVG fallback.`  
  > `Performance governor averaging over 60 frames (downgrading scale/tier if >24ms, pausing when hidden).`
  - **Classification**: `new requirement`
- **Added: Client Failover & Safe API Client**
  > `web/lib/apiClient.ts probes /health and /ready, retries /ask once on next URL before any token received.`
  - **Classification**: `new requirement`
- **Added: Automated Contrast Checker**
  > `scripts/check_contrast.ts computes WCAG AA contrast for every text/background and UI pair.`
  - **Classification**: `new requirement`

---

### `prompts/9.txt`
- **Modified: Multi-Provider Free Deployment Targets**
  > `deploy/<provider>/ for Oracle A1, Cloud Run, HF Space, AWS EC2 free, Render/Koyeb light mode, Vercel frontend.`
  - **Classification**: `new requirement`
- **Added: Automated Keep-Warm Workflow**
  > `scripts/warmup.py and .github/workflows/warmup.yml with 10 UTC cron entries (= irregular daytime IST).`
  - **Classification**: `new requirement`
- **Added: Post-Deploy Smoke Suite & Cold-Start Measurement**
  > `scripts/smoke.py and scripts/measure_coldstart.py recording time-to-first-byte, time-to-ready.`
  - **Classification**: `new requirement`
- **Added: Cost Guard and Secrets Scanners**
  > `scripts/cost_guard.py tagging project=regulatoriq, gitleaks, trivy, actionlint, hadolint.`
  - **Classification**: `new requirement`

---

## 2. Impact Assessment & Dependency Graph

1. **Phases 1–5**:
   - Status: Complete and verified (`make verify-p1` ... `make verify-p5` pass cleanly).
   - Action: Document checklists in `docs/PLAN_1.md` through `docs/PLAN_5.md`. No code changes required as shared data contracts remain intact.
2. **Phase 6**:
   - Status: Complete. All 18 scenario tests, Hypothesis property tests, and 16-thread concurrency tests pass.
   - Action: Generate `reports/agent_report.md` via `scripts/run_agent_eval.py`, update `evals/thresholds.yaml` and `docs/STATE.json`, verify with `make verify-p6`, commit, and push.
3. **Phase 7 (Immediate Next Phase)**:
   - Status: Ready to execute.
   - Action: Implement FastAPI app conforming to updated `prompts/7.txt`: `api/preflight.py`, `api/index_fetch.py`, `scripts/mock_api.py`, `docs/openapi.json`, SSE streaming, and lifespan state machine.
4. **Phases 8 & 9**:
   - Consume Phase 7 contracts (`docs/openapi.json`, `scripts/mock_api.py`, `events.schema.json`).
