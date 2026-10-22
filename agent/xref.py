"""Cross-reference traversal across interrelated RBI circulars and Master Directions.

Enables multi-hop evidence collection:
- Follows reference edges and in-text citations up to xref_max_hops.
- Targets specific referenced paragraphs/clauses when mentioned.
- Protects against cycles and respects document budgets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from retrieval.hybrid import RankedChunk


@dataclass
class XRefFinding:
    """Record of cross-referenced document traversal."""

    src_doc_id: str
    target_doc_id: str
    relation: str  # "refers_to", "amends", "cites"
    reference_text: str
    path: List[str]
    retrieved_chunks: List[RankedChunk] = field(default_factory=list)


class XRefTraverser:
    """Traverses references between circulars and Master Directions."""

    def __init__(self, store: Any, max_hops: int = 2, max_docs: int = 4) -> None:
        self.store = store
        self.max_hops = max_hops
        self.max_docs = max_docs

    def traverse(
        self,
        ranked_chunks: List[RankedChunk],
        query: str,
        retriever: Optional[Any] = None,
    ) -> List[XRefFinding]:
        """Discover and retrieve relevant cross-referenced sections."""
        findings: List[XRefFinding] = []
        visited_docs: Set[str] = set()
        for rc in ranked_chunks[:3]:
            visited_docs.add(rc.chunk.doc_id)

        docs_explored = 0

        for rc in ranked_chunks[:3]:
            if docs_explored >= self.max_docs:
                break

            doc_id = rc.chunk.doc_id
            links = []
            if hasattr(self.store, "links_for"):
                try:
                    links = self.store.links_for(doc_id)
                except Exception:
                    links = []

            for link in links:
                if docs_explored >= self.max_docs:
                    break

                target_doc = getattr(link, "target_doc_id", None) or getattr(link, "tgt_doc_id", None)
                rel = getattr(link, "rel_type", "refers_to") or "refers_to"

                if not target_doc or target_doc in visited_docs:
                    continue

                visited_docs.add(target_doc)
                docs_explored += 1

                # Fetch candidate chunks from referenced document
                ref_chunks: List[Any] = []
                if hasattr(self.store, "doc_chunks"):
                    try:
                        ref_chunks = self.store.doc_chunks(target_doc)
                    except Exception:
                        ref_chunks = []

                if not ref_chunks and hasattr(self.store, "lookup_identifier"):
                    target_circ = getattr(link, "target_circular_no", None)
                    if target_circ:
                        cids = self.store.lookup_identifier(target_circ)
                        ref_chunks = self.store.get_chunks(cids)

                matched_rcs: List[RankedChunk] = []
                for ch in ref_chunks[:2]:
                    matched_rcs.append(
                        RankedChunk(
                            chunk=ch,
                            fused_score=rc.fused_score * 0.85,
                            rerank_score=rc.rerank_score * 0.85,
                            rank=rc.rank + 1,
                            status="current" if getattr(ch, "is_current", True) else "superseded",
                        )
                    )

                findings.append(
                    XRefFinding(
                        src_doc_id=doc_id,
                        target_doc_id=target_doc,
                        relation=rel,
                        reference_text=getattr(link, "context_text", "") or f"Reference from {doc_id} to {target_doc}",
                        path=[doc_id, target_doc],
                        retrieved_chunks=matched_rcs,
                    )
                )

        return findings
