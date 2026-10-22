"""Verification script for Phase 4: Eval Set Generation, Baseline RAG, Metrics Harness.

Run via: `make verify-p4` or `python scripts/verify_p4.py`.
"""

from __future__ import annotations

import hashlib
import json

from config.paths import (
    BASELINES_DIR,
    EVAL_BASELINE_REPORT_MD,
    EVAL_SET_META,
    EVAL_SET_PATH,
    RUNS_DIR,
    STATE_FILE_PATH,
    THRESHOLDS_PATH,
)
from evals.gate import check_regression_gates
from evals.generate import EvalSetGenerator
from retrieval.index_store import IndexStore


def verify_phase_4() -> None:
    print("=" * 60)
    print(" Verifying Phase 4: Eval Set Generation & Baseline Harness")
    print("=" * 60)

    # 1. Check STATE.json
    assert STATE_FILE_PATH.exists(), "docs/STATE.json does not exist"
    with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)

    p4_state = state.get("phases", {}).get("4", {})
    assert p4_state.get("status") == "complete", "Phase 4 status in STATE.json is not complete"
    print("✓ docs/STATE.json phase 4 status is valid")

    # 2. Check eval_set.v1.jsonl & meta
    assert EVAL_SET_PATH.exists(), f"Missing {EVAL_SET_PATH}"
    assert EVAL_SET_META.exists(), f"Missing {EVAL_SET_META}"

    with open(EVAL_SET_META, "r", encoding="utf-8") as f:
        meta = json.load(f)

    actual_sha = hashlib.sha256(EVAL_SET_PATH.read_bytes()).hexdigest()
    assert actual_sha == meta.get("sha256"), "SHA256 of eval_set.v1.jsonl does not match meta file"
    print(f"✓ eval_set.v1.jsonl validates with sha256: {actual_sha[:12]}...")

    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    assert len(questions) == 100 or len(meta.get("shortfalls", [])) > 0, "Question count mismatch"
    print(f"✓ Evaluation set contains exactly {len(questions)} verified questions")

    # 3. Re-run HARD checks over the frozen set
    store = IndexStore.load(verify="fast")
    gen = EvalSetGenerator(store)
    for q in questions:
        is_valid, passed, failed = gen.verify_candidate(q)
        assert is_valid, f"HARD check failed for question {q['qid']}: {failed}"
    print("✓ Re-running HARD checks over frozen set passed for 100% of questions")

    # 4. Check baseline runs for dev and test exist
    p4_art = p4_state.get("artifacts", {})
    dev_run_id = p4_art.get("baseline_run_id_dev")
    test_run_id = p4_art.get("baseline_run_id_test")

    dev_dir = RUNS_DIR / dev_run_id
    test_dir = RUNS_DIR / test_run_id
    assert (
        dev_dir.exists()
        and (dev_dir / "metrics.json").exists()
        and (dev_dir / "report.md").exists()
    ), f"Missing dev run files in {dev_dir}"
    assert (
        test_dir.exists()
        and (test_dir / "metrics.json").exists()
        and (test_dir / "report.md").exists()
    ), f"Missing test run files in {test_dir}"
    print("✓ Baseline runs for dev and test exist with metrics.json and report.md")

    # 5. Check baseline.json and thresholds.yaml exist
    baseline_json = BASELINES_DIR / "baseline.json"
    assert baseline_json.exists(), f"Missing {baseline_json}"
    assert THRESHOLDS_PATH.exists(), f"Missing {THRESHOLDS_PATH}"
    print("✓ evals/baselines/baseline.json and evals/thresholds.yaml exist")

    # 6. Check eval-gate passes
    gate_ok = check_regression_gates(system_name="baseline")
    assert gate_ok, "eval-gate failed for baseline system"
    print("✓ eval-gate check passed successfully")

    # 7. Check reports/eval_baseline.md exists and documents provider and judge
    assert EVAL_BASELINE_REPORT_MD.exists(), f"Missing {EVAL_BASELINE_REPORT_MD}"
    report_content = EVAL_BASELINE_REPORT_MD.read_text(encoding="utf-8")
    assert "extractive" in report_content.lower() or "llm" in report_content.lower()
    assert "judge" in report_content.lower()
    print("✓ reports/eval_baseline.md exists with judge types and LLM details")

    print("\n✅ Phase 4 Verification PASSED successfully!\n")


if __name__ == "__main__":
    verify_phase_4()
