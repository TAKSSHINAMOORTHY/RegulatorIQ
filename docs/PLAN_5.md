# Plan: Prompt 5 of 10 - Hybrid Retrieval, RRF & Reranking

- [x] PART A: HYBRID RETRIEVAL & FUSION (retrieval/hybrid.py)
  - [x] A1. Reciprocal Rank Fusion (RRF) and weighted normalization
  - [x] A2. Circular identifier exact matching boost
  - [x] A3. Temporal validity policies
- [x] PART B: CROSS-ENCODER RERANKING (retrieval/rerank.py)
  - [x] B1. ms-marco-MiniLM-L-6-v2 cross-encoder
  - [x] B2. Calibrated confidence scoring
- [x] PART C: QUERY REWRITING (retrieval/rewrite.py)
- [x] PART D: CONTEXT DIVERSIFICATION (retrieval/context.py)
- [x] PART E: RETRIEVER INTEGRATION (retrieval/pipeline.py)
- [x] PART F: TUNING & FULL ABLATION STUDY (`make tune`, `make ablate`)
- [x] PART G: VERIFICATION AND CLAIMS (`make verify-p5`)
