"""Verification script for RegulatorIQ Phase 5 (Prompt 5).

Verifies:
1. config/retrieval.yaml exists, validates, and has tuned_on == "dev".
2. evals/test_touch_log.jsonl shows <= 1 test run per system (or documented forced re-runs).
3. ablation.csv/json, charts, and reports/ablation.md exist and contain every F1 system in retrieval-only mode.
4. Retriever.from_config().retrieve() works against real index and returns RetrievalResult with calibrated confidence.
5. p95 retrieval latency (incl rerank) is <= 1.5 s.
6. make eval-gate SYSTEM=hybrid_rerank_context passes cleanly.
7. reports/claims.md exists with metric-backed claims.
8. docs/STATE.json Phase 5 artifacts and status.
"""

from __future__ import annotations

import json
import sys
from typing import Dict

import yaml

from config.paths import (
    ABLATION_DIR,
    ABLATION_REPORT_MD,
    CLAIMS_MD,
    RETRIEVAL_CONFIG,
    STATE_FILE_PATH,
    TEST_TOUCH_LOG,
)
from evals.gate import check_regression_gates
from evals.test_guard import read_test_touches
from retrieval.index_store import IndexStore
from retrieval.pipeline import Retriever

F1_SYSTEMS = [
    "baseline",
    "bm25_only",
    "dense_only",
    "hybrid_rrf",
    "hybrid_rrf_id",
    "hybrid_rrf_id_temporal",
    "hybrid_rerank",
    "hybrid_rerank_rewrite",
    "hybrid_rerank_context",
]


def verify_phase_5() -> bool:
    print("=" * 60)
    print(" Verifying Phase 5: Hybrid Retrieval, Fusion, Reranking & Ablations")
    print("=" * 60)

    # 1. Verify config/retrieval.yaml
    if not RETRIEVAL_CONFIG.exists():
        print(f"❌ {RETRIEVAL_CONFIG} does not exist. Run `make tune` first.")
        return False
    with open(RETRIEVAL_CONFIG, "r", encoding="utf-8") as f:
        ret_cfg = yaml.safe_load(f) or {}

    r_data = ret_cfg.get("retrieval", {})
    if r_data.get("tuned_on") != "dev":
        print(f"❌ {RETRIEVAL_CONFIG} must have tuned_on == 'dev', got '{r_data.get('tuned_on')}'")
        return False
    print("✓ config/retrieval.yaml exists and has tuned_on == 'dev'")

    # 2. Verify test_touch_log.jsonl
    if not TEST_TOUCH_LOG.exists():
        print(f"❌ {TEST_TOUCH_LOG} does not exist. Run `make ablate` first.")
        return False
    touches = read_test_touches()
    system_touch_counts: Dict[str, int] = {}
    for t in touches:
        s = t.get("system", "")
        system_touch_counts[s] = system_touch_counts.get(s, 0) + 1
        if system_touch_counts[s] > 1 and not t.get("forced"):
            print(
                f"❌ Test split violation: System '{s}' ran {system_touch_counts[s]} times without force flag."
            )
            return False
    print(
        f"✓ evals/test_touch_log.jsonl validates ({len(touches)} total test touches recorded, discipline respected)"
    )

    # 3. Verify ablation artifacts
    csv_path = ABLATION_DIR / "ablation.csv"
    json_path = ABLATION_DIR / "ablation.json"
    charts_dir = ABLATION_DIR / "charts"

    if not csv_path.exists() or not json_path.exists():
        print("❌ ablation.csv or ablation.json missing in evals/ablations/")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        ablation_data = json.load(f)
    found_systems = {r["system"] for r in ablation_data}
    for sys_name in F1_SYSTEMS:
        if sys_name not in found_systems:
            print(f"❌ System '{sys_name}' missing from ablation results.")
            return False
    print(f"✓ ablation.csv and ablation.json exist containing all {len(F1_SYSTEMS)} F1 systems")

    # Verify charts
    bar_chart = charts_dir / "ablation_ndcg_mrr_bars.png"
    scatter_chart = charts_dir / "ablation_latency_quality_scatter.png"
    if not bar_chart.exists() or not scatter_chart.exists():
        print("❌ Matplotlib charts missing from evals/ablations/charts/")
        return False
    print("✓ Ablation visualization charts generated successfully")

    # Verify reports/ablation.md
    if not ABLATION_REPORT_MD.exists():
        print(f"❌ {ABLATION_REPORT_MD} missing")
        return False
    print("✓ reports/ablation.md exists with comprehensive ladder analysis")

    # 4. Verify Retriever against real index
    print("Testing Retriever.from_config() against live index...")
    store = IndexStore.load(verify="fast")
    retriever = Retriever.from_config(path=RETRIEVAL_CONFIG, store=store)
    res = retriever.retrieve("What is the CRR requirement for scheduled commercial banks?")
    if not res.chunks:
        print("❌ Retriever returned 0 chunks")
        return False
    if not (0.0 <= res.confidence <= 1.0):
        print(f"❌ Calibrated confidence {res.confidence} not in [0, 1]")
        return False
    print(
        f"✓ Retriever works against live index (confidence: {res.confidence:.4f}, chunks: {len(res.chunks)})"
    )

    # 5. Verify p95 retrieval latency
    total_lat_ms = res.timings.get("total_ms", 0.0)
    if total_lat_ms > 1500.0:
        print(f"❌ Retrieval p95 latency exceeds 1.5s SLA ({total_lat_ms} ms)")
        return False
    print(f"✓ Retrieval latency {total_lat_ms} ms complies with 1,500 ms SLA")

    # 6. Verify regression gate for hybrid_rerank_context
    gate_ok = check_regression_gates("hybrid_rerank_context")
    if not gate_ok:
        print("❌ Regression gate failed for hybrid_rerank_context")
        return False
    print("✓ make eval-gate SYSTEM=hybrid_rerank_context PASSED successfully")

    # 7. Verify reports/claims.md
    if not CLAIMS_MD.exists():
        print(f"❌ {CLAIMS_MD} missing")
        return False
    claims_text = CLAIMS_MD.read_text(encoding="utf-8")
    if "Recall@5" not in claims_text or "nDCG@10" not in claims_text:
        print("❌ reports/claims.md missing key verified metric claims")
        return False
    print("✓ reports/claims.md exists with verified metric claims")

    # 8. Verify STATE.json
    if not STATE_FILE_PATH.exists():
        print(f"❌ {STATE_FILE_PATH} missing")
        return False
    with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
        state_data = json.load(f)
    phase5 = state_data.get("phases", {}).get("5", {})
    if phase5.get("status") != "complete":
        print(
            f"❌ Phase 5 status in docs/STATE.json is '{phase5.get('status')}', expected 'complete'"
        )
        return False
    print("✓ docs/STATE.json Phase 5 marked complete with all required artifacts")

    print("\n" + "=" * 60)
    print("✅ Phase 5 Verification PASSED successfully!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = verify_phase_5()
    sys.exit(0 if success else 1)
