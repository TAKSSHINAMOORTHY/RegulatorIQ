"""Baseline RAG Pipeline for RegulatorIQ.

Deliberately naive pipeline:
1. store.search_dense(question, k=5, filters=None)
2. Build context: numbered chunks with metadata
3. Single LLM call (or extractive fallback)
4. Parse {answer, citations[], refused}
5. Return standardized RagAnswer
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agent.llm import LLM
from agent.types import RagAnswer
from config.paths import CONFIG_DIR
from retrieval.index_store import IndexStore


def load_refusal_patterns() -> List[str]:
    """Load regex refusal patterns from config."""
    pat_file = CONFIG_DIR / "refusal_patterns.yaml"
    if pat_file.exists():
        with open(pat_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("patterns", [])
    return [
        "(?i)cannot find",
        "(?i)not available in the provided documents",
        "(?i)outside the scope",
    ]


class BaselineRAG:
    """Deliberately naive baseline RAG system without reranking, rewriting, or agent logic."""

    def __init__(
        self,
        index_store: IndexStore,
        llm: Optional[LLM] = None,
        prompt_path: Optional[Path] = None,
    ) -> None:
        self.index_store = index_store
        self.llm = llm or LLM()
        self.prompt_path = prompt_path or (Path(__file__).parent / "prompts" / "baseline.v1.txt")
        if self.prompt_path.exists():
            self.prompt_template = self.prompt_path.read_text(encoding="utf-8")
        else:
            self.prompt_template = (
                "Context:\n{context}\n\nQuestion: {question}\n\n"
                "Return JSON with answer, citations, and refused."
            )
        self.prompt_hash = hashlib.sha256(self.prompt_template.encode("utf-8")).hexdigest()[:12]
        self.refusal_patterns = [re.compile(p) for p in load_refusal_patterns()]

    def answer(self, question: str, k: int = 5) -> RagAnswer:
        """Run the naive baseline pipeline on the input question."""
        t_start = time.perf_counter()

        # 1. Dense retrieval top-k
        t0_ret = time.perf_counter()
        hits = self.index_store.search_dense(question, k=k, filters=None)
        t_ret = time.perf_counter() - t0_ret

        retrieved_chunks = []
        retrieved_meta = []
        for rank, hit in enumerate(hits, start=1):
            chunk = self.index_store.metadata_store.get_chunk(hit.chunk_id)
            if chunk:
                retrieved_chunks.append(chunk)
                retrieved_meta.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "score": hit.score,
                        "rank": rank,
                        "title": chunk.title,
                        "circular_no": chunk.circular_no,
                        "source_url": chunk.source_url,
                    }
                )

        if not retrieved_chunks:
            return RagAnswer(
                answer="No relevant regulatory documents were found.",
                citations=[],
                refused=True,
                retrieved=[],
                timings={
                    "total_s": round(time.perf_counter() - t_start, 3),
                    "retrieval_s": round(t_ret, 3),
                    "generation_s": 0.0,
                },
                usage={"in": 0, "out": 0},
                provider=self.llm.provider.name,
                model=self.llm.provider.model,
            )

        # 2. Build context
        context_blocks = []
        for i, chunk in enumerate(retrieved_chunks, start=1):
            meta_str = (
                f"[{i}] Title: {chunk.title} | "
                f"Circular No: {chunk.circular_no or 'N/A'} | "
                f"Date: {chunk.issue_date or 'N/A'} | "
                f"Ref: {chunk.para_ref or 'N/A'}"
            )
            context_blocks.append(f"{meta_str}\nText:\n{chunk.text}")
        context_text = "\n\n".join(context_blocks)

        prompt_content = self.prompt_template.replace("{context}", context_text).replace(
            "{question}", question
        )

        # 3. LLM Generation
        t0_gen = time.perf_counter()
        llm_res = self.llm.generate(
            messages=[{"role": "user", "content": prompt_content}],
            max_tokens=512,
            temperature=0.0,
            json_schema={"type": "object"},
        )
        t_gen = time.perf_counter() - t0_gen

        # 4. Parse response
        answer_text = ""
        refused = False
        raw_citations: List[Any] = []

        if llm_res.parsed_json and isinstance(llm_res.parsed_json, dict):
            answer_text = str(llm_res.parsed_json.get("answer", "")).strip()
            refused = bool(llm_res.parsed_json.get("refused", False))
            raw_cits = llm_res.parsed_json.get("citations", [])
            if isinstance(raw_cits, list):
                raw_citations = raw_cits
        else:
            answer_text = llm_res.text.strip()
            # Extract bracket citations from raw text like [1], [2]
            found = re.findall(r"\[(\d+)\]", answer_text)
            raw_citations = [int(x) for x in found]

        # Check refusal patterns if not explicitly refused
        if not refused:
            for pat in self.refusal_patterns:
                if pat.search(answer_text):
                    refused = True
                    break

        # 5. Map citations to retrieved chunks
        resolved_citations: List[Dict[str, Any]] = []
        # If citations weren't explicitly in JSON, extract from answer text
        if not raw_citations:
            found = re.findall(r"\[(\d+)\]", answer_text)
            raw_citations = [int(x) for x in found]

        seen_refs = set()
        for c in raw_citations:
            try:
                ref_num = int(c)
            except (ValueError, TypeError):
                continue

            if ref_num in seen_refs:
                continue
            seen_refs.add(ref_num)

            if 1 <= ref_num <= len(retrieved_chunks):
                ch = retrieved_chunks[ref_num - 1]
                resolved_citations.append(
                    {
                        "ref_num": ref_num,
                        "chunk_id": ch.chunk_id,
                        "doc_id": ch.doc_id,
                        "circular_no": ch.circular_no,
                        "title": ch.title,
                        "issue_date": ch.issue_date,
                        "para_ref": ch.para_ref,
                        "page_start": ch.page_start,
                        "source_url": ch.source_url,
                    }
                )
            else:
                # Invalid citation reference
                resolved_citations.append(
                    {
                        "ref_num": ref_num,
                        "chunk_id": None,
                        "error": "invalid_citation_index",
                    }
                )

        timings = {
            "total_s": round(time.perf_counter() - t_start, 3),
            "retrieval_s": round(t_ret, 3),
            "generation_s": round(t_gen, 3),
        }

        return RagAnswer(
            answer=answer_text,
            citations=resolved_citations,
            refused=refused,
            retrieved=retrieved_meta,
            timings=timings,
            usage=llm_res.usage,
            provider=llm_res.provider,
            model=llm_res.model,
        )
