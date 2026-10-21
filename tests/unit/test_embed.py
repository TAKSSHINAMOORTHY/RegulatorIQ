"""Unit tests for embedding adapters, quantisation, and atomic shard caching."""

import numpy as np

from retrieval.embed import (
    EmbeddingCache,
    FakeEmbedder,
    HashingEmbedder,
    dequantize_vectors,
    get_embedder,
    normalize_l2,
    quantize_vectors,
)


def test_fake_embedder():
    fe = FakeEmbedder(dim=384)
    assert fe.dim == 384
    assert fe.name == "fake"
    assert not fe.degraded

    docs = ["Capital adequacy rules for commercial banks", "Priority sector lending guidelines"]
    vecs = fe.embed_documents(docs)
    assert vecs.shape == (2, 384)
    # Check L2 unit length
    for v in vecs:
        assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-5)

    # Query embedding
    q_vec = fe.embed_query("Capital adequacy")
    assert q_vec.shape == (384,)
    assert np.isclose(np.linalg.norm(q_vec), 1.0, atol=1e-5)

    # Determinism
    vecs_repeat = fe.embed_documents(docs)
    np.testing.assert_allclose(vecs, vecs_repeat)


def test_hashing_embedder():
    he = HashingEmbedder(dim=384)
    assert he.dim == 384
    assert he.degraded is True
    vecs = he.embed_documents(["KYC compliance rules", "Risk management"])
    assert vecs.shape == (2, 384)
    assert np.isclose(np.linalg.norm(vecs[0]), 1.0, atol=1e-5)


def test_quantisation_roundtrip():
    # Test symmetric int8 scalar quantisation error bound
    rng = np.random.RandomState(42)
    raw = rng.randn(20, 384).astype(np.float32)
    vecs = normalize_l2(raw)

    q_int8, meta_int8 = quantize_vectors(vecs, quant="int8")
    assert q_int8.dtype == np.int8
    assert meta_int8["quant"] == "int8"

    rec_int8 = dequantize_vectors(q_int8, meta_int8)
    assert rec_int8.shape == vecs.shape
    cos_sims = np.sum(vecs * rec_int8, axis=-1)
    mean_cos = float(np.mean(cos_sims))
    assert mean_cos >= 0.99, f"int8 mean cosine similarity {mean_cos} < 0.99"

    # Test fp16
    q_fp16, meta_fp16 = quantize_vectors(vecs, quant="fp16")
    assert q_fp16.dtype == np.float16
    rec_fp16 = dequantize_vectors(q_fp16, meta_fp16)
    np.testing.assert_allclose(vecs, rec_fp16, atol=1e-3)


def test_embedding_cache(tmp_path):
    cache = EmbeddingCache(model_slug="test_model", cache_dir=tmp_path)
    key1 = cache.cache_key("test chunk text 1", "test_model", "v1")
    key2 = cache.cache_key("test chunk text 2", "test_model", "v1")

    cached_map, missing = cache.get_cached([key1, key2])
    assert len(cached_map) == 0
    assert missing == [key1, key2]

    # Put vectors
    vec1 = normalize_l2(np.ones((1, 384), dtype=np.float32))[0]
    vec2 = normalize_l2(np.full((1, 384), 2.0, dtype=np.float32))[0]
    cache.put_vectors([(key1, vec1), (key2, vec2)])

    # Retrieve again
    cached_map2, missing2 = cache.get_cached([key1, key2])
    assert len(missing2) == 0
    assert key1 in cached_map2
    assert key2 in cached_map2
    np.testing.assert_allclose(cached_map2[key1], vec1, atol=1e-3)


def test_get_embedder_factory():
    fake = get_embedder(prefer_fake=True)
    assert isinstance(fake, FakeEmbedder)


def test_fastembed_embedder():
    from retrieval.embed import FastEmbedEmbedder, load_model_config

    cfg = load_model_config("BAAI/bge-small-en-v1.5")
    assert cfg["dim"] == 384
    assert "query_prefix" in cfg

    fe = FastEmbedEmbedder("BAAI/bge-small-en-v1.5")
    vecs = fe.embed_documents(["Sample regulatory clause", "Another text"])
    assert vecs.shape == (2, 384)
    q_vec = fe.embed_query("Query search")
    assert q_vec.shape == (384,)
    empty_vecs = fe.embed_documents([])
    assert empty_vecs.shape == (0, 384)


def test_quantize_edge_cases():
    import pytest

    vecs = np.ones((2, 384), dtype=np.float32)
    # fp32 / none
    q_none, meta_none = quantize_vectors(vecs, quant="none")
    assert meta_none["quant"] == "none"
    dec_none = dequantize_vectors(q_none, meta_none)
    assert dec_none.shape == (2, 384)

    # Invalid
    with pytest.raises(ValueError):
        quantize_vectors(vecs, quant="invalid_quant")

    with pytest.raises(ValueError):
        dequantize_vectors(vecs, {"quant": "unknown"})


def test_get_embedder_fallbacks(monkeypatch):
    # Test fallback to STEmbedder or HashingEmbedder when FastEmbed fails
    monkeypatch.setattr("retrieval.embed.FastEmbedEmbedder", None)
    emb = get_embedder("nonexistent_model")
    assert emb.degraded or emb.name.startswith("sentence-transformers")
