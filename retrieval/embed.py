"""Embedding pipeline with multiple backends, query prefixes, L2 normalization,
quantisation, and atomic shard caching.

Supported Embedders:
1. FastEmbedEmbedder: Default CPU ONNX runtime (fastembed)
2. STEmbedder: Fallback sentence-transformers (PyTorch CPU)
3. HashingEmbedder: Degraded last-resort offline HashingVectorizer + TruncatedSVD
4. FakeEmbedder: Deterministic unit vectors for offline testing (no network)
"""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from config.paths import EMBED_CACHE_DIR
from config.settings import settings


def load_model_config(model_name: str) -> Dict[str, Any]:
    """Load model configuration from config/models.yaml."""
    models_yaml = Path(__file__).resolve().parent.parent / "config" / "models.yaml"
    if models_yaml.exists():
        with open(models_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            models = data.get("models", {})
            if model_name in models:
                res = models[model_name]
                return dict(res) if isinstance(res, dict) else {}
    # Default fallback config
    return {
        "dim": 384,
        "max_tokens": 512,
        "query_prefix": (
            "Represent this sentence for searching relevant passages: "
            if "bge" in model_name.lower()
            else ""
        ),
        "doc_prefix": "",
    }


def normalize_l2(vectors: np.ndarray) -> np.ndarray:
    """Normalize vectors to unit length (L2 norm = 1.0)."""
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1e-12, norms)
    return (vectors / norms).astype(np.float32)


class BaseEmbedder(ABC):
    """Abstract base class for all embedding adapters."""

    name: str
    dim: int
    max_tokens: int
    query_prefix: str
    doc_prefix: str
    degraded: bool = False
    revision: str = "v1"

    @abstractmethod
    def embed_documents(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        """Embed a list of document texts. Returns (N, dim) normalized float32 array."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query string. Returns (dim,) normalized float32 array."""
        pass


class FastEmbedEmbedder(BaseEmbedder):
    """Default embedder using fastembed ONNX runtime on CPU."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self.name = model_name
        cfg = load_model_config(model_name)
        self.dim = cfg.get("dim", 384)
        self.max_tokens = cfg.get("max_tokens", 512)
        self.query_prefix = cfg.get("query_prefix", "")
        self.doc_prefix = cfg.get("doc_prefix", "")
        self.degraded = False
        self.revision = "fastembed-0.9"

        # Initialize fastembed TextEmbedding
        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)

        # Prefix documents if configured (BGE documents have no prefix)
        prefixed_texts = [f"{self.doc_prefix}{t}" if self.doc_prefix else t for t in texts]

        all_vecs: List[np.ndarray] = []
        for vec in self._model.embed(prefixed_texts, batch_size=batch_size):
            all_vecs.append(np.array(vec, dtype=np.float32))

        matrix = np.vstack(all_vecs)
        return normalize_l2(matrix)

    def embed_query(self, text: str) -> np.ndarray:
        full_query = f"{self.query_prefix}{text}" if self.query_prefix else text
        vec = next(iter(self._model.embed([full_query])))
        arr = np.array(vec, dtype=np.float32).reshape(1, -1)
        res = normalize_l2(arr)[0]
        return np.asarray(res, dtype=np.float32)


class STEmbedder(BaseEmbedder):
    """Fallback embedder using sentence-transformers (PyTorch CPU)."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.name = model_name
        cfg = load_model_config(model_name)
        self.dim = cfg.get("dim", 384)
        self.max_tokens = cfg.get("max_tokens", 256)
        self.query_prefix = cfg.get("query_prefix", "")
        self.doc_prefix = cfg.get("doc_prefix", "")
        self.degraded = False
        self.revision = "st-v2"
        self._model = SentenceTransformer(model_name, device="cpu")

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        prefixed = [f"{self.doc_prefix}{t}" if self.doc_prefix else t for t in texts]
        vecs = self._model.encode(
            prefixed, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True
        )
        return np.asarray(vecs, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        query_text = f"{self.query_prefix}{text}" if self.query_prefix else text
        vec = self._model.encode([query_text], show_progress_bar=False, normalize_embeddings=True)
        return np.asarray(vec[0], dtype=np.float32)


class HashingEmbedder(BaseEmbedder):
    """Last-resort offline fallback using HashingVectorizer + TruncatedSVD (degraded)."""

    def __init__(self, dim: int = 384) -> None:
        self.name = "hashing"
        self.dim = dim
        self.max_tokens = 512
        self.query_prefix = ""
        self.doc_prefix = ""
        self.degraded = True
        self.revision = "hash-svd-v1"

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)

        # Deterministic feature hashing to dim
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            words = text.lower().split()
            for w in words:
                h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 16) % 2 == 0 else -1.0
                matrix[i, idx] += sign
        return normalize_l2(matrix)

    def embed_query(self, text: str) -> np.ndarray:
        vecs = self.embed_documents([text])
        return np.asarray(vecs[0], dtype=np.float32)


