"""Context assembly, deduplication, MMR diversification, neighbor expansion, and budgeting.

Formats structured, numbered context bundles respecting token limits, avoiding
mid-sentence truncation, and maintaining document grouping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import rapidfuzz.fuzz

from retrieval.chunking import TokenCounter
from retrieval.hybrid import RankedChunk


@dataclass
class ContextBundle:
    """Assembled context payload for generation."""

    text: str
    items: List[RankedChunk]
    token_count: int
    dropped: List[RankedChunk] = field(default_factory=list)


def compute_text_similarity(t1: str, t2: str) -> float:
    """Compute normalized text similarity using rapidfuzz."""
    if not t1 or not t2:
        return 0.0
    return float(rapidfuzz.fuzz.ratio(t1, t2))


def mmr_diversify(
    candidates: List[RankedChunk],
    lambda_mmr: float = 0.7,
    top_k: int = 15,
) -> List[RankedChunk]:
    """Maximal Marginal Relevance (MMR) selection over ranked chunks."""
    if not candidates:
        return []

    selected: List[RankedChunk] = [candidates[0]]
    remaining: List[RankedChunk] = list(candidates[1:])

    # Normalize rerank scores to [0, 1] for balanced combination
    max_score = max(c.rerank_score for c in candidates)
    min_score = min(c.rerank_score for c in candidates)
    denom = max(1e-6, max_score - min_score)

    while remaining and len(selected) < top_k:
        best_idx = -1
        best_mmr_score = -1e9

        for idx, cand in enumerate(remaining):
            norm_score = (cand.rerank_score - min_score) / denom
            max_sim = max(
                compute_text_similarity(cand.chunk.text, s.chunk.text) / 100.0 for s in selected
            )
            mmr_val = lambda_mmr * norm_score - (1.0 - lambda_mmr) * max_sim
            if mmr_val > best_mmr_score:
                best_mmr_score = mmr_val
                best_idx = idx

        if best_idx >= 0:
            selected.append(remaining.pop(best_idx))
        else:
            break

    return selected + remaining


def build_context(
    result: Any,
    token_budget: int = 3000,
    expand_neighbors: bool = False,
    use_mmr: bool = False,
    lambda_mmr: float = 0.7,
    dedupe_threshold: float = 92.0,
    per_doc_cap: int = 3,
    store: Optional[Any] = None,
) -> ContextBundle:
    """Build formatted, deduplicated, and budgeted context bundle from retrieval results."""
    # Extract ranked chunks from RetrievalResult or list
    if hasattr(result, "chunks"):
        raw_chunks: List[RankedChunk] = list(result.chunks)
        plan = getattr(result, "plan", None)
    else:
        raw_chunks = list(result)
        plan = None

    if not raw_chunks:
        return ContextBundle(text="", items=[], token_count=0, dropped=[])

    id_matched_docs: Set[str] = set()
    if plan and plan.identifiers and store and hasattr(store, "lookup_identifier"):
        for ident in plan.identifiers:
            cids = store.lookup_identifier(ident)
            for ch in store.get_chunks(cids):
                id_matched_docs.add(ch.doc_id)

    # 1. Deduplication (rapidfuzz >= dedupe_threshold)
    deduped_chunks: List[RankedChunk] = []
    dropped: List[RankedChunk] = []

    for rc in raw_chunks:
        is_dupe = False
        for chosen in deduped_chunks:
            sim = compute_text_similarity(rc.chunk.text, chosen.chunk.text)
            if sim >= dedupe_threshold:
                is_dupe = True
                break
            # Also check if same doc and adjacent with high overlap
            if rc.chunk.doc_id == chosen.chunk.doc_id:
                if abs(rc.chunk.ordinal - chosen.chunk.ordinal) <= 1 and sim >= 80.0:
                    is_dupe = True
                    break
        if is_dupe:
            dropped.append(rc)
        else:
            deduped_chunks.append(rc)

    # 2. Neighbor expansion (window=1 for top 2 chunks)
    if expand_neighbors and store is not None and hasattr(store, "neighbors"):
        expanded: List[RankedChunk] = []
        seen_ids = {rc.chunk.chunk_id for rc in deduped_chunks}

        for i, rc in enumerate(deduped_chunks):
            expanded.append(rc)
            if i < 2:  # Only expand top 2
                nb_chunks = store.neighbors(rc.chunk.chunk_id, window=1)
                for nb in nb_chunks:
                    if nb.chunk_id not in seen_ids:
                        seen_ids.add(nb.chunk_id)
                        nb_rc = RankedChunk(
                            chunk=nb,
                            fused_score=rc.fused_score * 0.9,
                            rerank_score=rc.rerank_score * 0.9,
                            rank=rc.rank,
                            status="current" if nb.is_current else "superseded",
                            superseded_by=rc.superseded_by,
                        )
                        expanded.append(nb_rc)
        deduped_chunks = expanded

    # 3. MMR diversification if enabled
    if use_mmr:
        deduped_chunks = mmr_diversify(deduped_chunks, lambda_mmr=lambda_mmr)

    # 4. Per-document cap (max 3 per doc unless exact identifier match)
    capped_chunks: List[RankedChunk] = []
    doc_counts: Dict[str, int] = {}

    for rc in deduped_chunks:
        doc_id = rc.chunk.doc_id
        cap = 20 if doc_id in id_matched_docs else per_doc_cap
        curr_count = doc_counts.get(doc_id, 0)
        if curr_count < cap:
            doc_counts[doc_id] = curr_count + 1
            capped_chunks.append(rc)
        else:
            dropped.append(rc)

    # 5. Order by rerank score, but group chunks of the same document together
    # Find best rank per doc
    doc_best_score: Dict[str, float] = {}
    for rc in capped_chunks:
        d = rc.chunk.doc_id
        doc_best_score[d] = max(doc_best_score.get(d, -1e9), rc.rerank_score)

    capped_chunks.sort(
        key=lambda rc: (-doc_best_score[rc.chunk.doc_id], rc.chunk.doc_id, rc.chunk.ordinal)
    )

    # 6. Token budgeting using index tokenizer
    counter = TokenCounter()
    formatted_items: List[Tuple[RankedChunk, str, int]] = []

    for idx, rc in enumerate(capped_chunks, start=1):
        c = rc.chunk
        doc_type = getattr(c, "doc_type", "Document")
        title = getattr(c, "title", "")
        circular_no = getattr(c, "circular_no", None) or "N/A"
        issue_date = getattr(c, "issue_date", None) or "N/A"
        para_ref = getattr(c, "para_ref", None) or "N/A"

        if rc.superseded_by:
            status_str = f"superseded by {rc.superseded_by}"
        elif rc.status == "superseded":
            status_str = "superseded"
        elif rc.status == "current":
            status_str = "current"
        else:
            status_str = "unknown"

        label = f"[{idx}] {doc_type} | {title} | {circular_no} | {issue_date} | {para_ref} | status: {status_str}"
        body = c.text.strip()
        chunk_text = f"{label}\n{body}"
        tokens = counter.count(chunk_text)
        formatted_items.append((rc, chunk_text, tokens))

    # Fit items within token_budget
    # If total exceeds budget, drop lowest-ranked (or last) chunks entirely (never cut mid-sentence)
    accepted_chunks: List[RankedChunk] = []
    accepted_texts: List[str] = []
    total_tokens = 0

    for rc, text_block, count in formatted_items:
        if total_tokens + count <= token_budget:
            accepted_chunks.append(rc)
            accepted_texts.append(text_block)
            total_tokens += count
        else:
            # Cannot fit entire chunk without cutting mid-sentence -> drop chunk
            dropped.append(rc)

    final_text = "\n\n".join(accepted_texts)
    return ContextBundle(
        text=final_text,
        items=accepted_chunks,
        token_count=total_tokens,
        dropped=dropped,
    )
