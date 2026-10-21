# 📊 RegulatorIQ Index & Retrieval Verification Report

**Generated At:** 2026-10-21T21:19:18.243640Z
**Index Version:** `2.1.0-BAAI_bge-small-en-v1_5-799bed3e`
**Total Chunks:** 111
**Embedding Model:** `BAAI/bge-small-en-v1.5` (384d, Degraded: `False`)
**Vector Backend:** `faiss` | **Quantisation:** `fp16`

---

## 🎯 Sanity Checks Summary

| Test Area | Metric | Result | Target | Status |
|---|---|---|---|---|
| **Self-Retrieval (Dense)** | Recall@5 | 92.9% | >= 90% | ✅ PASS |
| **Self-Retrieval (BM25)** | Recall@5 | 97.6% | >= 90% | ✅ PASS |
| **Identifier Exact Match** | Match Rate | 100.0% | 100% | ✅ PASS |
| **Filter Correctness** | Allow-Mask Integrity | 100.0% | 100% | ✅ PASS |

---

## ⚡ Latency & Resource Benchmarks

- **Dense Search (k=30):** p50 = 9.25 ms | p95 = 51.95 ms (Budget: <= 150 ms ✅)
- **BM25 Search (k=30):** p50 = 0.59 ms | p95 = 7.45 ms (Budget: <= 100 ms ✅)
- **Index Load Time:** 0.113 s (Budget: <= 15 s ✅)
- **Peak RSS:** 545.33 MB (Budget: <= 1,500 MB ✅)
- **Total Artifact Bytes:** 0.58 MB
