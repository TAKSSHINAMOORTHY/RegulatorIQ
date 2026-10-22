"""Unified Retriever API, retrieval orchestration, and RagPipeline v2.

Exports:
- Retriever: Main entrypoint for Prompt 5 and Prompt 6.
- RetrievalResult: Scored and calibrated retrieval outcome.
- RagPipeline: End-to-end question answering pipeline using rag.v2 prompt.
- build_context: Public re-export from retrieval.context.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agent.llm import LLM, repair_and_parse_json
from agent.types import RagAnswer
from config.paths import PROMPT_RAG_V2_PATH, RETRIEVAL_CONFIG
from retrieval.context import build_context
from retrieval.hybrid import HybridConfig, HybridRetriever, RankedChunk
from retrieval.index_store import IndexStore
from retrieval.query_analysis import QueryPlan, analyze_query
from retrieval.rerank import (
    BaseReranker,
    ConfidenceCalibrator,
    CrossEncoderFastEmbed,
    FakeReranker,
    LexicalSemanticReranker,
    RerankCache,
    rerank_candidates,
)
from retrieval.rewrite import QueryRewriter


@dataclass
class RetrievalResult:
    """Standardized retrieval output returned by Retriever.retrieve."""

    chunks: List[RankedChunk]
    plan: QueryPlan
    confidence: float
    top1_score: float
    margin: float
    warnings: List[str] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


class Retriever:
    """Unified regulatory retrieval engine supporting hybrid search, fusion, reranking, and rewriting."""

    def __init__(
        self,
        store: IndexStore,
        config: Dict[str, Any],
        reranker: Optional[BaseReranker] = None,
        llm: Optional[LLM] = None,
        cache: Optional[RerankCache] = None,
        calibrator: Optional[ConfidenceCalibrator] = None,
    ) -> None:
        self.store = store
        self.config = config
        self.llm = llm
        self.cache = cache or RerankCache()
        self.calibrator = calibrator or ConfidenceCalibrator.load()

        # Build component configurations
        self._validate_config(config)
        ret_conf = config.get("retrieval", {})

        # Hybrid candidate configuration
        h_conf = ret_conf.get("hybrid", {})
        self.hybrid_config = HybridConfig(
            k_dense=int(h_conf.get("k_dense", 50)),
            k_bm25=int(h_conf.get("k_bm25", 50)),
            fusion_method=str(h_conf.get("fusion_method", "rrf")),
            rrf_k=int(h_conf.get("rrf_k", 60)),
            w_dense=float(h_conf.get("w_dense", 1.0)),
            w_bm25=float(h_conf.get("w_bm25", 1.0)),
            alpha_dense=float(h_conf.get("alpha_dense", 0.5)),
            boost_id=float(h_conf.get("boost_id", 0.05)),
            lambda_superseded=float(h_conf.get("lambda_superseded", 0.85)),
            min_pool=int(h_conf.get("min_pool", 10)),
            max_id_chunks_per_doc=int(h_conf.get("max_id_chunks_per_doc", 20)),
            apply_temporal=bool(h_conf.get("apply_temporal", True)),
            apply_id_boost=bool(h_conf.get("apply_id_boost", True)),
        )
        self.hybrid_retriever = HybridRetriever(self.store, self.hybrid_config)

        # Reranker setup
        r_conf = ret_conf.get("reranker", {})
        self.reranker_enabled = bool(r_conf.get("enabled", True))
        self.rerank_depth = int(r_conf.get("rerank_depth", 30))
        self.top_n = int(r_conf.get("top_n", 8))
        self.early_exit_margin = float(r_conf.get("early_exit_margin", 0.05))

        if reranker is not None:
            self.reranker = reranker
        elif self.reranker_enabled:
            model_name = r_conf.get("model_name", "Xenova/ms-marco-MiniLM-L-6-v2")
            try:
                self.reranker = CrossEncoderFastEmbed(model_name=model_name)
            except Exception:
                self.reranker = LexicalSemanticReranker()
        else:
            self.reranker = FakeReranker(mode="identity")

        # Query rewrite setup
        rw_conf = ret_conf.get("rewrite", {})
        self.rewriter = QueryRewriter(
            llm=self.llm,
            use_rules=bool(rw_conf.get("use_rules", True)),
            use_llm_rewrite=bool(rw_conf.get("use_llm_rewrite", False)),
            use_hyde=bool(rw_conf.get("use_hyde", False)),
            use_multi_query=bool(rw_conf.get("use_multi_query", False)),
        )

        # Context assembly setup
        ctx_conf = ret_conf.get("context", {})
        self.token_budget = int(ctx_conf.get("token_budget", 3000))
        self.expand_neighbors = bool(ctx_conf.get("expand_neighbors", False))
        self.use_mmr = bool(ctx_conf.get("use_mmr", False))
        self.lambda_mmr = float(ctx_conf.get("lambda_mmr", 0.7))
        self.dedupe_threshold = float(ctx_conf.get("dedupe_threshold", 92.0))
        self.per_doc_cap = int(ctx_conf.get("per_doc_cap", 3))

    @staticmethod
    def _validate_config(config: Dict[str, Any]) -> None:
        """Validate configuration structure and parameter constraints."""
        if not isinstance(config, dict):
            raise ValueError(f"Configuration must be a dictionary, got {type(config)}")
        ret_conf = config.get("retrieval", {})
        h_conf = ret_conf.get("hybrid", {})
        valid_methods = {"rrf", "weighted_norm", "dense_only", "bm25_only"}
        method = h_conf.get("fusion_method", "rrf")
        if method not in valid_methods:
            raise ValueError(f"Invalid fusion_method '{method}'. Must be one of {valid_methods}")
        if h_conf.get("w_dense", 1.0) < 0 or h_conf.get("w_bm25", 1.0) < 0:
            raise ValueError("Fusion weights must be non-negative")
        if h_conf.get("rrf_k", 60) <= 0:
            raise ValueError("rrf_k must be positive")

    @classmethod
    def from_config(
        cls,
        path: Optional[Path] = None,
        store: Optional[IndexStore] = None,
        llm: Optional[LLM] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "Retriever":
        """Instantiate Retriever from a yaml configuration file."""
        config_path = path or RETRIEVAL_CONFIG
        if not config_path.exists():
            # Create default configuration if not present
            config = {
                "retrieval": {
                    "version": "1.0.0",
                    "tuned_on": "dev",
                    "hybrid": {
                        "k_dense": 50,
                        "k_bm25": 50,
                        "fusion_method": "rrf",
                        "rrf_k": 60,
                        "w_dense": 1.0,
                        "w_bm25": 1.0,
                        "alpha_dense": 0.5,
                        "boost_id": 0.05,
                        "lambda_superseded": 0.85,
                        "min_pool": 10,
                        "max_id_chunks_per_doc": 20,
                        "apply_temporal": True,
                        "apply_id_boost": True,
                    },
                    "reranker": {
                        "enabled": True,
                        "model_name": "Xenova/ms-marco-MiniLM-L-6-v2",
                        "rerank_depth": 30,
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
                        "use_mmr": False,
                        "lambda_mmr": 0.7,
                        "per_doc_cap": 3,
                    },
                }
            }
        else:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        if overrides:
            config = copy.deepcopy(config)
            # Deep update overrides
            for k, v in overrides.items():
                if isinstance(v, dict) and k in config:
                    config[k].update(v)
                else:
                    config[k] = v

        if store is None:
            store = IndexStore.load()

        return cls(store=store, config=config, llm=llm)

    def retrieve(
        self,
        question: str,
        *,
        filters: Optional[Any] = None,
        as_of: Optional[str] = None,
        history: Optional[bool] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> RetrievalResult:
        """Execute full hybrid retrieval pipeline for a question."""
        t_start = time.perf_counter()
        timings: Dict[str, float] = {}

        # 1. Query Analysis
        t_qa = time.perf_counter()
        plan = analyze_query(question, store=self.store)
        if as_of is not None:
            plan.as_of_date = as_of
            plan.wants_current = True
        if history is not None:
            plan.wants_history = history
            if history:
                plan.wants_current = False
        timings["query_analysis_ms"] = round((time.perf_counter() - t_qa) * 1000.0, 2)

        # 2. Query Rewriting
        t_rw = time.perf_counter()
        rewrite_res = self.rewriter.rewrite(plan)
        plan.query_variants = rewrite_res.query_variants
        timings["rewrite_ms"] = round((time.perf_counter() - t_rw) * 1000.0, 2)

        # 3. Candidate Generation and Fusion
        t_fuse = time.perf_counter()
        candidates, fuse_warnings = self.hybrid_retriever.retrieve_candidates(
            plan=plan,
            filters=filters,
        )
        timings["fusion_ms"] = round((time.perf_counter() - t_fuse) * 1000.0, 2)

        # 4. Cross-Encoder Reranking
        t_rr = time.perf_counter()
        top_n = self.top_n
        depth = self.rerank_depth
        if overrides:
            top_n = int(overrides.get("top_n", top_n))
            depth = int(overrides.get("rerank_depth", depth))

        if self.reranker_enabled:
            final_chunks, rr_meta = rerank_candidates(
                query=question,
                candidates=candidates,
                reranker=self.reranker,
                rerank_depth=depth,
                top_n=top_n,
                early_exit_margin=self.early_exit_margin,
                cache=self.cache,
                calibrator=self.calibrator,
            )
            top1_score = rr_meta["top1_score"]
            margin = rr_meta["margin"]
            confidence = rr_meta["confidence"]
        else:
            final_chunks = candidates[:top_n]
            for rk, c in enumerate(final_chunks, start=1):
                c.rank = rk
            top1_score = final_chunks[0].fused_score if final_chunks else 0.0
            margin = (
                (top1_score - final_chunks[1].fused_score) if len(final_chunks) > 1 else top1_score
            )
            confidence = self.calibrator.predict_proba(top1_score, margin)
            rr_meta = {
                "top1_score": top1_score,
                "margin": margin,
                "confidence": confidence,
                "early_exit": False,
                "rerank_count": 0,
            }

        timings["rerank_ms"] = round((time.perf_counter() - t_rr) * 1000.0, 2)
        timings["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)

        all_warnings = list(plan.warnings) + fuse_warnings
        if rewrite_res.degraded_rewrite:
            all_warnings.append("degraded_rewrite")

        return RetrievalResult(
            chunks=final_chunks,
            plan=plan,
            confidence=confidence,
            top1_score=top1_score,
            margin=margin,
            warnings=all_warnings,
            timings=timings,
            debug={
                "fused_candidate_count": len(candidates),
                "reranker": getattr(self.reranker, "model_id", "none"),
                "degraded": getattr(self.reranker, "degraded", False),
                "rr_meta": rr_meta,
            },
        )


class RagPipeline:
    """End-to-end question answering pipeline using Retriever, Context assembly, and Prompt v2."""

    def __init__(self, retriever: Retriever, llm: Optional[LLM] = None) -> None:
        self.retriever = retriever
        self.llm = llm or LLM()
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        if PROMPT_RAG_V2_PATH.exists():
            return PROMPT_RAG_V2_PATH.read_text(encoding="utf-8")
        return 'Context:\n{context}\n\nQuestion: {question}\n\nReturn JSON: {"answer": "...", "citations": [], "refused": false}'

    def answer(self, question: str, **kwargs: Any) -> RagAnswer:
        """Answer question using retrieved context and prompt v2."""
        t0 = time.perf_counter()

        # 1. Retrieve relevant chunks
        result = self.retriever.retrieve(question, **kwargs)

        # 2. Assemble context bundle
        bundle = build_context(
            result,
            token_budget=self.retriever.token_budget,
            expand_neighbors=self.retriever.expand_neighbors,
            use_mmr=self.retriever.use_mmr,
            lambda_mmr=self.retriever.lambda_mmr,
            dedupe_threshold=self.retriever.dedupe_threshold,
            per_doc_cap=self.retriever.per_doc_cap,
            store=self.retriever.store,
        )

        # 3. Format prompt
        # Use str.replace to protect JSON curly braces in template
        prompt_text = self.prompt_template.replace("{context}", bundle.text).replace(
            "{question}", question
        )

        # 4. Generate answer via LLM
        t_llm = time.perf_counter()
        messages = [{"role": "user", "content": prompt_text}]
        llm_res = self.llm.generate(messages=messages, max_tokens=1024)
        t_llm_elapsed = time.perf_counter() - t_llm

        # 5. Parse response
        parsed = repair_and_parse_json(llm_res.text) or {}
        answer_text = str(parsed.get("answer", llm_res.text))
        refused = bool(parsed.get("refused", False))
        raw_citations = parsed.get("citations", [])

        # Extract citation numbers from answer text if not in citations field
        if not raw_citations:
            found_refs = [int(m) for m in re.findall(r"\[(\d+)\]", answer_text)]
            raw_citations = sorted(list(set(found_refs)))

        # Build citation objects linking to items
        citations: List[Dict[str, Any]] = []
        for ref_num in raw_citations:
            idx = ref_num - 1
            if 0 <= idx < len(bundle.items):
                item = bundle.items[idx]
                c = item.chunk
                citations.append(
                    {
                        "ref_num": ref_num,
                        "chunk_id": c.chunk_id,
                        "doc_id": c.doc_id,
                        "circular_no": getattr(c, "circular_no", None),
                        "title": getattr(c, "title", ""),
                        "issue_date": getattr(c, "issue_date", None),
                        "para_ref": getattr(c, "para_ref", None),
                        "source_url": getattr(c, "source_url", ""),
                    }
                )

        retrieved_items = [
            {
                "chunk_id": item.chunk.chunk_id,
                "doc_id": item.chunk.doc_id,
                "rank": item.rank,
                "fused_score": item.fused_score,
                "rerank_score": item.rerank_score,
                "status": item.status,
                "superseded_by": item.superseded_by,
            }
            for item in bundle.items
        ]

        total_elapsed = time.perf_counter() - t0
        timings = dict(result.timings)
        timings["llm_generation_ms"] = round(t_llm_elapsed * 1000.0, 2)
        timings["total_pipeline_ms"] = round(total_elapsed * 1000.0, 2)

        return RagAnswer(
            answer=answer_text,
            citations=citations,
            refused=refused,
            retrieved=retrieved_items,
            timings=timings,
            usage=llm_res.usage,
            provider=llm_res.provider,
            model=llm_res.model,
        )
