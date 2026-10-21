"""Stable IndexStore interface for dense vector, BM25, and metadata retrieval.

This module is the ONLY public interface imported by later phases (Prompts 4 to 10).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pyarrow.parquet as pq

from config.paths import (
    INDEX_DIR,
    INDEX_POINTER,
    LINKS_PATH,
)
from config.settings import settings
from retrieval.embed import (
    BaseEmbedder,
    FakeEmbedder,
    HashingEmbedder,
    dequantize_vectors,
    get_embedder,
    normalize_l2,
)
from retrieval.lexical import DualBM25Index, IdentifierIndex
from retrieval.store import Chunk, Filters, MetadataStore


class IndexIntegrityError(Exception):
    """Raised when index files are missing, corrupted, or have sha256/size mismatch."""

    pass


@dataclass
class Hit:
    """Retrieval search hit."""

    chunk_id: str
    score: float
    rank: int


@dataclass
class Link:
    """Supersession or reference graph link."""

    src_doc_id: str
    relation: str
    dst_ref_text: Optional[str]
    dst_doc_id: Optional[str]
    evidence_text: Optional[str]
    confidence: float
    resolved: bool
    method: str


def compute_file_sha256(filepath: Path) -> str:
    """Compute sha256 checksum of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class IndexStore:
    """Unified retrieval store holding dense vectors, BM25, identifiers, and metadata."""

    def __init__(
        self,
        index_dir: Path,
        manifest: Dict[str, Any],
        embedder: BaseEmbedder,
        metadata_store: MetadataStore,
        bm25_index: DualBM25Index,
        identifier_index: IdentifierIndex,
        vectors: np.ndarray,
        quant_meta: Dict[str, Any],
        vector_backend: str = "faiss",
        faiss_index: Any = None,
        qdrant_client: Any = None,
        load_seconds: float = 0.0,
    ) -> None:
        self.index_dir = Path(index_dir)
        self._manifest = manifest
        self.embedder = embedder
        self.metadata_store = metadata_store
        self.bm25_index = bm25_index
        self.identifier_index = identifier_index
        self.vectors = vectors
        self.quant_meta = quant_meta
        self.vector_backend = vector_backend
        self.faiss_index = faiss_index
        self.qdrant_client = qdrant_client
        self._load_seconds = load_seconds
        self._links_cache: Optional[Dict[str, List[Link]]] = None

    @property
    def manifest(self) -> Dict[str, Any]:
        """Index manifest metadata dictionary."""
        return self._manifest

    @property
    def version(self) -> str:
        """Index version string."""
        return str(self._manifest.get("version", "unknown"))

    @property
    def chunk_count(self) -> int:
        """Total number of indexed chunks."""
        return len(self.metadata_store)

    def __len__(self) -> int:
        return len(self.metadata_store)

    @classmethod
    def load(
        cls,
        path: Optional[Union[str, Path]] = None,
        verify: str = "fast",
    ) -> IndexStore:
        """Load an IndexStore from disk.

        Args:
            path: Optional directory path. If None, resolves from INDEX_POINTER.
            verify: "fast" (file presence + sizes) or "full" (sha256 checksums).
        """
        start_time = time.perf_counter()

        if path is None:
            if not INDEX_POINTER.exists():
                raise FileNotFoundError(f"Index pointer file missing: {INDEX_POINTER}")
            with open(INDEX_POINTER, "r", encoding="utf-8") as f:
                version_str = f.read().strip()
            target_dir = INDEX_DIR / version_str
        else:
            target_dir = Path(path)

        if not target_dir.exists():
            raise FileNotFoundError(f"Index directory does not exist: {target_dir}")

        manifest_file = target_dir / "manifest.json"
        if not manifest_file.exists():
            raise IndexIntegrityError(f"Missing manifest.json in {target_dir}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            try:
                manifest = json.load(f)
            except Exception as e:
                raise IndexIntegrityError(f"Failed to parse manifest.json: {e}")

        # Verification
        files_spec = manifest.get("files", [])
        for file_info in files_spec:
            rel_path = file_info["path"]
            fpath = target_dir / rel_path
            if not fpath.exists():
                raise IndexIntegrityError(f"Corrupted index: missing expected file {rel_path}")

            actual_size = fpath.stat().st_size
            expected_size = file_info.get("bytes")
            if expected_size is not None and actual_size != expected_size:
                raise IndexIntegrityError(
                    f"Corrupted index: size mismatch on {rel_path} (got {actual_size}, expected {expected_size})"
                )

            if verify == "full":
                expected_sha = file_info.get("sha256")
                if expected_sha:
                    actual_sha = compute_file_sha256(fpath)
                    if actual_sha != expected_sha:
                        raise IndexIntegrityError(f"Corrupted index: sha256 mismatch on {rel_path}")

        # 1. Load Embedder
        emb_info = manifest.get("embedder", {})
        emb_name = emb_info.get("name", settings.EMBED_MODEL_NAME)
        embedder: BaseEmbedder
        if emb_name == "fake":
            embedder = FakeEmbedder(dim=emb_info.get("dim", 384))
        elif emb_name == "hashing":
            embedder = HashingEmbedder(dim=emb_info.get("dim", 384))
        else:
            embedder = get_embedder(model_name=emb_name)

        # 2. Load Metadata and Text Blob Store
        meta_dir = target_dir / "meta"
        metadata_store = MetadataStore.load(meta_dir)

        # 3. Load BM25 Index
        lex_dir = target_dir / "lexical"
        bm25_index = DualBM25Index.load(lex_dir)

        # 4. Load Identifier Index
        ident_path = lex_dir / "identifiers.json.zst"
        identifier_index = IdentifierIndex.load(ident_path)

        # 5. Load Vectors and Dense Backend
        dense_dir = target_dir / "dense"
        quant_info = manifest.get("quantisation", {})

        # Find vector npy file
        npy_files = list(dense_dir.glob("vectors.*.npy"))
        if not npy_files:
            raise IndexIntegrityError(f"No vectors array found in {dense_dir}")
        vectors_path = npy_files[0]
        vectors = np.load(vectors_path, mmap_mode="r")

        vector_backend = manifest.get("vector_backend", "faiss")
        faiss_index = None
        qdrant_client = None

        if vector_backend == "faiss":
            faiss_file = dense_dir / "faiss.index"
            if faiss_file.exists():
                import faiss

                try:
                    faiss_index = faiss.read_index(str(faiss_file))
                except Exception:
                    faiss_index = None

        elif vector_backend == "qdrant":
            qdrant_path = dense_dir / "qdrant"
            if qdrant_path.exists():
                from qdrant_client import QdrantClient

                qdrant_client = QdrantClient(path=str(qdrant_path))

        load_seconds = time.perf_counter() - start_time

        return cls(
            index_dir=target_dir,
            manifest=manifest,
            embedder=embedder,
            metadata_store=metadata_store,
            bm25_index=bm25_index,
            identifier_index=identifier_index,
            vectors=vectors,
            quant_meta=quant_info,
            vector_backend=vector_backend,
            faiss_index=faiss_index,
            qdrant_client=qdrant_client,
            load_seconds=load_seconds,
        )

    def embed_query(self, text: str) -> np.ndarray:
        """Generate normalized embedding for query."""
        return self.embedder.embed_query(text)

    def search_dense(
        self,
        query: Union[str, np.ndarray],
        k: int = 10,
        filters: Optional[Filters] = None,
    ) -> List[Hit]:
        """Dense similarity search (inner product of L2-normalized vectors)."""
        if isinstance(query, str):
            q_vec = self.embed_query(query)
        else:
            q_vec = normalize_l2(query.reshape(1, -1))[0]

        allow_mask = self.metadata_store.build_allow_mask(filters)
        total_chunks = len(self.metadata_store)

        if total_chunks == 0 or not np.any(allow_mask):
            return []

        # Backend 1: FAISS with IDSelector
        if self.vector_backend == "faiss" and self.faiss_index is not None:
            import faiss

            allowed_indices = np.where(allow_mask)[0].astype(np.int64)
            if len(allowed_indices) == 0:
                return []
            sel = faiss.IDSelectorArray(allowed_indices)
            params = faiss.SearchParameters(sel=sel)  # type: ignore[call-arg]
            effective_k = min(k, len(allowed_indices))
            distances, indices = self.faiss_index.search(
                q_vec.reshape(1, -1).astype(np.float32),
                effective_k,
                params=params,
            )
            hits: List[Hit] = []
            for rank, (idx, dist) in enumerate(zip(indices[0], distances[0]), start=1):
                if idx < 0 or idx >= total_chunks:
                    continue
                cid = self.metadata_store.chunk_ids[idx]
                hits.append(Hit(chunk_id=cid, score=round(float(dist), 5), rank=rank))
            return hits

        # Fallback / NumPy backend
        # Dequantize or cast vectors to float32
        dequant = dequantize_vectors(self.vectors, self.quant_meta)
        scores = np.dot(dequant, q_vec)

        # Apply pre-filtering allow mask directly
        scores = np.where(allow_mask, scores, -np.inf)

        allowed_count = int(np.sum(allow_mask))
        effective_k = min(k, allowed_count)
        if effective_k <= 0:
            return []

        top_indices = np.argsort(-scores)[:effective_k]

        hits = []
        for rank, idx in enumerate(top_indices, start=1):
            sc = float(scores[idx])
            if np.isneginf(sc):
                break
            cid = self.metadata_store.chunk_ids[idx]
            hits.append(Hit(chunk_id=cid, score=round(sc, 5), rank=rank))

        return hits

    def search_bm25(
        self,
        query: str,
        k: int = 10,
        filters: Optional[Filters] = None,
    ) -> List[Hit]:
        """BM25 keyword search over plain and stemmed fields."""
        allow_mask = self.metadata_store.build_allow_mask(filters)
        chunk_ids, scores, ranks = self.bm25_index.search(query, k=k, allow_mask=allow_mask)

        hits: List[Hit] = []
        for cid, sc, rk in zip(chunk_ids, scores, ranks):
            hits.append(Hit(chunk_id=cid, score=sc, rank=rk))
        return hits

    def lookup_identifier(self, text: str) -> List[str]:
        """Exact lookup of chunk IDs by circular or direction identifier."""
        return self.identifier_index.lookup(text)

    def get_chunks(self, chunk_ids: List[str]) -> List[Chunk]:
        """Retrieve full chunk objects by IDs, preserving order."""
        res: List[Chunk] = []
        for cid in chunk_ids:
            chunk = self.metadata_store.get_chunk(cid)
            if chunk is not None:
                res.append(chunk)
        return res

    def neighbors(self, chunk_id: str, window: int = 1) -> List[Chunk]:
        """Return adjacent chunk ordinals within the same document."""
        chunk = self.metadata_store.get_chunk(chunk_id)
        if chunk is None:
            return []

        doc_chunks = self.doc_chunks(chunk.doc_id)
        current_ord = chunk.ordinal

        results: List[Chunk] = []
        for c in doc_chunks:
            if abs(c.ordinal - current_ord) <= window:
                results.append(c)

        results.sort(key=lambda x: x.ordinal)
        return results

    def doc_chunks(self, doc_id: str) -> List[Chunk]:
        """Retrieve all chunks belonging to a document, sorted by ordinal."""
        allow_mask = self.metadata_store._doc_ids == doc_id
        indices = np.where(allow_mask)[0]
        chunks = [self.metadata_store.get_chunk_by_index(i) for i in indices]
        chunks.sort(key=lambda c: c.ordinal)
        return chunks

    def links_for(self, doc_id: str) -> List[Link]:
        """Lazy load and return supersession and reference links for a document."""
        if self._links_cache is None:
            self._links_cache = {}
            if LINKS_PATH.exists():
                try:
                    df = pq.read_table(LINKS_PATH).to_pylist()
                    for r in df:
                        src = r.get("src_doc_id", "")
                        link = Link(
                            src_doc_id=src,
                            relation=r.get("relation", "refers"),
                            dst_ref_text=r.get("dst_ref_text"),
                            dst_doc_id=r.get("dst_doc_id"),
                            evidence_text=r.get("evidence_text"),
                            confidence=float(r.get("confidence", 0.0)),
                            resolved=bool(r.get("resolved", False)),
                            method=r.get("method", "number_match"),
                        )
                        if src not in self._links_cache:
                            self._links_cache[src] = []
                        self._links_cache[src].append(link)
                except Exception:
                    pass

        return self._links_cache.get(doc_id, [])

    def stats(self) -> Dict[str, Any]:
        """Return runtime performance and degradation statistics."""
        import psutil

        process = psutil.Process()
        rss_bytes = process.memory_info().rss
        rss_mb = round(rss_bytes / (1024 * 1024), 2)

        return {
            "version": self.version,
            "chunk_count": self.chunk_count,
            "embedder": {
                "name": self.embedder.name,
                "dim": self.embedder.dim,
                "degraded": self.embedder.degraded,
            },
            "vector_backend": self.vector_backend,
            "quantisation": self.quant_meta.get("mode", "fp16"),
            "load_seconds": round(self._load_seconds, 3),
            "rss_mb": rss_mb,
            "degraded": self.embedder.degraded,
        }
