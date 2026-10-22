"""Registry for all RAG and retrieval systems evaluated by RegulatorIQ.

Defines exact Prompt 5 ablation systems:
1. baseline (Prompt 4 naive baseline, untouched)
2. bm25_only (pure lexical retrieval)
3. dense_only (pure vector similarity)
4. hybrid_rrf (reciprocal rank fusion)
5. hybrid_rrf_id (+ exact circular identifier boosting)
6. hybrid_rrf_id_temporal (+ temporal validity policies)
7. hybrid_rerank (+ cross-encoder reranking)
8. hybrid_rerank_rewrite (+ rules/LLM query rewriting)
9. hybrid_rerank_context (+ context dedupe, grouping, MMR diversification)
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from agent.types import RagAnswer
from config.paths import RETRIEVAL_CONFIG
from retrieval.index_store import IndexStore
from retrieval.pipeline import RagPipeline, Retriever

_SYSTEM_REGISTRY: Dict[str, Callable[..., Any]] = {}


class RetrievalOnlySystem:
    """Wrapper exposing standard .answer() interface without invoking LLM generation."""

    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    def retrieve(self, question: str, **kwargs: Any) -> Any:
        return self.retriever.retrieve(question, **kwargs)

    def answer(self, question: str, **kwargs: Any) -> RagAnswer:
        res = self.retriever.retrieve(question, **kwargs)
        retrieved = [
            {
                "chunk_id": rc.chunk.chunk_id,
                "doc_id": rc.chunk.doc_id,
                "rank": rc.rank,
                "fused_score": rc.fused_score,
                "rerank_score": rc.rerank_score,
                "status": rc.status,
                "superseded_by": rc.superseded_by,
            }
            for rc in res.chunks
        ]
        return RagAnswer(
            answer="",
            citations=[],
            refused=False,
            retrieved=retrieved,
            timings=res.timings,
            usage={"in": 0, "out": 0},
            provider="retrieval_only",
            model="none",
        )


def register_system(name: str, factory: Callable[..., Any]) -> None:
    """Register a system factory function under a unique name."""
    _SYSTEM_REGISTRY[name] = factory


def get_system(name: str, **kwargs: Any) -> Any:
    """Retrieve and instantiate a registered system by name."""
    if name not in _SYSTEM_REGISTRY:
        available = list(_SYSTEM_REGISTRY.keys())
        raise KeyError(f"Unknown system '{name}'. Available systems: {available}")
    return _SYSTEM_REGISTRY[name](**kwargs)


def list_systems() -> list[str]:
    """Return all registered system names."""
    return list(_SYSTEM_REGISTRY.keys())


# 1. Baseline System (Prompt 4 untouched)
def _create_baseline(**kwargs: Any) -> Any:
    from agent.baseline import BaselineRAG

    index_store = kwargs.get("index_store")
    if index_store is None:
        index_store = IndexStore.load(verify="fast")
    llm = kwargs.get("llm")
    return BaselineRAG(index_store=index_store, llm=llm)


register_system("baseline", _create_baseline)


def _build_system(overrides: Dict[str, Any], **kwargs: Any) -> Any:
    """Generic builder for Phase 5 retrieval and e2e systems."""
    retrieval_only = bool(kwargs.get("retrieval_only", False))
    store = kwargs.get("index_store") or kwargs.get("store")
    if store is None:
        store = IndexStore.load(verify="fast")
    llm = kwargs.get("llm")

    retriever = Retriever.from_config(
        path=RETRIEVAL_CONFIG,
        store=store,
        llm=llm,
        overrides=overrides,
    )

    if retrieval_only:
        return RetrievalOnlySystem(retriever)
    return RagPipeline(retriever=retriever, llm=llm)


# 2. bm25_only
register_system(
    "bm25_only",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "bm25_only",
                    "apply_id_boost": False,
                    "apply_temporal": False,
                },
                "reranker": {"enabled": False},
                "rewrite": {"use_rules": False, "use_llm_rewrite": False},
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 3. dense_only
register_system(
    "dense_only",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "dense_only",
                    "apply_id_boost": False,
                    "apply_temporal": False,
                },
                "reranker": {"enabled": False},
                "rewrite": {"use_rules": False, "use_llm_rewrite": False},
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 4. hybrid_rrf
register_system(
    "hybrid_rrf",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "rrf",
                    "w_dense": 1.0,
                    "w_bm25": 1.0,
                    "rrf_k": 60,
                    "apply_id_boost": False,
                    "apply_temporal": False,
                },
                "reranker": {"enabled": False},
                "rewrite": {"use_rules": False, "use_llm_rewrite": False},
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 5. hybrid_rrf_id
register_system(
    "hybrid_rrf_id",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "rrf",
                    "w_dense": 1.0,
                    "w_bm25": 1.0,
                    "rrf_k": 60,
                    "apply_id_boost": True,
                    "boost_id": 0.05,
                    "apply_temporal": False,
                },
                "reranker": {"enabled": False},
                "rewrite": {"use_rules": False, "use_llm_rewrite": False},
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 6. hybrid_rrf_id_temporal
register_system(
    "hybrid_rrf_id_temporal",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "rrf",
                    "w_dense": 1.0,
                    "w_bm25": 1.0,
                    "rrf_k": 60,
                    "apply_id_boost": True,
                    "boost_id": 0.05,
                    "apply_temporal": True,
                    "lambda_superseded": 0.85,
                },
                "reranker": {"enabled": False},
                "rewrite": {"use_rules": False, "use_llm_rewrite": False},
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 7. hybrid_rerank
register_system(
    "hybrid_rerank",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "rrf",
                    "w_dense": 1.0,
                    "w_bm25": 1.0,
                    "rrf_k": 60,
                    "apply_id_boost": True,
                    "boost_id": 0.05,
                    "apply_temporal": True,
                    "lambda_superseded": 0.85,
                },
                "reranker": {
                    "enabled": True,
                    "rerank_depth": 30,
                    "top_n": 8,
                },
                "rewrite": {"use_rules": False, "use_llm_rewrite": False},
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 8. hybrid_rerank_rewrite
register_system(
    "hybrid_rerank_rewrite",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "rrf",
                    "w_dense": 1.0,
                    "w_bm25": 1.0,
                    "rrf_k": 60,
                    "apply_id_boost": True,
                    "boost_id": 0.05,
                    "apply_temporal": True,
                    "lambda_superseded": 0.85,
                },
                "reranker": {
                    "enabled": True,
                    "rerank_depth": 30,
                    "top_n": 8,
                },
                "rewrite": {
                    "use_rules": True,
                    "use_llm_rewrite": False,
                },
                "context": {"dedupe_threshold": 100.0, "use_mmr": False, "expand_neighbors": False},
            }
        },
        **kw,
    ),
)

# 9. hybrid_rerank_context (The proposed best system)
register_system(
    "hybrid_rerank_context",
    lambda **kw: _build_system(
        overrides={
            "retrieval": {
                "hybrid": {
                    "fusion_method": "rrf",
                    "w_dense": 1.0,
                    "w_bm25": 1.0,
                    "rrf_k": 60,
                    "apply_id_boost": True,
                    "boost_id": 0.05,
                    "apply_temporal": True,
                    "lambda_superseded": 0.85,
                },
                "reranker": {
                    "enabled": True,
                    "rerank_depth": 30,
                    "top_n": 8,
                },
                "rewrite": {
                    "use_rules": True,
                    "use_llm_rewrite": False,
                },
                "context": {
                    "dedupe_threshold": 92.0,
                    "per_doc_cap": 3,
                    "use_mmr": False,
                    "expand_neighbors": False,
                },
            }
        },
        **kw,
    ),
)


# ---------------------------------------------------------------------------
# Phase 6: Agentic Systems and Ablation Ladder
# ---------------------------------------------------------------------------


# Alias: rag_best == hybrid_rerank_context (Prompt 5 winner)
register_system("rag_best", lambda **kw: get_system("hybrid_rerank_context", **kw))


def _build_agent_system(cap_overrides: Dict[str, bool], forced_mode: Optional[str] = None, **kwargs: Any) -> Any:
    """Builder for agentic systems with customizable capability toggles."""
    from agent.runner import AgentRunner

    store = kwargs.get("index_store") or kwargs.get("store")
    if store is None:
        store = IndexStore.load(verify="fast")
    llm = kwargs.get("llm")

    overrides: Dict[str, Any] = {"capabilities": dict(cap_overrides)}
    runner = AgentRunner.from_config(
        retriever=None,
        llm=llm,
        overrides=overrides,
    )
    if forced_mode:
        runner.mode = forced_mode
    return runner


# Full agent in RULES mode (zero-LLM deterministic fallback)
register_system(
    "agent_rules",
    lambda **kw: _build_agent_system(
        cap_overrides={
            "router": True,
            "decompose": True,
            "grade_retry": True,
            "validity": True,
            "xref": True,
            "selfcheck": True,
            "clarify": True,
        },
        forced_mode="rules",
        **kw,
    ),
)

# Full agent in FULL mode (or auto-resolved)
register_system(
    "agent_full",
    lambda **kw: _build_agent_system(
        cap_overrides={
            "router": True,
            "decompose": True,
            "grade_retry": True,
            "validity": True,
            "xref": True,
            "selfcheck": True,
            "clarify": True,
        },
        **kw,
    ),
)

# Ladder variant 1: rag_best + router
register_system(
    "agent_ladder_router",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": False, "grade_retry": False, "validity": False, "xref": False, "selfcheck": False, "clarify": False},
        **kw,
    ),
)

# Ladder variant 2: + grade_retry
register_system(
    "agent_ladder_grade",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": False, "grade_retry": True, "validity": False, "xref": False, "selfcheck": False, "clarify": False},
        **kw,
    ),
)

# Ladder variant 3: + decompose
register_system(
    "agent_ladder_decompose",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": True, "grade_retry": True, "validity": False, "xref": False, "selfcheck": False, "clarify": False},
        **kw,
    ),
)

# Ladder variant 4: + validity
register_system(
    "agent_ladder_validity",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": True, "grade_retry": True, "validity": True, "xref": False, "selfcheck": False, "clarify": False},
        **kw,
    ),
)

# Ladder variant 5: + xref
register_system(
    "agent_ladder_xref",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": True, "grade_retry": True, "validity": True, "xref": True, "selfcheck": False, "clarify": False},
        **kw,
    ),
)

# Ladder variant 6: + selfcheck
register_system(
    "agent_ladder_selfcheck",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": True, "grade_retry": True, "validity": True, "xref": True, "selfcheck": True, "clarify": False},
        **kw,
    ),
)

# Ladder variant 7: + clarify (non-interactive: assumptions) == agent_full
register_system(
    "agent_ladder_clarify",
    lambda **kw: _build_agent_system(
        cap_overrides={"router": True, "decompose": True, "grade_retry": True, "validity": True, "xref": True, "selfcheck": True, "clarify": True},
        **kw,
    ),
)

