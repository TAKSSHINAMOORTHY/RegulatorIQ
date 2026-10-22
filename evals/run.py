"""Evaluation Runner for RegulatorIQ.

Runs an evaluation of a registered RAG system against the frozen evaluation set.
Computes retrieval and generation metrics with 95% bootstrap confidence intervals,
logs run records to evals/runs/<run_id>/, categorizes failure modes into buckets,
and produces a comprehensive Markdown report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agent.types import RagAnswer
from config.paths import (
    EVAL_SET_META,
    EVAL_SET_PATH,
    RUNS_DIR,
)
from evals.metrics import (
    bootstrap_ci,
    compute_all_gold_found,
    compute_answer_correctness,
    compute_citation_metrics,
    compute_doc_recall_at_k,
    compute_faithfulness,
    compute_hit_at_k,
    compute_mrr,
    compute_ndcg_at_10,
    compute_overall_score,
    compute_recall_at_k,
)
from evals.systems import get_system
from retrieval.index_store import IndexStore


def get_git_commit() -> str:
    """Get current git short commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def evaluate_sample(
    question_item: Dict[str, Any],
    rag_answer: RagAnswer,
    judge_type: str = "lexical_support",
) -> Dict[str, Any]:
    """Compute all sample-level metrics for a single question-answer pair."""
    q_type = question_item.get("type", "unknown")
    expected_beh = question_item.get("expected_behavior", "answer")
    gold_chunks = question_item.get("gold_chunk_ids", [])
    gold_docs = question_item.get("gold_doc_ids", [])
    answer_keys = question_item.get("answer_keys", [])

    retrieved = rag_answer.retrieved
    ret_chunk_ids = [r.get("chunk_id", "") for r in retrieved]
    ret_doc_ids = [r.get("doc_id", "") for r in retrieved]

    # 1. Retrieval Metrics
    rec_at_1 = compute_recall_at_k(ret_chunk_ids, gold_chunks, 1)
    rec_at_3 = compute_recall_at_k(ret_chunk_ids, gold_chunks, 3)
    rec_at_5 = compute_recall_at_k(ret_chunk_ids, gold_chunks, 5)
    rec_at_10 = compute_recall_at_k(ret_chunk_ids, gold_chunks, 10)
    rec_at_20 = compute_recall_at_k(ret_chunk_ids, gold_chunks, 20)

    hit_at_1 = compute_hit_at_k(ret_chunk_ids, gold_chunks, 1)
    hit_at_5 = compute_hit_at_k(ret_chunk_ids, gold_chunks, 5)
    hit_at_20 = compute_hit_at_k(ret_chunk_ids, gold_chunks, 20)

    mrr = compute_mrr(ret_chunk_ids, gold_chunks)
    ndcg_10 = compute_ndcg_at_10(ret_chunk_ids, gold_chunks)
    doc_rec_5 = compute_doc_recall_at_k(ret_doc_ids, gold_docs, 5)
    all_gold_found = compute_all_gold_found(ret_doc_ids, gold_docs, 5)

    gold_in_context = 1.0 if any(cid in set(gold_chunks) for cid in ret_chunk_ids[:5]) else 0.0

    # 2. Generation Metrics
    ans_text = rag_answer.answer
    refused = rag_answer.refused

    if expected_beh == "refuse":
        refusal_acc = 1.0 if refused else 0.0
        false_refusal = 0.0
        hallucination_rate = 1.0 if not refused else 0.0
        ans_correct = 1.0 if refused else 0.0
        faith_val = 1.0 if refused else 0.0
        claims_verdicts = []
    else:
        refusal_acc = 0.0
        false_refusal = 1.0 if refused else 0.0
        hallucination_rate = 0.0
        if refused:
            ans_correct = 0.0
            faith_val = 0.0
            claims_verdicts = []
        else:
            ans_correct = compute_answer_correctness(ans_text, answer_keys)
            cited_texts = [r.get("text", "") for r in retrieved[:3]]
            faith_val, claims_verdicts = compute_faithfulness(
                ans_text,
                cited_texts,
                judge_type=judge_type,
            )

    # 3. Citations
    cited_ids = [c.get("chunk_id") for c in rag_answer.citations]
    cit_prec, cit_rec = compute_citation_metrics(cited_ids, gold_chunks)

    # 4. Temporal accuracy
    temporal_acc = 1.0
    if question_item.get("requires_current", False):
        if refused:
            temporal_acc = 0.0
        else:
            temporal_acc = ans_correct

    return {
        "qid": question_item["qid"],
        "type": q_type,
        "split": question_item.get("split", "dev"),
        "expected_behavior": expected_beh,
        "refused": refused,
        "recall_at_1": rec_at_1,
        "recall_at_3": rec_at_3,
        "recall_at_5": rec_at_5,
        "recall_at_10": rec_at_10,
        "recall_at_20": rec_at_20,
        "hit_at_1": hit_at_1,
        "hit_at_5": hit_at_5,
        "hit_at_20": hit_at_20,
        "mrr": mrr,
        "ndcg_at_10": ndcg_10,
        "doc_recall_at_5": doc_rec_5,
        "all_gold_found": all_gold_found,
        "gold_in_context": gold_in_context,
        "answer_correctness": ans_correct,
        "faithfulness": faith_val,
        "citation_precision": cit_prec,
        "citation_recall": cit_rec,
        "refusal_accuracy": refusal_acc,
        "false_refusal_rate": false_refusal,
        "hallucination_rate": hallucination_rate,
        "temporal_accuracy": temporal_acc,
        "latency_total_s": rag_answer.timings.get("total_s", 0.0),
        "tokens_in": rag_answer.usage.get("in", 0),
        "tokens_out": rag_answer.usage.get("out", 0),
        "claims_verdicts": claims_verdicts,
    }


