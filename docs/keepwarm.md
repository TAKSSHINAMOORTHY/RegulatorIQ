# Keep-Warm Strategy & Analysis

This document explains what 10 pings/day can and cannot achieve across cloud providers and details our keep-warm architecture.

---

## 1. Provider Capabilities Under 10 Pings/Day

| Provider | Sleep Threshold | 10 Pings/Day Impact | Verdict |
| :--- | :--- | :--- | :--- |
| **Hugging Face Spaces** | 48 hours idle | 10 pings/day keeps the Space permanently awake and responsive. | **100% Effective** |
| **Oracle Cloud (Always-Free)** | N/A (Always on) | Prevents idle-reclamation warnings by maintaining ongoing operational activity. | **Effective** |
| **AWS EC2 (Mumbai)** | N/A (Always on) | Keeps cache fresh in RAM; no cold start. | **Effective** |
| **Google Cloud Run** | Scales to 0 immediately | Warms instances during ping windows; cold starts still occur during off-schedule requests. | **Partial** |
| **Render Free Tier** | 15 minutes idle | Waking panel in frontend provides countdown and graceful explanation for cold starts. | **Partial (Expected)** |

---

## 2. Schedule Design (Indian Standard Time)

The 10 pings are scheduled at irregular, non-on-the-hour intervals throughout the Indian business day (07:00 - 22:00 IST) to maximize coverage:
1. `07:10 IST` (01:40 UTC)
2. `08:40 IST` (03:10 UTC)
3. `10:05 IST` (04:35 UTC)
4. `11:50 IST` (06:20 UTC)
5. `13:15 IST` (07:45 UTC)
6. `14:55 IST` (09:25 UTC)
7. `16:20 IST` (10:50 UTC)
8. `18:05 IST` (12:35 UTC)
9. `19:40 IST` (14:10 UTC)
10. `21:25 IST` (15:55 UTC)

---

## 3. Strict Safety Guards

1. **Non-LLM Execution:** `POST /warmup` runs embedding, BM25, and vector retrieval on a synthetic query. It **never invokes LLM APIs**, guaranteeing zero LLM quota consumption.
2. **Analytics Exclusion:** `X-Warmup: 1` header instructs the logging middleware to exclude warmup queries from the public query counters.
3. **Daily Cap:** `scripts/warmup.py` enforces a local counter refusing to execute more than 10 times in any rolling 24-hour window.
