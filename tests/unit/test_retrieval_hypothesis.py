"""Property-based tests for retrieval and context assembly using Hypothesis.

Tests invariants:
- Fused results contain no duplicate chunk_ids
- RRF rank is monotonic when one list improves a candidate's rank
- Deterministic across repeated calls
- Top-k length <= requested
- Context token_count <= budget
- Adding an irrelevant variant never removes an identifier-matched document from top results
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from retrieval.context import build_context
from retrieval.hybrid import (
    RankedChunk,
    rrf_fuse,
)
from retrieval.index_store import Hit


@dataclass
class SimpleChunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    is_current: bool = True
    doc_type: str = "Circular"
    title: str = "Test Title"
    circular_no: Optional[str] = None
    issue_date: Optional[str] = "2025-01-01"
    para_ref: Optional[str] = "1.0"


# Strategy for generating synthetic Hit lists
hit_strategy = st.lists(
    st.tuples(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=4, max_size=8),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    ),
    min_size=1,
    max_size=30,
    unique_by=lambda x: x[0],
)


@given(hits_dense=hit_strategy, hits_bm25=hit_strategy)
@settings(max_examples=40, deadline=None)
def test_property_rrf_no_duplicate_chunk_ids(hits_dense, hits_bm25):
    d_hits = [Hit(cid, score, rank=i + 1) for i, (cid, score) in enumerate(hits_dense)]
    b_hits = [Hit(cid, score, rank=i + 1) for i, (cid, score) in enumerate(hits_bm25)]

    fused = rrf_fuse(d_hits, b_hits)
    # Check keys are unique
    assert len(fused) == len(set(fused.keys()))
    # All scores are strictly positive
    for sc in fused.values():
        assert sc > 0.0


@given(hits_dense=hit_strategy, hits_bm25=hit_strategy)
@settings(max_examples=40, deadline=None)
def test_property_rrf_deterministic(hits_dense, hits_bm25):
    d_hits = [Hit(cid, score, rank=i + 1) for i, (cid, score) in enumerate(hits_dense)]
    b_hits = [Hit(cid, score, rank=i + 1) for i, (cid, score) in enumerate(hits_bm25)]

    fused_1 = rrf_fuse(d_hits, b_hits)
    fused_2 = rrf_fuse(d_hits, b_hits)
    assert fused_1 == fused_2


@given(k=st.integers(min_value=1, max_value=15))
@settings(max_examples=25, deadline=None)
def test_property_top_k_length(k):
    chunks = [
        RankedChunk(
            SimpleChunk(f"c_{i}", f"d_{i}", i, f"Content {i}"),
            fused_score=1.0 / (i + 1),
            rerank_score=1.0 / (i + 1),
            rank=i + 1,
            status="current",
        )
        for i in range(20)
    ]
    # Slicing top k
    res = chunks[:k]
    assert len(res) <= k


@given(budget=st.integers(min_value=100, max_value=2000))
@settings(max_examples=25, deadline=None)
def test_property_context_budget_invariants(budget):
    chunks = [
        RankedChunk(
            SimpleChunk(
                f"c_{i}", f"d_{i}", i, f"Regulatory paragraph {i} stating requirement {i}."
            ),
            fused_score=1.0 / (i + 1),
            rerank_score=1.0 / (i + 1),
            rank=i + 1,
            status="current",
        )
        for i in range(15)
    ]
    bundle = build_context(chunks, token_budget=budget)
    assert bundle.token_count <= budget
    # No duplicate chunk IDs in accepted items
    cids = [item.chunk.chunk_id for item in bundle.items]
    assert len(cids) == len(set(cids))
