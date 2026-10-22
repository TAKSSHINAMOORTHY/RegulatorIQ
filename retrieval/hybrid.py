"""Hybrid retrieval, fusion algorithms, identifier boosting, and temporal policies.

Implements candidate generation (dense + BM25 + identifier hits), fusion methods
(RRF, weighted normalisation, dense_only, bm25_only), temporal validity policies,
and multi-query reciprocal rank fusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from retrieval.index_store import Filters, Hit, IndexStore
from retrieval.query_analysis import QueryPlan


@dataclass
class RankedChunk:
    """A scored, ranked chunk carrying provenance, score, and temporal validity."""

    chunk: Any
    fused_score: float
    rerank_score: float
    rank: int
    status: str  # "current" | "superseded" | "unknown"
    superseded_by: Optional[str] = None


@dataclass
class HybridConfig:
    """Configuration for candidate generation and fusion."""

    k_dense: int = 50
    k_bm25: int = 50
    fusion_method: str = "rrf"  # "rrf" | "weighted_norm" | "dense_only" | "bm25_only"
    rrf_k: int = 60
    w_dense: float = 1.0
    w_bm25: float = 1.0
    alpha_dense: float = 0.5  # for weighted_norm: alpha * dense + (1 - alpha) * bm25
    boost_id: float = 0.05
    lambda_superseded: float = 0.85
    min_pool: int = 10
    max_id_chunks_per_doc: int = 20
    apply_temporal: bool = True
    apply_id_boost: bool = True


def rrf_fuse(
    dense_hits: List[Hit],
    bm25_hits: List[Hit],
    rrf_k: int = 60,
    w_dense: float = 1.0,
    w_bm25: float = 1.0,
) -> Dict[str, float]:
    """Reciprocal Rank Fusion over dense and BM25 hits.

    Formula: score(c) = sum_i w_i / (rrf_k + rank_i)
    """
    scores: Dict[str, float] = {}

    for hit in dense_hits:
        cid = hit.chunk_id
        score = w_dense / (rrf_k + hit.rank)
        scores[cid] = scores.get(cid, 0.0) + score

    for hit in bm25_hits:
        cid = hit.chunk_id
        score = w_bm25 / (rrf_k + hit.rank)
        scores[cid] = scores.get(cid, 0.0) + score

    return scores


def weighted_norm_fuse(
    dense_hits: List[Hit],
    bm25_hits: List[Hit],
    alpha: float = 0.5,
) -> Dict[str, float]:
    """Weighted min-max normalized fusion between dense and BM25 scores."""
    scores: Dict[str, float] = {}

    def min_max_norm(hits: List[Hit]) -> Dict[str, float]:
        if not hits:
            return {}
        raw_scores = [h.score for h in hits]
        s_min = min(raw_scores)
        s_max = max(raw_scores)
        if abs(s_max - s_min) < 1e-9:
            return {h.chunk_id: 1.0 for h in hits}
        return {h.chunk_id: (h.score - s_min) / (s_max - s_min) for h in hits}

    norm_dense = min_max_norm(dense_hits)
    norm_bm25 = min_max_norm(bm25_hits)

    all_cids = set(norm_dense.keys()) | set(norm_bm25.keys())
    for cid in all_cids:
        s_d = norm_dense.get(cid, 0.0)
        s_b = norm_bm25.get(cid, 0.0)
        scores[cid] = alpha * s_d + (1.0 - alpha) * s_b

    return scores


class HybridRetriever:
    """Core retrieval layer handling candidate generation and fusion."""

    def __init__(self, store: IndexStore, config: Optional[HybridConfig] = None) -> None:
        self.store = store
        self.config = config or HybridConfig()

    def _get_identifier_chunks(self, plan: QueryPlan) -> List[Tuple[str, str]]:
        """Fetch chunks for documents matched by exact identifier.

        Returns list of (chunk_id, doc_id) up to max_id_chunks_per_doc per document.
        """
        id_chunks: List[Tuple[str, str]] = []
        seen_cids: Set[str] = set()

        for ident in plan.identifiers:
            matched_cids = self.store.lookup_identifier(ident)
            if not matched_cids:
                continue

            # Group matched chunks by doc_id
            matched_chunks = self.store.get_chunks(matched_cids)
            doc_groups: Dict[str, List[Any]] = {}
            for ch in matched_chunks:
                doc_groups.setdefault(ch.doc_id, []).append(ch)

            for doc_id in doc_groups.keys():
                # Retrieve all doc chunks sorted by ordinal
                all_chunks = self.store.doc_chunks(doc_id)
                lead_chunks = all_chunks[: self.config.max_id_chunks_per_doc]
                for ch in lead_chunks:
                    if ch.chunk_id not in seen_cids:
                        seen_cids.add(ch.chunk_id)
                        id_chunks.append((ch.chunk_id, doc_id))

        return id_chunks

    def _generate_candidates_for_variant(
        self,
        query: str,
        filters: Optional[Filters] = None,
    ) -> Tuple[List[Hit], List[Hit]]:
        """Fetch dense and BM25 candidates for a single query variant."""
        dense_hits = self.store.search_dense(
            query=query,
            k=self.config.k_dense,
            filters=filters,
        )
        bm25_hits = self.store.search_bm25(
            query=query,
            k=self.config.k_bm25,
            filters=filters,
        )
        return dense_hits, bm25_hits

    def _fuse_hits(
        self,
        dense_hits: List[Hit],
        bm25_hits: List[Hit],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Apply configured fusion algorithm to dense and BM25 hits.

        Returns (fused_scores, dense_score_lookup).
        """
        dense_lookup = {h.chunk_id: h.score for h in dense_hits}

        method = self.config.fusion_method
        if method == "rrf":
            fused = rrf_fuse(
                dense_hits=dense_hits,
                bm25_hits=bm25_hits,
                rrf_k=self.config.rrf_k,
                w_dense=self.config.w_dense,
                w_bm25=self.config.w_bm25,
            )
        elif method == "weighted_norm":
            fused = weighted_norm_fuse(
                dense_hits=dense_hits,
                bm25_hits=bm25_hits,
                alpha=self.config.alpha_dense,
            )
        elif method == "dense_only":
            fused = {h.chunk_id: float(h.score) for h in dense_hits}
        elif method == "bm25_only":
            fused = {h.chunk_id: float(h.score) for h in bm25_hits}
        else:
            # Fallback to rrf
            fused = rrf_fuse(
                dense_hits=dense_hits,
                bm25_hits=bm25_hits,
                rrf_k=self.config.rrf_k,
            )

        return fused, dense_lookup

    def _apply_temporal_policy(
        self,
        scored_cids: List[str],
        score_map: Dict[str, float],
        plan: QueryPlan,
    ) -> Tuple[List[str], Dict[str, float], List[str]]:
        """Apply temporal filtering and soft penalties per B4.

        Returns (filtered_cids, adjusted_score_map, warnings).
        """
        if not self.config.apply_temporal:
            return scored_cids, score_map, []

        warnings: List[str] = []
        chunks = self.store.get_chunks(scored_cids)
        chunk_map = {c.chunk_id: c for c in chunks}

        # Case 1: as_of_date is present
        if plan.as_of_date:
            as_of = plan.as_of_date
            surviving_cids: List[str] = []
            for cid in scored_cids:
                c = chunk_map.get(cid)
                if not c:
                    continue
                v_from = c.valid_from or c.issue_date
                v_to = c.valid_to
                # If valid_from is after as_of, it was not yet in force
                if v_from and as_of < v_from:
                    continue
                # If valid_to is on or before as_of, it has expired
                if v_to and as_of >= v_to:
                    continue
                surviving_cids.append(cid)
            return surviving_cids, score_map, warnings

        # Case 2: wants_current and not wants_history
        if plan.wants_current and not plan.wants_history:
            current_cids = [
                cid for cid in scored_cids if chunk_map.get(cid) and chunk_map[cid].is_current
            ]
            if len(current_cids) >= self.config.min_pool:
                # Hard filter: keep ONLY current chunks
                return current_cids, score_map, warnings
            else:
                # Fall back to soft penalty
                warnings.append("few_current_results")
                adjusted = dict(score_map)
                for cid in scored_cids:
                    c = chunk_map.get(cid)
                    if c and not c.is_current:
                        adjusted[cid] = adjusted[cid] * self.config.lambda_superseded
                return scored_cids, adjusted, warnings

        # Case 3: wants_history
        if plan.wants_history:
            # No preference or penalty
            return scored_cids, score_map, warnings

        # Case 4: Neither stated -> soft preference against superseded
        adjusted = dict(score_map)
        for cid in scored_cids:
            c = chunk_map.get(cid)
            if c and not c.is_current:
                adjusted[cid] = adjusted[cid] * self.config.lambda_superseded

        return scored_cids, adjusted, warnings

    def retrieve_candidates(
        self,
        plan: QueryPlan,
        filters: Optional[Filters] = None,
    ) -> Tuple[List[RankedChunk], List[str]]:
        """Run candidate retrieval, fusion, identifier boost, and temporal policy."""
        warnings: List[str] = list(plan.warnings)

        # Multi-query variant execution
        variant_score_maps: List[Dict[str, float]] = []
        dense_lookups: Dict[str, float] = {}

        for variant in plan.query_variants:
            d_hits, b_hits = self._generate_candidates_for_variant(
                query=variant,
                filters=filters,
            )
            v_scores, d_lookup = self._fuse_hits(d_hits, b_hits)
            variant_score_maps.append(v_scores)
            for cid, sc in d_lookup.items():
                if cid not in dense_lookups or sc > dense_lookups[cid]:
                    dense_lookups[cid] = sc

        # Combine variant lists with RRF over variants (B5)
        combined_scores: Dict[str, float] = {}
        if len(variant_score_maps) == 1:
            combined_scores = variant_score_maps[0]
        else:
            for v_map in variant_score_maps:
                # Sort variant hits to get ranks
                sorted_cids = sorted(
                    v_map.keys(),
                    key=lambda x: (-v_map[x], -dense_lookups.get(x, 0.0), x),
                )
                for rank, cid in enumerate(sorted_cids, start=1):
                    rrf_val = 1.0 / (self.config.rrf_k + rank)
                    combined_scores[cid] = combined_scores.get(cid, 0.0) + rrf_val

        # Add identifier chunks (B1) and identifier boost (B3)
        id_chunks = self._get_identifier_chunks(plan)
        id_cids = {cid for cid, _ in id_chunks}

        if self.config.apply_id_boost and id_cids:
            # Ensure all identifier chunks exist in combined_scores
            min_score = min(combined_scores.values()) if combined_scores else 0.0
            for cid, _ in id_chunks:
                if cid not in combined_scores:
                    combined_scores[cid] = min_score * 0.5

            # Apply additive identifier boost
            for cid in id_cids:
                if cid in combined_scores:
                    combined_scores[cid] += self.config.boost_id

        # Sort candidate list deterministically
        # Tie break: fused_score desc, dense_score desc, chunk_id asc
        all_cids = list(combined_scores.keys())
        all_cids.sort(
            key=lambda cid: (
                -combined_scores[cid],
                -dense_lookups.get(cid, 0.0),
                cid,
            )
        )

        # Apply temporal policy (B4)
        surviving_cids, final_score_map, temp_warnings = self._apply_temporal_policy(
            all_cids, combined_scores, plan
        )
        warnings.extend(temp_warnings)

        # Re-sort surviving candidates after potential temporal penalties
        surviving_cids.sort(
            key=lambda cid: (
                -final_score_map[cid],
                -dense_lookups.get(cid, 0.0),
                cid,
            )
        )

        # Build RankedChunk objects
        chunks = self.store.get_chunks(surviving_cids)
        chunk_map = {c.chunk_id: c for c in chunks}

        ranked_chunks: List[RankedChunk] = []
        for rank, cid in enumerate(surviving_cids, start=1):
            c = chunk_map.get(cid)
            if not c:
                continue

            # Determine validity status and superseding document
            if c.is_current:
                status = "current"
                superseded_by = None
            else:
                status = "superseded"
                links = self.store.links_for(c.doc_id)
                superseded_by = None
                for link in links:
                    rel = getattr(link, "rel_type", getattr(link, "relation", ""))
                    if rel in ("superseded_by", "supersedes", "repealed_by"):
                        superseded_by = getattr(
                            link,
                            "target_circular_no",
                            getattr(
                                link,
                                "target_doc_id",
                                getattr(link, "dst_ref_text", getattr(link, "dst_doc_id", None)),
                            ),
                        )
                        break

            fused_score = round(final_score_map[cid], 6)
            ranked_chunks.append(
                RankedChunk(
                    chunk=c,
                    fused_score=fused_score,
                    rerank_score=fused_score,  # Prior to reranker stage
                    rank=rank,
                    status=status,
                    superseded_by=superseded_by,
                )
            )

        return ranked_chunks, warnings
