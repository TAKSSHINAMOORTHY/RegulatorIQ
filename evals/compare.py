"""Comparison Harness for RegulatorIQ Evaluation Runs.

Compares two evaluation runs using paired bootstrap differences with 95% confidence intervals.
STRICT REQUIREMENT: Refuses to compute deltas across different judge types.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config.paths import RUNS_DIR
from evals.metrics import paired_bootstrap_delta


class JudgeTypeMismatchError(Exception):
    """Raised when comparing runs evaluated with incompatible judge types."""


def load_run_data(run_id_or_path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load run metrics and results from RUNS_DIR or direct path."""
    p = Path(run_id_or_path)
    if not p.is_dir():
        p = RUNS_DIR / run_id_or_path

    if not p.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_id_or_path}")

    metrics_file = p / "metrics.json"
    results_file = p / "results.jsonl"

    if not metrics_file.exists():
        raise FileNotFoundError(f"Missing metrics.json in {p}")

    with open(metrics_file, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    results = []
    if results_file.exists():
        with open(results_file, "r", encoding="utf-8") as f:
            results = [json.loads(line) for line in f if line.strip()]

    return metrics, results


def compare_runs(run_a_id: str, run_b_id: str) -> str:
    """Compare two evaluation runs and return Markdown comparison table."""
    metrics_a, results_a = load_run_data(run_a_id)
    metrics_b, results_b = load_run_data(run_b_id)

    cfg_a = metrics_a["run_config"]
    cfg_b = metrics_b["run_config"]

    # HARD RULE: Refuse comparison across different judge types
    judge_a = cfg_a.get("judge_type")
    judge_b = cfg_b.get("judge_type")
    if judge_a != judge_b:
        raise JudgeTypeMismatchError(
            f"Cannot compare runs with different judge types: Run A has '{judge_a}', "
            f"Run B has '{judge_b}'. Comparisons are valid only with identical judge types."
        )

    # Check identical sample sets
    qids_a = [r["qid"] for r in results_a]
    qids_b = [r["qid"] for r in results_b]
    if qids_a != qids_b:
        # Align by common qids if needed
        common_qids = [qid for qid in qids_a if qid in set(qids_b)]
        map_a = {r["qid"]: r for r in results_a}
        map_b = {r["qid"]: r for r in results_b}
        results_a = [map_a[qid] for qid in common_qids]
        results_b = [map_b[qid] for qid in common_qids]

    md = []
    md.append(f"# Run Comparison: `{cfg_a['run_id']}` (A) vs `{cfg_b['run_id']}` (B)")
    md.append("")
    md.append(f"- **System A**: `{cfg_a['system_name']}` ({cfg_a.get('split', 'all')})")
    md.append(f"- **System B**: `{cfg_b['system_name']}` ({cfg_b.get('split', 'all')})")
    md.append(f"- **Judge Type**: `{judge_a}`")
    md.append(
        f"- **Overall Score**: A = **{metrics_a['overall_score']}**, B = **{metrics_b['overall_score']}** (Δ = **{round(metrics_a['overall_score'] - metrics_b['overall_score'], 4)}**)"
    )
    md.append("")

    md.append("## Paired Bootstrap Metric Differences (A - B)")
    md.append("")
    md.append("| Metric | Mean A | Mean B | Delta (A - B) | 95% CI on Delta | Stat. Sig.? |")
    md.append("|---|---|---|---|---|---|")

    metric_keys = [
        "recall_at_5",
        "hit_at_5",
        "mrr",
        "ndcg_at_10",
        "answer_correctness",
        "faithfulness",
        "citation_precision",
        "refusal_accuracy",
    ]

    for mk in metric_keys:
        vals_a = [r["metrics"][mk] for r in results_a]
        vals_b = [r["metrics"][mk] for r in results_b]

        mean_a = float(metrics_a["headline_metrics"][mk]["mean"])
        mean_b = float(metrics_b["headline_metrics"][mk]["mean"])

        delta_ci = paired_bootstrap_delta(vals_a, vals_b, n_resamples=1000, seed=42)
        ci_str = f"[{delta_ci.ci_low:+.4f}, {delta_ci.ci_high:+.4f}]"

        # Statistically significant if 0 is outside 95% CI
        sig = "Yes" if (delta_ci.ci_low > 0 or delta_ci.ci_high < 0) else "No"
        md.append(
            f"| `{mk}` | {mean_a:.4f} | {mean_b:.4f} | **{delta_ci.mean:+.4f}** | {ci_str} | {sig} |"
        )
    md.append("")

    return "\n".join(md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two RegulatorIQ evaluation runs")
    parser.add_argument("run_a", help="First run ID or path")
    parser.add_argument("run_b", help="Second run ID or path")
    args = parser.parse_args()

    try:
        report = compare_runs(args.run_a, args.run_b)
        print(report)
    except JudgeTypeMismatchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