def categorize_failure(
    sample: Dict[str, Any], q_item: Dict[str, Any], ans: RagAnswer
) -> Optional[str]:
    """Bucket errors into failure modes."""
    exp = q_item.get("expected_behavior", "answer")

    if exp == "refuse" and not ans.refused:
        return "under_refusal"
    if exp == "answer" and ans.refused:
        return "over_refusal"
    if exp == "answer" and sample["hit_at_5"] == 0.0 and sample["hit_at_20"] == 1.0:
        return "wrong_chunk_ranked_low"
    if exp == "answer" and sample["hit_at_5"] == 0.0:
        return "retrieval_miss"
    if exp == "answer" and sample["faithfulness"] < 0.6:
        return "generation_unfaithful"
    if q_item.get("requires_current", False) and sample["temporal_accuracy"] < 0.5:
        return "temporal_error"
    if any(c.get("error") for c in ans.citations) or (
        sample["citation_precision"] == 0.0 and len(ans.citations) > 0
    ):
        return "citation_error"
    return None


def run_evaluation(
    system_name: str = "baseline",
    split: str = "all",
    eval_set_path: Path = EVAL_SET_PATH,
    judge_type: str = "lexical_support",
    seed: int = 42,
    save_run: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """Run full evaluation suite over specified split."""
    if not eval_set_path.exists():
        raise FileNotFoundError(
            f"Evaluation set not found at {eval_set_path}. Run `make eval-gen` first."
        )

    # Read questions
    with open(eval_set_path, "r", encoding="utf-8") as f:
        all_questions = [json.loads(line) for line in f if line.strip()]

    if split != "all":
        questions = [q for q in all_questions if q.get("split") == split]
    else:
        questions = all_questions

    if not questions:
        raise ValueError(f"No questions found for split '{split}'")

    # Read meta
    eval_meta = {}
    if EVAL_SET_META.exists():
        with open(EVAL_SET_META, "r", encoding="utf-8") as f:
            eval_meta = json.load(f)

    eval_sha = eval_meta.get("sha256", hashlib.sha256(eval_set_path.read_bytes()).hexdigest())

    # Load system
    store = IndexStore.load(verify="fast")
    system = get_system(system_name, index_store=store)

    utc_now = datetime.now(timezone.utc)
    ts_str = utc_now.strftime("%Y%m%d_%H%M%S")
    ns_suffix = time.perf_counter_ns() % 1_000_000
    cfg_raw = f"{system_name}:{split}:{judge_type}:{eval_sha[:8]}:{ts_str}_{ns_suffix}".encode(
        "utf-8"
    )
    cfg_hash = hashlib.sha256(cfg_raw).hexdigest()[:8]
    run_id = f"{ts_str}_{cfg_hash}"

    results = []
    run_logs = []
    failure_buckets: Dict[str, List[Dict[str, Any]]] = {
        "retrieval_miss": [],
        "wrong_chunk_ranked_low": [],
        "generation_unfaithful": [],
        "over_refusal": [],
        "under_refusal": [],
        "temporal_error": [],
        "citation_error": [],
    }

    t0 = time.perf_counter()
    for q_item in questions:
        q_text = q_item["question"]
        rag_ans: RagAnswer = system.answer(q_text)

        eval_res = evaluate_sample(q_item, rag_ans, judge_type=judge_type)
        results.append(eval_res)

        # Failure bucketing
        fail_mode = categorize_failure(eval_res, q_item, rag_ans)
        if fail_mode and fail_mode in failure_buckets:
            if len(failure_buckets[fail_mode]) < 5:
                failure_buckets[fail_mode].append(
                    {
                        "qid": q_item["qid"],
                        "question": q_text,
                        "expected_answer": q_item.get("gold_answer", ""),
                        "system_answer": rag_ans.answer,
                        "refused": rag_ans.refused,
                    }
                )

        run_logs.append(
            {
                "qid": q_item["qid"],
                "question": q_text,
                "answer": rag_ans.answer,
                "citations": rag_ans.citations,
                "refused": rag_ans.refused,
                "retrieved": rag_ans.retrieved,
                "timings": rag_ans.timings,
                "usage": rag_ans.usage,
                "metrics": eval_res,
            }
        )

    duration_s = time.perf_counter() - t0

    # Aggregate metrics with Bootstrap 95% CI
    metric_keys = [
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "recall_at_10",
        "recall_at_20",
        "hit_at_1",
        "hit_at_5",
        "hit_at_20",
        "mrr",
        "ndcg_at_10",
        "doc_recall_at_5",
        "all_gold_found",
        "gold_in_context",
        "answer_correctness",
        "faithfulness",
        "citation_precision",
        "citation_recall",
        "refusal_accuracy",
        "false_refusal_rate",
        "hallucination_rate",
        "temporal_accuracy",
    ]

    headline_metrics = {}
    for mk in metric_keys:
        vals = [r[mk] for r in results]
        ci_res = bootstrap_ci(vals, n_resamples=1000, seed=seed)
        d = ci_res.to_dict()
        d["judge_type"] = judge_type if mk in ("faithfulness", "answer_relevance") else "exact"
        headline_metrics[mk] = d

    # Overall Score
    means_dict = {k: headline_metrics[k]["mean"] for k in headline_metrics}
    overall_score = compute_overall_score(means_dict)

    # Breakdown by type
    per_type_metrics = {}
    for q_type in ["exact_lookup", "temporal", "multi_hop", "semantic_paraphrase", "unanswerable"]:
        sub_res = [r for r in results if r["type"] == q_type]
        if sub_res:
            per_type_metrics[q_type] = {
                "count": len(sub_res),
                "recall_at_5": round(float(np.mean([r["recall_at_5"] for r in sub_res])), 4),
                "mrr": round(float(np.mean([r["mrr"] for r in sub_res])), 4),
                "answer_correctness": round(
                    float(np.mean([r["answer_correctness"] for r in sub_res])), 4
                ),
                "faithfulness": round(float(np.mean([r["faithfulness"] for r in sub_res])), 4),
                "citation_precision": round(
                    float(np.mean([r["citation_precision"] for r in sub_res])), 4
                ),
                "refusal_accuracy": round(
                    float(np.mean([r["refusal_accuracy"] for r in sub_res])), 4
                ),
            }

    # Timing and tokens
    p50_latency = round(float(np.percentile([r["latency_total_s"] for r in results], 50)), 3)
    p95_latency = round(float(np.percentile([r["latency_total_s"] for r in results], 95)), 3)
    total_tokens_in = sum(r["tokens_in"] for r in results)
    total_tokens_out = sum(r["tokens_out"] for r in results)

    # Build run payload
    run_config = {
        "run_id": run_id,
        "timestamp_utc": utc_now.isoformat(),
        "system_name": system_name,
        "split": split,
        "sample_count": len(results),
        "index_version": store.version,
        "eval_set_path": str(eval_set_path),
        "eval_set_sha256": eval_sha,
        "llm_provider": system.llm.provider.name if hasattr(system, "llm") else "extractive",
        "llm_model": system.llm.provider.model if hasattr(system, "llm") else "none",
        "judge_type": judge_type,
        "git_commit": get_git_commit(),
        "duration_seconds": round(duration_s, 2),
    }

    metrics_payload = {
        "run_config": run_config,
        "overall_score": overall_score,
        "headline_metrics": headline_metrics,
        "per_type_metrics": per_type_metrics,
        "latency": {"p50_s": p50_latency, "p95_s": p95_latency},
        "tokens": {"total_in": total_tokens_in, "total_out": total_tokens_out},
        "failure_counts": {k: len(v) for k, v in failure_buckets.items()},
    }

    # Save to disk
    if save_run:
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        with open(run_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(run_config, f, indent=2)

        with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics_payload, f, indent=2)

        with open(run_dir / "results.jsonl", "w", encoding="utf-8") as f:
            for log in run_logs:
                f.write(json.dumps(log, ensure_ascii=False) + "\n")

        # Generate report.md
        report_md = _render_markdown_report(metrics_payload, failure_buckets)
        with open(run_dir / "report.md", "w", encoding="utf-8") as f:
            f.write(report_md)

    return run_id, metrics_payload


def _render_markdown_report(
    metrics_payload: Dict[str, Any], failure_buckets: Dict[str, List[Dict[str, Any]]]
) -> str:
    """Generate Markdown report for evaluation run."""
    cfg = metrics_payload["run_config"]
    hl = metrics_payload["headline_metrics"]
    pt = metrics_payload["per_type_metrics"]

    md = []
    md.append(f"# RegulatorIQ Evaluation Report: Run `{cfg['run_id']}`")
    md.append("")
    md.append(f"- **System**: `{cfg['system_name']}`")
    md.append(f"- **Split**: `{cfg['split']}` ({cfg['sample_count']} samples)")
    md.append(f"- **LLM Provider**: `{cfg['llm_provider']}` ({cfg['llm_model']})")
    md.append(f"- **Judge Type**: `{cfg['judge_type']}`")
    md.append(f"- **Overall Weighted Score**: **{metrics_payload['overall_score']}**")
    md.append(
        f"- **Duration**: {cfg['duration_seconds']}s (p50: {metrics_payload['latency']['p50_s']}s, p95: {metrics_payload['latency']['p95_s']}s)"
    )
    md.append("")

    md.append("## Headline Metrics (with 95% Bootstrap Confidence Intervals)")
    md.append("")
    md.append("| Metric | Mean | 95% CI | Half-Width | Judge Type |")
    md.append("|---|---|---|---|---|")
    for k, v in hl.items():
        ci_str = f"[{v['ci_low']:.4f}, {v['ci_high']:.4f}]"
        md.append(
            f"| `{k}` | **{v['mean']:.4f}** | {ci_str} | ±{v['ci_half_width']:.4f} | `{v['judge_type']}` |"
        )
    md.append("")

    md.append("## Breakdown by Question Type")
    md.append("")
    md.append(
        "| Type | Count | Recall@5 | MRR | Correctness | Faithfulness | Citation Prec | Refusal Acc |"
    )
    md.append("|---|---|---|---|---|---|---|---|")
    for q_type, m in pt.items():
        md.append(
            f"| `{q_type}` | {m['count']} | {m['recall_at_5']:.4f} | {m['mrr']:.4f} | "
            f"{m['answer_correctness']:.4f} | {m['faithfulness']:.4f} | {m['citation_precision']:.4f} | {m['refusal_accuracy']:.4f} |"
        )
    md.append("")

    md.append("## Failure Bucket Analysis")
    md.append("")
    for mode, samples in failure_buckets.items():
        count = len(samples)
        md.append(f"### {mode.replace('_', ' ').title()} ({count} examples)")
        if not samples:
            md.append("*(No occurrences recorded)*\n")
            continue
        for s in samples:
            md.append(f"- **QID**: `{s['qid']}`")
            md.append(f"  - **Question**: {s['question']}")
            md.append(f"  - **Expected**: {s['expected_answer']}")
            md.append(f"  - **Answer**: {s['system_answer']}")
            md.append(f"  - **Refused**: `{s['refused']}`")
        md.append("")

    md.append("## Plain-Language Interpretation")
    md.append(
        "This baseline RAG uses dense similarity retrieval (top-5) with deterministic extractive sentence answering. "
    )
    md.append(
        "Retrieval recall@5 measures what fraction of authoritative regulatory chunks were found. "
    )
    md.append(
        "Faithfulness measures whether generated statements are entailed by the cited source text without hallucination. "
    )
    md.append(
        "Refusal accuracy confirms appropriate rejection of queries outside RBI remit or absent from the indexed corpus."
    )
    md.append("")

    return "\n".join(md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RegulatorIQ RAG Evaluation")
    parser.add_argument("--system", default="baseline", help="Registered system name")
    parser.add_argument(
        "--split", default="all", choices=["dev", "test", "all"], help="Evaluation split"
    )
    parser.add_argument(
        "--judge-type", default="lexical_support", help="Judge type for faithfulness"
    )
    args = parser.parse_args()

    run_id, payload = run_evaluation(
        system_name=args.system, split=args.split, judge_type=args.judge_type
    )
    print(f"Evaluation complete. Run ID: {run_id}")
    print(f"Overall Score: {payload['overall_score']}")
