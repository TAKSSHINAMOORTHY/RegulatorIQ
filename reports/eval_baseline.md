# RegulatorIQ Baseline Evaluation Report (Phase 4)

> [!IMPORTANT]
> **Provider & Judge Transparency Notice:**
> - **LLM Provider**: `extractive` (`bm25-sentence-extractor`). This run represents a deterministic extractive fallback baseline without generative model hallucination.
> - **Faithfulness Judge**: `lexical_support` (flagged as `proxy`: content-word overlap + number match).
> - **Relevance Judge**: cosine similarity with index embedder (`proxy`).

---

## 1. Executive Summary

This evaluation establishes the empirical reference benchmark for RegulatorIQ using an intentionally naive baseline RAG pipeline:
- **Retrieval**: BGE-small-en-v1.5 dense vector similarity search ($k=5$), no lexical BM25, no cross-encoder reranking, no metadata filters.
- **Generation**: Extractive sentence selection with citation attribution.
- **Evaluation Dataset**: `eval_set.v1.jsonl` (100 ground-truth questions grounded in official RBI corpus, machine-verified, frozen with sha256).
- **Test Split Headline Performance**: Overall Weighted Score = **0.1952**, Recall@5 = **0.5422**, Hit@5 = **0.7750**, MRR = **0.5967**, Document Recall@5 = **0.8375**.

---

## 2. Test Split Headline Metrics (with 95% Bootstrap Confidence Intervals)

Metrics computed over the frozen `test` partition ($N=40$) using 1,000 seeded bootstrap resamples:

| Metric | Mean | 95% Bootstrap CI | CI Half-Width | Judge Type | Description |
|---|---|---|---|---|---|
| `recall_at_1` | 0.2235 | [0.1310, 0.3202] | ±0.0946 | Exact | Gold chunk retrieved at rank 1 |
| `recall_at_3` | 0.4060 | [0.2967, 0.5214] | ±0.1124 | Exact | Gold chunk retrieved in top 3 |
| `recall_at_5` | **0.5422** | [0.4269, 0.6556] | ±0.1144 | Exact | Gold chunk retrieved in top 5 context |
| `hit_at_1` | 0.5000 | [0.3250, 0.6500] | ±0.1625 | Exact | At least one gold chunk at rank 1 |
| `hit_at_5` | **0.7750** | [0.6500, 0.9000] | ±0.1250 | Exact | At least one gold chunk in top 5 |
| `mrr` | **0.5967** | [0.4612, 0.7288] | ±0.1338 | Exact | Mean Reciprocal Rank of first gold chunk |
| `ndcg_at_10` | 0.5258 | [0.4082, 0.6450] | ±0.1184 | Exact | Normalized Discounted Cumulative Gain |
| `doc_recall_at_5` | **0.8375** | [0.7250, 0.9375] | ±0.1063 | Exact | Correct document found in top 5 |
| `all_gold_found` | 0.8000 | [0.6750, 0.9000] | ±0.1125 | Exact | All required multi-hop documents found |
| `answer_correctness`| 0.1833 | [0.1083, 0.2625] | ±0.0771 | Exact | Date/number-aware key containment |
| `faithfulness` | 0.0031 | [0.0000, 0.0094] | ±0.0047 | Proxy | Entailment against cited chunks |
| `citation_precision`| 0.4000 | [0.2500, 0.5500] | ±0.1500 | Exact | Cited chunks matching gold chunks |
| `temporal_accuracy` | 0.2833 | [0.1708, 0.4042] | ±0.1167 | Exact | Accurate temporal adherence |
| `overall_score` | **0.1952** | — | — | Weighted | Combined score (weights in eval_weights.yaml) |

---

## 3. Performance Breakdown by Question Type

| Question Type | Sample Count | Recall@5 | Hit@5 | MRR | Correctness | Faithfulness | Citation Prec |
|---|---|---|---|---|---|---|---|
| `exact_lookup` | 10 | 0.6445 | 0.9000 | 0.6833 | 0.1000 | 0.0125 | 0.5000 |
| `temporal` | 10 | 0.6048 | 0.9000 | 0.7000 | 0.2833 | 0.0000 | 0.5000 |
| `multi_hop` | 8 | 0.5292 | 0.8750 | 0.6771 | 0.1250 | 0.0000 | 0.3750 |
| `semantic_paraphrase` | 8 | 0.3542 | 0.6250 | 0.4021 | 0.1875 | 0.0000 | 0.2500 |
| `unanswerable` | 4 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 |

---

## 4. Failure Mode Analysis

The evaluation suite automatically categorized system errors into predefined buckets:

1. **Retrieval Misses (`retrieval_miss`)**:
   - Occurs on complex semantic paraphrases where query terms have zero lexical overlap with technical RBI documents.
   - Example (`q_paraphrase_004`): *"How does leverage expansion among major artificial intelligence companies present potential vulnerabilities to broader economic stability?"* (Gold chunk ranked > 5 due to lack of dense semantic tuning).
2. **Multi-Hop Partial Coverage (`wrong_chunk_ranked_low`)**:
   - Occurs when comparing two distinct circulars; naive dense retrieval fetches chunks from doc A into top-5 but relegates doc B to ranks 6–10.
   - Example (`q_multihop_007`): Comparing 364-Day T-Bills with VRR auctions.
3. **Extractive Limitation on Abstract Queries**:
   - Extractive selection selects individual verbatim sentences rather than synthesizing multi-hop comparative statements.

---

## 5. What These Numbers Mean

- **Dense Retrieval Works Well for Known Entities**: The baseline achieves **77.5% Hit@5** and **83.8% Document Recall@5**, showing that the BGE-small-en-v1.5 embeddings and FAISS index accurately map regulatory questions to relevant RBI documents.
- **Hybrid Search & Reranking Are Essential**: Pure dense retrieval struggles with subtle semantic paraphrases and complex multi-hop comparisons (Phase 5 hybrid search with BM25 Reciprocal Rank Fusion + cross-encoder reranking will address this directly).
- **Generative Synthesis vs Extractive**: Generative synthesis (Phase 6 agentic workflow) is needed to reformulate multi-chunk findings into cohesive regulatory answers with strict claim verification.

---

## 6. Regression Gating

These test baseline metrics are frozen into `evals/baselines/baseline.json` and enforce CI quality gates in `evals/thresholds.yaml`. All subsequent phases (Phase 5 Hybrid, Phase 6 Agentic RAG) must pass `make eval-gate SYSTEM=<name>` without regressing beyond baseline minus 1.0× CI tolerance.
