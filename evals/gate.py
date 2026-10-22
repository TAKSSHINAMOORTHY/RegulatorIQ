"""Regression Gating for RegulatorIQ Evaluation in CI/CD.

Checks evaluation run metrics against evals/thresholds.yaml:
1. Metric must meet or exceed the absolute floor.
2. Metric must not fall below (baseline_mean - tolerance), where tolerance = 1.0 x CI half-width.
Exits with non-zero code on regression.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from config.paths import RUNS_DIR, THRESHOLDS_PATH
from evals.run import run_evaluation


def load_thresholds() -> Dict[str, Any]:
    """Load CI regression thresholds from YAML."""
    if not THRESHOLDS_PATH.exists():
        raise FileNotFoundError(f"Thresholds file not found at {THRESHOLDS_PATH}")
    with open(THRESHOLDS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_latest_run_for_system(system_name: str, split: str = "test") -> Optional[Path]:
    """Find the most recent run directory for a given system and split."""
    if not RUNS_DIR.exists():
        return None
    runs = []
    for d in RUNS_DIR.iterdir():
        if d.is_dir() and (d / "config.json").exists() and (d / "metrics.json").exists():
            try:
                with open(d / "config.json", "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if cfg.get("system_name") == system_name and cfg.get("split") in (split, "all"):
                        runs.append((cfg.get("timestamp_utc", ""), d))
            except Exception:
                continue
    if not runs:
        return None
    runs.sort(key=lambda x: x[0], reverse=True)
    return runs[0][1]


def check_regression_gates(system_name: str, run_id_or_path: Optional[str] = None) -> bool:
    """Validate system metrics against regression gates."""
    thresholds_data = load_thresholds()
    # Check if a system-specific configuration exists
    if "systems" in thresholds_data and system_name in thresholds_data["systems"]:
        sys_cfg = thresholds_data["systems"][system_name]
        metric_gates = sys_cfg.get("metric_gates", {})
        overall_gate = sys_cfg.get("overall_score_floor")
    else:
        metric_gates = thresholds_data.get("metric_gates", {})
        overall_gate = thresholds_data.get("overall_score_floor")

    if run_id_or_path:
        run_path = Path(run_id_or_path)
        if not run_path.is_dir():
            run_path = RUNS_DIR / run_id_or_path

    else:
        run_path = find_latest_run_for_system(system_name, split="test")
        if not run_path:
            print(f"No existing test run found for system '{system_name}'. Executing run now...")
            run_id, _ = run_evaluation(system_name=system_name, split="test", save_run=True)
            run_path = RUNS_DIR / run_id

    metrics_file = run_path / "metrics.json"
    with open(metrics_file, "r", encoding="utf-8") as f:
        run_data = json.load(f)

    cfg = run_data["run_config"]
    headline = run_data["headline_metrics"]
    overall = run_data["overall_score"]

    print("=" * 65)
    print(f" REGRESSION GATE CHECK: System='{system_name}' Split='{cfg.get('split')}'")
    print(f" Run ID: {cfg.get('run_id')}")
    print("=" * 65)

    failures: List[str] = []

    # Check overall score gate if present
    if overall_gate is not None:
        if overall < overall_gate:
            failures.append(f"Overall score {overall:.4f} is below floor {overall_gate:.4f}")
        else:
            print(f"✓ Overall score: {overall:.4f} >= {overall_gate:.4f}")

    # Check metric gates
    for metric_name, gate_cfg in metric_gates.items():
        if metric_name not in headline:
            continue

        val = float(headline[metric_name]["mean"])
        floor = gate_cfg.get("floor")
        base_val = gate_cfg.get("baseline_mean")
        tol = gate_cfg.get("tolerance", 0.0)

        # 1. Floor check
        if floor is not None and val < floor:
            failures.append(f"Metric '{metric_name}' value {val:.4f} < floor {floor:.4f}")

        # 2. Regression check against baseline
        if base_val is not None:
            min_allowed = base_val - tol
            if val < min_allowed:
                failures.append(
                    f"Metric '{metric_name}' regressed: {val:.4f} < (baseline {base_val:.4f} - tol {tol:.4f} = {min_allowed:.4f})"
                )
            else:
                print(
                    f"✓ {metric_name:20s}: {val:.4f} (baseline: {base_val:.4f}, min_allowed: {min_allowed:.4f})"
                )
        else:
            print(f"✓ {metric_name:20s}: {val:.4f}")

    print("=" * 65)
    if failures:
        print("❌ REGRESSION GATE FAILED with the following violations:")
        for fail in failures:
            print(f"  - {fail}")
        return False

    print("✅ All evaluation gates PASSED successfully!")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check evaluation regression gates")
    parser.add_argument("--system", default="baseline", help="System name")
    parser.add_argument("--run", default=None, help="Optional run ID or directory")
    args = parser.parse_args()

    passed = check_regression_gates(args.system, args.run)
    sys.exit(0 if passed else 1)
