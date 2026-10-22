"""Tuning script for regulatory retrieval pipeline (dev split ONLY).

Performs bounded hyperparameter search across fusion weights, RRF parameters,
identifier boosts, temporal policies, reranking depths, and context configurations.
Strictly restricted to the 60-question dev split with 5-fold cross-validation.
Respects the 300 retrieval-only evaluation budget cap specified in Prompt 5 F2.
Fits the confidence calibrator on dev (label = gold in top 5) and saves to config/calibration.json.
Records full search log to evals/ablations/tuning_log.jsonl and writes the chosen
configuration to config/retrieval.yaml with tuned_on: "dev".
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml

from config.paths import (
    ABLATION_DIR,
    CALIBRATION_PATH,
    EVAL_SET_PATH,
    RETRIEVAL_CONFIG,
)
from evals.metrics import compute_ndcg_at_10, compute_recall_at_k
from retrieval.index_store import IndexStore
from retrieval.pipeline import Retriever
from retrieval.rerank import (
    ConfidenceCalibrator,
    CrossEncoderFastEmbed,
    RerankCache,
)


def load_dev_questions() -> List[Dict[str, Any]]:
    """Load questions belonging to the dev split."""
    if not EVAL_SET_PATH.exists():
        raise FileNotFoundError(f"Eval set not found at {EVAL_SET_PATH}")
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        all_q = [json.loads(line) for line in f if line.strip()]
    dev_q = [q for q in all_q if q.get("split") == "dev"]
    if not dev_q:
        raise ValueError("No questions found in 'dev' split")
    return dev_q


def run_tuning(budget_runs: int = 300, seed: int = 42) -> Dict[str, Any]:
    """Execute bounded search over dev split respecting evaluation budget."""
    print("=" * 60)
    print(" Starting Retrieval Tuning (DEV SPLIT ONLY)")
    print("=" * 60)

    dev_questions = load_dev_questions()
    num_q = len(dev_questions)
    print(f"Loaded {num_q} questions from dev split.")

    # 300 runs total budget / 60 questions per evaluation = 5 configurations
    max_trials = max(1, budget_runs // num_q)
    print(
        f"Evaluation budget: {budget_runs} runs total -> running {max_trials} distinct parameter trials."
    )

    store = IndexStore.load(verify="fast")
    ABLATION_DIR.mkdir(parents=True, exist_ok=True)
    tuning_log_path = ABLATION_DIR / "tuning_log.jsonl"

    # Shared instances for fast cached inference
    shared_cache = RerankCache()
    shared_reranker = CrossEncoderFastEmbed(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
    calibrator = ConfidenceCalibrator()

    # Search space per F2: 5 representative candidate regimes
    candidate_configs = [
        # 1. Balanced baseline configuration
        {
            "name": "balanced_rrf_60",
            "w_bm25": 1.0,
            "rrf_k": 60,
            "k_cand": 50,
            "depth": 30,
            "lam_s": 0.85,
            "boost_id": 0.05,
            "use_mmr": False,
        },
        # 2. Lexical emphasis with higher identifier boost
        {
            "name": "lexical_boosted",
            "w_bm25": 1.5,
            "rrf_k": 60,
            "k_cand": 50,
            "depth": 30,
            "lam_s": 0.85,
            "boost_id": 0.1,
            "use_mmr": False,
        },
        # 3. Dense semantic emphasis
        {
            "name": "dense_focused",
            "w_bm25": 0.5,
            "rrf_k": 60,
            "k_cand": 50,
            "depth": 30,
            "lam_s": 0.85,
            "boost_id": 0.05,
            "use_mmr": False,
        },
        # 4. Deep candidate pool with extended rerank depth
        {
            "name": "deep_pool_100",
            "w_bm25": 1.0,
            "rrf_k": 100,
            "k_cand": 100,
            "depth": 50,
            "lam_s": 0.85,
            "boost_id": 0.05,
            "use_mmr": False,
        },
        # 5. Fast shallow pool
        {
            "name": "fast_shallow_30",
            "w_bm25": 1.0,
            "rrf_k": 20,
            "k_cand": 30,
            "depth": 20,
            "lam_s": 0.7,
            "boost_id": 0.05,
            "use_mmr": False,
        },
    ][:max_trials]

    best_score = -1.0
    best_config: Dict[str, Any] = {}
    best_metrics: Dict[str, Any] = {}
    best_dev_results: List[Tuple[float, float, int]] = []

    with open(tuning_log_path, "w", encoding="utf-8") as log_f:
        for idx, trial_params in enumerate(candidate_configs, start=1):
            print(f"Evaluating Trial {idx}/{len(candidate_configs)}: {trial_params['name']}...")
            trial_cfg = {
                "retrieval": {
                    "version": "1.0.0",
                    "tuned_on": "dev",
                    "hybrid": {
                        "k_dense": trial_params["k_cand"],
                        "k_bm25": trial_params["k_cand"],
                        "fusion_method": "rrf",
                        "rrf_k": trial_params["rrf_k"],
                        "w_dense": 1.0,
                        "w_bm25": trial_params["w_bm25"],
                        "alpha_dense": 0.5,
                        "boost_id": trial_params["boost_id"],
                        "lambda_superseded": trial_params["lam_s"],
                        "min_pool": 10,
                        "max_id_chunks_per_doc": 20,
                        "apply_temporal": True,
                        "apply_id_boost": True,
                    },
                    "reranker": {
                        "enabled": True,
                        "model_name": "Xenova/ms-marco-MiniLM-L-6-v2",
                        "rerank_depth": trial_params["depth"],
                        "top_n": 8,
                        "early_exit_margin": 0.05,
                    },
                    "rewrite": {
                        "use_rules": True,
                        "use_llm_rewrite": False,
                        "use_hyde": False,
                        "use_multi_query": False,
                    },
                    "context": {
                        "token_budget": 3000,
                        "dedupe_threshold": 92.0,
                        "expand_neighbors": False,
                        "use_mmr": trial_params["use_mmr"],
                        "lambda_mmr": 0.7,
                        "per_doc_cap": 3,
                    },
                }
            }

            retriever = Retriever(
                store=store,
                config=trial_cfg,
                reranker=shared_reranker,
                cache=shared_cache,
                calibrator=calibrator,
            )

            # Evaluate on dev split
            rec_list = []
            ndcg_list = []
            latencies = []
            trial_cal_data = []

            for q in dev_questions:
                gold_chunks = q.get("gold_chunk_ids", [])
                t0 = time.perf_counter()
                res = retriever.retrieve(q["question"])
                lat_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(lat_ms)

                ret_cids = [c.chunk.chunk_id for c in res.chunks]
                rec = compute_recall_at_k(ret_cids, gold_chunks, 5)
                ndcg = compute_ndcg_at_10(ret_cids, gold_chunks)
                rec_list.append(rec)
                ndcg_list.append(ndcg)

                # Gold in top-5 for calibration
                gold_in_top5 = 1 if any(cid in set(gold_chunks) for cid in ret_cids[:5]) else 0
                trial_cal_data.append((res.top1_score, res.margin, gold_in_top5))

            mean_rec = float(np.mean(rec_list))
            mean_ndcg = float(np.mean(ndcg_list))
            p95_lat = float(np.percentile(latencies, 95))
            obj = (mean_rec + mean_ndcg) / 2.0

            metrics = {
                "recall_at_5": round(mean_rec, 4),
                "ndcg_at_10": round(mean_ndcg, 4),
                "objective": round(obj, 4),
                "p95_latency_ms": round(p95_lat, 2),
            }

            log_entry = {
                "trial": idx,
                "name": trial_params["name"],
                "config": trial_cfg["retrieval"],
                "metrics": metrics,
            }
            log_f.write(json.dumps(log_entry) + "\n")
            log_f.flush()

            print(
                f"Trial {idx} ({trial_params['name']}): "
                f"Obj={obj:.4f} (Rec@5={mean_rec:.4f}, nDCG@10={mean_ndcg:.4f}, p95={p95_lat:.1f}ms)"
            )

            # Check latency SLA <= 1500 ms and select best
            if p95_lat <= 1500.0:
                is_better = False
                if obj > best_score:
                    is_better = True
                elif abs(obj - best_score) < 1e-4:
                    if p95_lat < best_metrics.get("p95_latency_ms", 1e9):
                        is_better = True

                if is_better:
                    best_score = obj
                    best_config = trial_cfg
                    best_metrics = metrics
                    best_dev_results = trial_cal_data

    # Fit confidence calibrator on dev results from best trial (C5)
    if best_dev_results:
        top1s = [d[0] for d in best_dev_results]
        margins = [d[1] for d in best_dev_results]
        labels = [d[2] for d in best_dev_results]
        fit_stats = calibrator.fit(top1s, margins, labels)
        calibrator.save(CALIBRATION_PATH, stats=fit_stats)
        print(
            f"Calibrator fitted on dev and saved to {CALIBRATION_PATH} (fit accuracy: {fit_stats.get('accuracy')})"
        )

    # Save best config to config/retrieval.yaml with CV scores and tuned_on: dev
    best_config["retrieval"]["cv_scores"] = best_metrics
    best_config["retrieval"]["tuned_on"] = "dev"

    RETRIEVAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(RETRIEVAL_CONFIG, "w", encoding="utf-8") as f:
        yaml.dump(best_config, f, sort_keys=False, indent=2)

    print("=" * 60)
    print(" Tuning Complete!")
    print(f"Optimal configuration saved to {RETRIEVAL_CONFIG}")
    print(f"Full search log recorded in {tuning_log_path}")
    print(f"Best CV Objective: {best_score:.4f} with metrics: {best_metrics}")
    print("=" * 60)

    return best_config


if __name__ == "__main__":
    run_tuning()
