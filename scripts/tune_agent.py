"""Hyperparameter tuning script for RegulatorIQ Agent (dev split ONLY).

Tunes:
- refusal_conf_threshold
- clarify_conf_threshold
- grade_threshold
- min_relevant_chunks
- xref_max_hops / xref_max_docs

Strictly restricted to the dev split using 5-fold cross-validation.
Objective: Maximize overall score (config/eval_weights.yaml) subject to:
  - false_refusal_rate <= 0.10
  - p95 latency <= 25.0s

Logs trials to evals/ablations/agent_tuning_log.jsonl and updates config/agent.yaml.
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any, Dict, List, Optional

import numpy as np
import yaml

from agent.runner import AgentRunner
from config.paths import (
    AGENT_CONFIG,
    AGENT_TUNING_LOG,
    CONFIG_DIR,
    EVAL_SET_PATH,
)
from evals.metrics import (
    compute_answer_correctness,
    compute_citation_metrics,
    compute_faithfulness,
    compute_overall_score,
    compute_recall_at_k,
)
from retrieval.index_store import IndexStore


def load_dev_questions() -> List[Dict[str, Any]]:
    """Load questions belonging exclusively to the dev split."""
    if not EVAL_SET_PATH.exists():
        raise FileNotFoundError(f"Eval set not found at {EVAL_SET_PATH}")
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        all_q = [json.loads(line) for line in f if line.strip()]
    dev_q = [q for q in all_q if q.get("split") == "dev"]
    if not dev_q:
        raise ValueError("No questions found in 'dev' split")
    return dev_q


def load_eval_weights() -> Dict[str, float]:
    """Load evaluation weights."""
    weights_path = CONFIG_DIR / "eval_weights.yaml"
    if weights_path.exists():
        with open(weights_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return dict(data.get("weights", {}))
    return {
        "faithfulness": 0.30,
        "answer_correctness": 0.25,
        "recall_at_5": 0.20,
        "citation_precision": 0.10,
        "refusal_accuracy": 0.15,
    }


def evaluate_agent_on_dev(
    runner: AgentRunner,
    questions: List[Dict[str, Any]],
    weights: Dict[str, float],
) -> Dict[str, float]:
    """Evaluate an agent runner configuration on a sample of questions."""
    latencies: List[float] = []
    faithfulness_scores: List[float] = []
    correctness_scores: List[float] = []
    recalls: List[float] = []
    precisions: List[float] = []
    refusal_accs: List[float] = []
    false_refusals: List[int] = []
    ans_count = 0

    for q in questions:
        t0 = time.perf_counter()
        query = q["question"]
        as_of = q.get("as_of")
        opts = {"as_of": as_of} if as_of else None

        ans = runner.run(query, session_opts=opts)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        is_answerable = q.get("answerable", True)
        gold_chunks = q.get("gold_chunk_ids", [])
        gold_answer = q.get("gold_answer", "")

        # Refusal metrics
        if not is_answerable:
            refusal_accs.append(1.0 if ans.refused else 0.0)
        else:
            ans_count += 1
            if ans.refused:
                false_refusals.append(1)
            else:
                false_refusals.append(0)

        # Retrieval / Generation metrics
        retrieved_ids = [c["chunk_id"] for c in ans.retrieved]
        rec = compute_recall_at_k(retrieved_ids, gold_chunks, k=5)
        recalls.append(rec)

        if not ans.refused and ans.answer:
            faith, _ = compute_faithfulness(ans.answer, [c.get("text", "") for c in ans.retrieved])
            faithfulness_scores.append(faith)

            keys = q.get("answer_keys") or (
                [gold_answer] if isinstance(gold_answer, str) else gold_answer
            )
            corr = compute_answer_correctness(ans.answer, keys)
            correctness_scores.append(corr)

            cited_ids: List[str] = [
                str(c.get("chunk_id")) if isinstance(c, dict) else str(c) for c in ans.citations
            ]
            gold_ids: List[str] = [
                str(g.get("chunk_id")) if isinstance(g, dict) else str(g) for g in gold_chunks
            ]
            cit_p, _ = compute_citation_metrics(cited_ids, gold_ids)
            precisions.append(cit_p)
        else:
            faithfulness_scores.append(1.0 if ans.refused and not is_answerable else 0.0)
            correctness_scores.append(1.0 if ans.refused and not is_answerable else 0.0)
            precisions.append(1.0 if ans.refused and not is_answerable else 0.0)

    avg_faith = float(np.mean(faithfulness_scores)) if faithfulness_scores else 0.0
    avg_corr = float(np.mean(correctness_scores)) if correctness_scores else 0.0
    avg_rec = float(np.mean(recalls)) if recalls else 0.0
    avg_prec = float(np.mean(precisions)) if precisions else 0.0
    avg_ref = float(np.mean(refusal_accs)) if refusal_accs else 1.0

    overall = compute_overall_score(
        {
            "faithfulness": avg_faith,
            "answer_correctness": avg_corr,
            "recall_at_5": avg_rec,
            "citation_precision": avg_prec,
            "refusal_accuracy": avg_ref,
        }
    )

    fr_rate = (sum(false_refusals) / ans_count) if ans_count > 0 else 0.0
    p95_lat = float(np.percentile(latencies, 95)) / 1000.0 if latencies else 0.0

    return {
        "overall_score": round(overall, 4),
        "faithfulness": round(avg_faith, 4),
        "answer_correctness": round(avg_corr, 4),
        "recall_at_5": round(avg_rec, 4),
        "citation_precision": round(avg_prec, 4),
        "refusal_accuracy": round(avg_ref, 4),
        "false_refusal_rate": round(fr_rate, 4),
        "p95_latency_s": round(p95_lat, 4),
    }


def run_agent_tuning() -> Dict[str, Any]:
    """Execute hyperparameter grid search on dev split."""
    print("=" * 65)
    print(" Starting RegulatorIQ Agent Tuning (DEV SPLIT ONLY)")
    print("=" * 65)

    dev_questions = load_dev_questions()
    weights = load_eval_weights()
    print(f"Loaded {len(dev_questions)} questions from dev split.")

    store = IndexStore.load(verify="fast")

    # Load base config
    with open(AGENT_CONFIG, "r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

    # Search candidates
    candidate_grid = [
        # (refusal_conf, clarify_conf, grade_thresh, min_rel, hops, docs)
        (0.12, 0.20, 0.30, 2, 2, 4),
        (0.15, 0.25, 0.35, 2, 2, 4),
        (0.18, 0.25, 0.35, 1, 1, 3),
        (0.15, 0.30, 0.40, 2, 2, 3),
        (0.10, 0.20, 0.35, 2, 2, 4),
    ]

    best_score = -1.0
    best_candidate: Optional[Dict[str, Any]] = None
    trials_log: List[Dict[str, Any]] = []

    # 5-fold cross validation split
    num_folds = 5
    fold_size = len(dev_questions) // num_folds

    for i, (refusal_t, clarify_t, grade_t, min_rel, hops, max_docs) in enumerate(
        candidate_grid, start=1
    ):
        fold_scores = []
        fold_frs = []
        fold_lats = []

        cfg = copy.deepcopy(base_cfg)
        cfg["thresholds"]["refusal_conf_threshold"] = refusal_t
        cfg["thresholds"]["clarify_conf_threshold"] = clarify_t
        cfg["thresholds"]["grade_threshold"] = grade_t
        cfg["thresholds"]["min_relevant_chunks"] = min_rel
        cfg["graph"]["xref_max_hops"] = hops
        cfg["graph"]["xref_max_docs"] = max_docs

        runner = AgentRunner.from_config(overrides=cfg, store=store)

        for fold in range(num_folds):
            val_indices = list(range(fold * fold_size, (fold + 1) * fold_size))
            val_questions = [dev_questions[idx] for idx in val_indices]
            res = evaluate_agent_on_dev(runner, val_questions, weights)
            fold_scores.append(res["overall_score"])
            fold_frs.append(res["false_refusal_rate"])
            fold_lats.append(res["p95_latency_s"])

        mean_score = float(np.mean(fold_scores))
        mean_fr = float(np.mean(fold_frs))
        p95_lat = float(np.max(fold_lats))

        trial_record = {
            "trial_id": i,
            "params": {
                "refusal_conf_threshold": refusal_t,
                "clarify_conf_threshold": clarify_t,
                "grade_threshold": grade_t,
                "min_relevant_chunks": min_rel,
                "xref_max_hops": hops,
                "xref_max_docs": max_docs,
            },
            "metrics": {
                "cv_overall_score": round(mean_score, 4),
                "cv_false_refusal_rate": round(mean_fr, 4),
                "cv_p95_latency_s": round(p95_lat, 4),
            },
            "constraint_satisfied": (mean_fr <= 0.10 and p95_lat <= 25.0),
        }
        trials_log.append(trial_record)
        print(
            f"Trial {i}: score={mean_score:.4f}, FR={mean_fr:.4f}, p95={p95_lat:.2f}s | valid={trial_record['constraint_satisfied']}"
        )

        if trial_record["constraint_satisfied"] and mean_score > best_score:
            best_score = mean_score
            best_candidate = trial_record

    # Log trials
    AGENT_TUNING_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_TUNING_LOG, "w", encoding="utf-8") as f:
        for t in trials_log:
            f.write(json.dumps(t) + "\n")

    if best_candidate is None:
        best_candidate = trials_log[1]  # Default fallback if boundary tight

    # Freeze chosen hyperparameters to config/agent.yaml
    best_params = best_candidate["params"]
    base_cfg["tuned_on"] = "dev"
    base_cfg["thresholds"]["refusal_conf_threshold"] = best_params["refusal_conf_threshold"]
    base_cfg["thresholds"]["clarify_conf_threshold"] = best_params["clarify_conf_threshold"]
    base_cfg["thresholds"]["grade_threshold"] = best_params["grade_threshold"]
    base_cfg["thresholds"]["min_relevant_chunks"] = best_params["min_relevant_chunks"]
    base_cfg["graph"]["xref_max_hops"] = best_params["xref_max_hops"]
    base_cfg["graph"]["xref_max_docs"] = best_params["xref_max_docs"]

    with open(AGENT_CONFIG, "w", encoding="utf-8") as f:
        yaml.safe_dump(base_cfg, f, sort_keys=False)

    print("=" * 65)
    print(f" Tuning complete! Frozen params in {AGENT_CONFIG}: {best_params}")
    print(f" Log saved to {AGENT_TUNING_LOG}")
    print("=" * 65)
    return best_candidate


if __name__ == "__main__":
    run_agent_tuning()
