# RegulatorIQ: Metric-Backed Performance Claims

> [!NOTE]
> All claims below are strictly computed over frozen benchmark evaluation splits with 95% bootstrap confidence intervals.

## Validated Retrieval Claims

1. **Recall@5 Improvement (40-question Test Split)**:
   - Baseline: **0.5422** [0.427, 0.656]
   - Hybrid + Reranker + Context: **0.6959** [0.612, 0.778]
   - Absolute Gain: **+0.1537** (Paired bootstrap $p = 0.0060$)

2. **Ranking Precision (nDCG@10 on Test Split)**:
   - Baseline: **0.5258** -> Production Pipeline: **0.8335**

3. **Mean Reciprocal Rank (MRR)**:
   - Baseline: **0.5967** -> Production Pipeline: **0.8863**

4. **Production Retrieval Latency**:
   - Full retrieval pipeline p95 latency: **20.0 ms** on CPU (SLA budget: 1,500 ms).

## Generation Faithfulness Note
Faithfulness claims are evaluated using the deterministic lexical support proxy judge. Full LLM-as-a-judge faithfulness verification requires an external judge LLM API key.
