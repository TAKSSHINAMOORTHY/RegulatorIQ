"""Integration tests for Phase 5 ablation study and retrieval pipeline."""

from __future__ import annotations

from evals.systems import list_systems
from retrieval.index_store import IndexStore
from retrieval.pipeline import Retriever


def test_registered_systems_exist() -> None:
    available = set(list_systems())
    expected = {
        "baseline",
        "bm25_only",
        "dense_only",
        "hybrid_rrf",
        "hybrid_rrf_id",
        "hybrid_rrf_id_temporal",
        "hybrid_rerank",
        "hybrid_rerank_rewrite",
        "hybrid_rerank_context",
    }
    assert expected.issubset(available), f"Missing systems: {expected - available}"


def test_retriever_pipeline_end_to_end() -> None:
    store = IndexStore.load(verify="fast")
    retriever = Retriever.from_config(store=store)

    q = "What is the exposure limit under RBI guidelines for commercial banks?"
    res = retriever.retrieve(q)

    assert len(res.chunks) > 0
    assert 0.0 <= res.confidence <= 1.0
    assert res.top1_score != 0.0
    assert "total_ms" in res.timings
    assert res.timings["total_ms"] > 0.0
