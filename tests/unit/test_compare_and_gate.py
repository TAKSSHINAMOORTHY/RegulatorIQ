"""Tests for run comparison and CI regression gating."""

from __future__ import annotations

import pytest

from evals.compare import JudgeTypeMismatchError, compare_runs
from evals.gate import check_regression_gates
from evals.run import run_evaluation


def test_judge_type_mismatch_raises_error(tmp_path):
    # Run 1 with lexical_support
    run_1, _ = run_evaluation(
        system_name="baseline", split="dev", judge_type="lexical_support", save_run=True
    )
    # Run 2 with llm_judge
    run_2, _ = run_evaluation(
        system_name="baseline", split="dev", judge_type="llm_judge", save_run=True
    )

    with pytest.raises(JudgeTypeMismatchError):
        compare_runs(run_1, run_2)


def test_eval_gate_passes_for_baseline():
    passed = check_regression_gates(system_name="baseline")
    assert passed, "Regression gate should pass for baseline reference"


def test_compare_runs_success():
    run_1, _ = run_evaluation(
        system_name="baseline", split="dev", judge_type="lexical_support", save_run=True
    )
    run_2, _ = run_evaluation(
        system_name="baseline", split="dev", judge_type="lexical_support", save_run=True
    )

    report = compare_runs(run_1, run_2)
    assert "# Run Comparison:" in report
    assert "Paired Bootstrap Metric Differences" in report
    assert "recall_at_5" in report
