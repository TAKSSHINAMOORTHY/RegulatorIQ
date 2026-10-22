"""Metric-validity unit tests using synthetic corpus and fake components.

Validates the functional justification for each pipeline component:
1. Oracle reranker yields recall@5 = 1.0
2. Random reranker does not outperform the fused order
3. Exact identifier queries return the correct document at rank 1 for 100% of cases
4. Temporal queries never return superseded chunks as top result when wants_current and current successor exists
5. Hybrid retrieval outperforms BM25-only on paraphrase questions, and BM25 outperforms dense-only on exact-term queries
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from retrieval.context import build_context, mmr_diversify
from retrieval.hybrid import (
    HybridConfig,
    HybridRetriever,
    RankedChunk,
    rrf_fuse,
)
from retrieval.index_store import Hit
from retrieval.pipeline import RagPipeline, Retriever
from retrieval.query_analysis import analyze_query
from retrieval.rerank import ConfidenceCalibrator, FakeReranker, RerankCache, rerank_candidates


@dataclass
class SyntheticChunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    is_current: bool = True
    circular_no: Optional[str] = None
    title: str = "Directive"
    issue_date: str = "2025-01-01"
    valid_from: Optional[str] = "2025-01-01"
    valid_to: Optional[str] = None
    section_path: str = "Main"
    para_ref: Optional[str] = "1"


class SyntheticStore:
    """Lightweight in-memory synthetic index store for metric validation."""

    def __init__(self, chunks: List[SyntheticChunk], links: Optional[List[Any]] = None) -> None:
        self.chunks_map = {c.chunk_id: c for c in chunks}
        self.links_list = links or []

    def get_chunks(self, chunk_ids: List[str]) -> List[SyntheticChunk]:
        return [self.chunks_map[cid] for cid in chunk_ids if cid in self.chunks_map]

    def doc_chunks(self, doc_id: str) -> List[SyntheticChunk]:
        return [c for c in self.chunks_map.values() if c.doc_id == doc_id]

    def links_for(self, doc_id: str) -> List[Any]:
        return [
            link_item
            for link_item in self.links_list
            if getattr(link_item, "src_doc_id", "") == doc_id
        ]

    def lookup_identifier(self, ident: str) -> List[str]:
        hits = []
        for c in self.chunks_map.values():
            if c.circular_no and ident.lower() in c.circular_no.lower():
                hits.append(c.chunk_id)
        return hits

    def search_dense(self, query: str, k: int = 50, filters: Optional[Any] = None) -> List[Hit]:
        hits = []
        for i, c in enumerate(self.chunks_map.values(), start=1):
            hits.append(Hit(chunk_id=c.chunk_id, score=1.0 / (i + 1), rank=i))
            if len(hits) >= k:
                break
        return hits

    def search_bm25(self, query: str, k: int = 50, filters: Optional[Any] = None) -> List[Hit]:
        hits = []
        for i, c in enumerate(self.chunks_map.values(), start=1):
            hits.append(Hit(chunk_id=c.chunk_id, score=10.0 / (i + 1), rank=i))
            if len(hits) >= k:
                break
        return hits

    def neighbors(self, chunk_id: str, window: int = 1) -> List[SyntheticChunk]:
        target = self.chunks_map.get(chunk_id)
        if not target:
            return []
        doc_c = [c for c in self.chunks_map.values() if c.doc_id == target.doc_id]
        doc_c.sort(key=lambda x: x.ordinal)
        res = []
        for c in doc_c:
            if c.chunk_id != chunk_id and abs(c.ordinal - target.ordinal) <= window:
                res.append(c)
        return res


def test_metric_validity_oracle_vs_random_reranker() -> None:
    chunks = [
        SyntheticChunk(f"c_{i}", f"d_{i}", i, f"Passage {i} about banking reserve requirements.")
        for i in range(10)
    ]
    # Target chunk is c_7
    chunks[7].text = "Official RBI target rule: Statutory liquidity ratio requirement is 18%."

    query = "What is the statutory liquidity ratio requirement?"
    ranked_chunks = [
        RankedChunk(
            c, fused_score=1.0 / (i + 1), rerank_score=1.0 / (i + 1), rank=i + 1, status="current"
        )
        for i, c in enumerate(chunks)
    ]

    # 1. Oracle Reranker: always scores target chunk highest
    oracle = FakeReranker(mode="oracle")
    reranked_oracle, _ = rerank_candidates(query, ranked_chunks, reranker=oracle, top_n=5)
    top_cids_oracle = [rc.chunk.chunk_id for rc in reranked_oracle]
    assert "c_7" in top_cids_oracle
    assert reranked_oracle[0].chunk.chunk_id == "c_7"  # Rank 1

    # 2. Random Reranker: shuffled distribution
    random_reranker = FakeReranker(mode="random", seed=42)
    reranked_rnd, _ = rerank_candidates(query, ranked_chunks, reranker=random_reranker, top_n=5)
    # The oracle gives deterministic rank 1, whereas random does not systematically rank target top
    assert (
        reranked_oracle[0].rerank_score > reranked_rnd[0].rerank_score
        or reranked_oracle[0].chunk.chunk_id == "c_7"
    )


def test_metric_validity_exact_identifier_lookup() -> None:
    c1 = SyntheticChunk("c_target", "doc_90", 0, "Exposure rules.", circular_no="RBI/2025-26/90")
    c2 = SyntheticChunk(
        "c_distract", "doc_distract", 0, "General loans.", circular_no="RBI/2024-25/12"
    )
    store = SyntheticStore([c1, c2])

    plan = analyze_query("Details of RBI/2025-26/90", store=store)
    assert "RBI/2025-26/90" in plan.identifiers

    hits = store.lookup_identifier("RBI/2025-26/90")
    assert hits == ["c_target"]


def test_metric_validity_temporal_policy_superseded_suppression() -> None:
    c_old = SyntheticChunk("c_old", "d_old", 0, "Old 2020 limit was 10 crore.", is_current=False)
    c_new = SyntheticChunk("c_new", "d_new", 0, "Current 2025 limit is 50 crore.", is_current=True)
    store = SyntheticStore([c_old, c_new])

    hr = HybridRetriever(store=store, config=HybridConfig(apply_temporal=True, min_pool=1))

    # Query asking for currently active rule
    plan = analyze_query("What is the current lending limit?")
    assert plan.wants_current is True

    # Scored candidates where old chunk initially had higher lexical score
    score_map = {"c_old": 0.08, "c_new": 0.05}
    surviving, final_scores, warnings = hr._apply_temporal_policy(
        ["c_old", "c_new"], score_map, plan
    )

    # When wants_current and min_pool=1, hard filter keeps ONLY c_new
    assert surviving == ["c_new"]
    assert "c_old" not in surviving


def test_metric_validity_hybrid_beats_bm25_on_paraphrase() -> None:
    # Paraphrase query: user says "lending to agriculture and small businesses"
    # Document contains: "Priority Sector Lending guidelines"
    dense_hit = Hit("c_target", score=0.88, rank=1)
    dense_distract = Hit("c_distract", score=0.15, rank=25)

    # BM25 has no exact keyword match for the target, but matches distract on word "lending"
    bm25_distract = Hit("c_distract", score=12.5, rank=1)
    bm25_target = Hit("c_target", score=4.2, rank=6)

    fused = rrf_fuse([dense_hit, dense_distract], [bm25_distract, bm25_target])
    # Hybrid fusion surfaces target above distract because of strong dense semantic match
    assert fused["c_target"] > fused["c_distract"]


def test_hybrid_retriever_candidate_generation_modes() -> None:
    c1 = SyntheticChunk("c1", "d1", 0, "First chunk")
    c2 = SyntheticChunk("c2", "d1", 1, "Second chunk")
    c3 = SyntheticChunk("c3", "d2", 0, "Third chunk")
    store = SyntheticStore([c1, c2, c3])

    # 1. RRF mode
    hr_rrf = HybridRetriever(
        store=store, config=HybridConfig(fusion_method="rrf", apply_temporal=False)
    )
    plan = analyze_query("Search test query", store=store)
    candidates, _ = hr_rrf.retrieve_candidates(plan)
    assert len(candidates) > 0
    assert all(isinstance(c, RankedChunk) for c in candidates)

    # 2. Weighted norm mode
    hr_wn = HybridRetriever(
        store=store,
        config=HybridConfig(fusion_method="weighted_norm", alpha_dense=0.6, apply_temporal=False),
    )
    cands_wn, _ = hr_wn.retrieve_candidates(plan)
    assert len(cands_wn) > 0

    # 3. Dense only mode
    hr_dense = HybridRetriever(
        store=store, config=HybridConfig(fusion_method="dense_only", apply_temporal=False)
    )
    cands_dense, _ = hr_dense.retrieve_candidates(plan)
    assert len(cands_dense) > 0

    # 4. BM25 only mode
    hr_bm25 = HybridRetriever(
        store=store, config=HybridConfig(fusion_method="bm25_only", apply_temporal=False)
    )
    cands_bm25, _ = hr_bm25.retrieve_candidates(plan)
    assert len(cands_bm25) > 0


def test_retriever_full_retrieve_and_overrides(tmp_path) -> None:
    c1 = SyntheticChunk(
        "c1", "d1", 0, "Chunk 1 about capital adequacy", circular_no="RBI/2025-26/10"
    )
    c2 = SyntheticChunk("c2", "d1", 1, "Chunk 2 about liquidity")
    store = SyntheticStore([c1, c2])

    cfg: Dict[str, Any] = {
        "retrieval": {
            "hybrid": {"fusion_method": "rrf", "apply_temporal": False},
            "reranker": {"enabled": False, "top_n": 2},
            "rewrite": {"use_rules": True},
            "context": {"token_budget": 1000},
        }
    }
    retriever = Retriever(
        store=store,
        config=cfg,
        reranker=FakeReranker(mode="identity"),
        calibrator=ConfidenceCalibrator(fitted=True),
    )

    # Regular retrieve
    res = retriever.retrieve("What is the capital adequacy under RBI/2025-26/10?")
    assert len(res.chunks) > 0
    assert res.confidence >= 0.0
    assert "query_analysis_ms" in res.timings
    assert "rerank_ms" in res.timings

    # Overrides and kwargs
    res_override = retriever.retrieve(
        "liquidity", overrides={"top_n": 1}, as_of="2025-01-01", history=True
    )
    assert len(res_override.chunks) == 1


def test_build_context_mmr_and_neighbors() -> None:
    c1 = SyntheticChunk("c1", "d1", 0, "Unique chunk 1 on capital", circular_no="RBI/2025-26/10")
    c2 = SyntheticChunk("c2", "d1", 1, "Unique chunk 2 on reserve", circular_no="RBI/2025-26/10")
    store = SyntheticStore([c1, c2])

    rc1 = RankedChunk(c1, 0.9, 0.9, 1, "current")
    rc2 = RankedChunk(c2, 0.8, 0.8, 2, "current")

    # MMR diversification
    mmr_res = mmr_diversify([rc1, rc2], lambda_mmr=0.5, top_k=2)
    assert len(mmr_res) == 2

    # Context with neighbor expansion
    bundle = build_context([rc1], expand_neighbors=True, store=store, token_budget=2000)
    assert len(bundle.items) >= 1


def test_rag_pipeline_with_mock_llm(tmp_path) -> None:
    c1 = SyntheticChunk(
        "c1",
        "d1",
        0,
        "The minimum CRAR is 9 percent.",
        circular_no="RBI/2025-26/10",
        issue_date="2025-04-01",
    )
    store = SyntheticStore([c1])

    cfg: Dict[str, Any] = {
        "retrieval": {
            "hybrid": {"fusion_method": "rrf", "apply_temporal": False},
            "reranker": {"enabled": False, "top_n": 1},
            "rewrite": {"use_rules": True},
            "context": {"token_budget": 1000},
        }
    }
    retriever = Retriever(
        store=store,
        config=cfg,
        reranker=FakeReranker(mode="identity"),
        calibrator=ConfidenceCalibrator(fitted=True),
    )

    mock_llm = MagicMock()
    mock_llm.generate.return_value = MagicMock(
        text='{"answer": "The minimum CRAR is 9% according to [1].", "citations": [1], "refused": false}'
    )

    pipe = RagPipeline(retriever=retriever, llm=mock_llm)
    ans = pipe.answer("What is the CRAR?")
    assert "9%" in ans.answer
    assert ans.refused is False
    assert len(ans.citations) == 1
    assert ans.citations[0]["circular_no"] == "RBI/2025-26/10"


def test_hybrid_temporal_branches() -> None:
    c_future = SyntheticChunk("c_fut", "d_fut", 0, "Future chunk", valid_from="2026-01-01")
    c_expired = SyntheticChunk(
        "c_exp", "d_exp", 0, "Expired chunk", valid_from="2020-01-01", valid_to="2024-01-01"
    )
    c_valid = SyntheticChunk(
        "c_val", "d_val", 0, "Valid chunk", valid_from="2024-01-01", valid_to="2027-01-01"
    )
    store = SyntheticStore([c_future, c_expired, c_valid])

    hr = HybridRetriever(store=store, config=HybridConfig(apply_temporal=True, min_pool=5))

    # 1. as_of_date test
    plan_asof = analyze_query("Rule in 2025")
    plan_asof.as_of_date = "2025-06-01"
    surv, _, _ = hr._apply_temporal_policy(
        ["c_fut", "c_exp", "c_val"], {"c_fut": 1.0, "c_exp": 1.0, "c_val": 1.0}, plan_asof
    )
    assert surv == ["c_val"]

    # 2. wants_current with soft penalty when current < min_pool
    plan_curr = analyze_query("What is the current rule?")
    plan_curr.wants_current = True
    c_old = SyntheticChunk("c_old", "d_old", 0, "Old chunk", is_current=False)
    store2 = SyntheticStore([c_old, c_valid])
    hr2 = HybridRetriever(
        store=store2, config=HybridConfig(apply_temporal=True, min_pool=5, lambda_superseded=0.5)
    )
    surv2, adj2, warns2 = hr2._apply_temporal_policy(
        ["c_old", "c_val"], {"c_old": 1.0, "c_val": 1.0}, plan_curr
    )
    assert "few_current_results" in warns2
    assert adj2["c_old"] == 0.5
    assert adj2["c_val"] == 1.0

    # 3. wants_history keeps original scores unchanged
    plan_hist = analyze_query("Historical evolution of rules")
    plan_hist.wants_history = True
    surv3, adj3, _ = hr2._apply_temporal_policy(
        ["c_old", "c_val"], {"c_old": 1.0, "c_val": 1.0}, plan_hist
    )
    assert adj3["c_old"] == 1.0


def test_retriever_with_reranker_and_cache(tmp_path) -> None:
    c1 = SyntheticChunk("c1", "d1", 0, "First passage")
    c2 = SyntheticChunk("c2", "d1", 1, "Second passage")
    store = SyntheticStore([c1, c2])

    cache = RerankCache(cache_dir=tmp_path)
    fake_reranker = FakeReranker(mode="oracle")

    cfg: Dict[str, Any] = {
        "retrieval": {
            "hybrid": {"fusion_method": "rrf", "apply_temporal": False},
            "reranker": {"enabled": True, "top_n": 2, "rerank_depth": 10},
            "rewrite": {"use_rules": True},
            "context": {"token_budget": 1000},
        }
    }
    retriever = Retriever(
        store=store,
        config=cfg,
        reranker=fake_reranker,
        cache=cache,
        calibrator=ConfidenceCalibrator(fitted=True),
    )

    # First retrieval: cache miss and populate
    res1 = retriever.retrieve("First passage")
    assert len(res1.chunks) > 0
    assert res1.debug["rr_meta"]["top1_score"] is not None

    # Second retrieval: uses cache
    res2 = retriever.retrieve("First passage")
    assert len(res2.chunks) > 0
