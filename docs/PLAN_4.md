# Plan: Prompt 4 of 10 - Evaluation Set, Baseline RAG & Harness

- [x] PART A: EVALUATION BENCHMARK SET (evals/generate.py)
  - [x] A1. 100 questions covering lookup, temporal, multi-hop, unanswerable
  - [x] A2. Frozen train/dev/test split with integrity sha256
- [x] PART B: NAIVE BASELINE RAG PIPELINE (agent/baseline.py)
- [x] PART C: METRICS AND HARNESS (evals/metrics.py, evals/run.py)
  - [x] C1. Recall@k, nDCG@10, MRR, faithfulness, answer correctness
  - [x] C2. 95% bootstrap confidence intervals
- [x] PART D: VERIFICATION AND GATES (`make verify-p4`)