class FakeEmbedder(BaseEmbedder):
    """Deterministic, seeded unit-vector generator for fast tests without network."""

    def __init__(self, dim: int = 384) -> None:
        self.name = "fake"
        self.dim = dim
        self.max_tokens = 512
        self.query_prefix = ""
        self.doc_prefix = ""
        self.degraded = False
        self.revision = "fake-v1"

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            # Seed from sha256 of text
            seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)
            raw = rng.randn(self.dim).astype(np.float32)
            matrix[i] = raw
        return normalize_l2(matrix)

    def embed_query(self, text: str) -> np.ndarray:
        vecs = self.embed_documents([text])
        return np.asarray(vecs[0], dtype=np.float32)


def get_embedder(model_name: Optional[str] = None, prefer_fake: bool = False) -> BaseEmbedder:
    """Factory to instantiate the appropriate embedder adapter."""
    if prefer_fake:
        return FakeEmbedder()

    target_name = model_name or settings.EMBED_MODEL_NAME

    # 1. Try FastEmbed
    try:
        return FastEmbedEmbedder(model_name=target_name)
    except Exception:
        # 2. Try SentenceTransformers
        try:
            return STEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            # 3. Fall back to HashingEmbedder (degraded)
            return HashingEmbedder(dim=384)


def quantize_vectors(
    vectors: np.ndarray,
    quant: str = "fp16",
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Quantize vectors to fp16 or int8.

    Returns:
        (quantized_array, quantization_metadata)
    """
    quant = quant.lower()
    if quant == "none" or quant == "fp32":
        return vectors.astype(np.float32), {"quant": "none"}

    if quant == "fp16":
        return vectors.astype(np.float16), {"quant": "fp16"}

    if quant == "int8":
        # Symmetric per-vector scalar int8 quantisation
        abs_max = np.max(np.abs(vectors), axis=-1, keepdims=True)
        scale = np.where(abs_max == 0, 1.0, abs_max / 127.0).astype(np.float32)
        int8_arr = np.clip(np.round(vectors / scale), -128, 127).astype(np.int8)

        meta = {
            "quant": "int8",
            "scale": scale,
        }
        return int8_arr, meta

    raise ValueError(f"Unsupported quantisation mode: {quant}")


def dequantize_vectors(
    quantized: np.ndarray,
    meta: Dict[str, Any],
) -> np.ndarray:
    """Reconstruct float32 vectors from quantized representation."""
    quant = meta.get("quant", "none")
    if quant in ("none", "fp32"):
        return quantized.astype(np.float32)
    if quant == "fp16":
        return quantized.astype(np.float32)
    if quant == "int8":
        scale = meta["scale"]
        float_vecs = quantized.astype(np.float32) * scale
        return normalize_l2(float_vecs)
    raise ValueError(f"Unknown quantisation mode: {quant}")


class EmbeddingCache:
    """Manages resumable sharded embedding cache stored in float16."""

    SHARD_SIZE = 5000

    def __init__(self, model_slug: str, cache_dir: Optional[Path] = None) -> None:
        self.model_slug = model_slug.replace("/", "_").replace(".", "_")
        self.cache_dir = Path(cache_dir or EMBED_CACHE_DIR) / self.model_slug
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.cache_dir / "cache_index.json"
        self.index: Dict[str, Dict[str, Any]] = self._load_index()

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return dict(data) if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}

    def _save_index(self) -> None:
        tmp_file = self.index_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self.index, f)
        os.replace(tmp_file, self.index_file)

    def cache_key(self, text_for_embedding: str, model_name: str, model_rev: str) -> str:
        """sha1(text_for_embedding + model_name + model_rev)."""
        content = f"{text_for_embedding}_{model_name}_{model_rev}".encode("utf-8")
        return hashlib.sha1(content).hexdigest()

    def get_cached(self, cache_keys: List[str]) -> Tuple[Dict[str, np.ndarray], List[str]]:
        """Retrieve cached vectors for given keys.

        Returns:
            (cached_vectors_map, missing_keys)
        """
        cached_map: Dict[str, np.ndarray] = {}
        missing_keys: List[str] = []

        # Group by shard for efficient loading
        shard_requests: Dict[int, List[Tuple[str, int]]] = {}

        for k in cache_keys:
            if k in self.index:
                shard_id = self.index[k]["shard_id"]
                row_idx = self.index[k]["row_idx"]
                if shard_id not in shard_requests:
                    shard_requests[shard_id] = []
                shard_requests[shard_id].append((k, row_idx))
            else:
                missing_keys.append(k)

        # Load shards
        for shard_id, entries in shard_requests.items():
            shard_path = self.cache_dir / f"shard_{shard_id}.npy"
            if shard_path.exists():
                shard_arr = np.load(shard_path, mmap_mode="r")
                for k, row_idx in entries:
                    if row_idx < len(shard_arr):
                        cached_map[k] = np.array(shard_arr[row_idx], dtype=np.float32)
                    else:
                        missing_keys.append(k)
            else:
                for k, _ in entries:
                    missing_keys.append(k)

        return cached_map, missing_keys

    def put_vectors(
        self,
        key_vector_pairs: List[Tuple[str, np.ndarray]],
    ) -> None:
        """Store new vectors in atomic shards."""
        if not key_vector_pairs:
            return

        # Determine next shard ID
        existing_shards = [
            int(p.stem.split("_")[1])
            for p in self.cache_dir.glob("shard_*.npy")
            if p.stem.split("_")[1].isdigit()
        ]
        current_shard_id = max(existing_shards) if existing_shards else 0

        # Load current shard if exists and has capacity
        current_shard_path = self.cache_dir / f"shard_{current_shard_id}.npy"
        current_vectors: List[np.ndarray] = []
        if current_shard_path.exists():
            current_vectors = list(np.load(current_shard_path))

        for key, vec in key_vector_pairs:
            if len(current_vectors) >= self.SHARD_SIZE:
                # Save full shard atomically
                self._write_shard(current_shard_id, current_vectors)
                current_shard_id += 1
                current_vectors = []

            row_idx = len(current_vectors)
            current_vectors.append(vec.astype(np.float16))
            self.index[key] = {
                "shard_id": current_shard_id,
                "row_idx": row_idx,
            }

        if current_vectors:
            self._write_shard(current_shard_id, current_vectors)

        self._save_index()

    def _write_shard(self, shard_id: int, vectors: List[np.ndarray]) -> None:
        """Write shard array atomically."""
        shard_path = self.cache_dir / f"shard_{shard_id}.npy"
        tmp_path = shard_path.with_suffix(".tmp.npy")
        arr = np.vstack(vectors).astype(np.float16)
        np.save(tmp_path, arr)
        os.replace(tmp_path, shard_path)
