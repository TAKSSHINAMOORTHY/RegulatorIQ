"""Unit and integration tests for IndexStore, integrity checking, and concurrency."""

import concurrent.futures

import pytest

from retrieval.build_index import build_index
from retrieval.embed import FakeEmbedder
from retrieval.index_store import IndexIntegrityError, IndexStore
from retrieval.store import Filters


def test_index_store_integration(tmp_path):
    chunks = [
        {
            "chunk_id": f"chunk_{i}",
            "doc_id": f"doc_{i // 2}",
            "ordinal": (i % 2) + 1,
            "text": f"Regulatory sentence number {i} regarding banking norms and capital adequacy.",
            "text_for_embedding": f"[Circular] Title {i} | RBI/2025-26/{100 + i} | Regulatory sentence number {i}",
            "doc_type": "Circular",
            "title": f"Title {i}",
            "circular_no": f"RBI/2025-26/{100 + i}",
            "issue_date": "2025-01-10",
            "valid_from": "2025-01-10",
            "valid_to": None,
            "is_current": True if i % 2 == 0 else False,
            "validity_confidence": "high",
            "topics": ["capital_adequacy"],
            "applicability_entities": ["commercial_banks"],
            "source_url": "https://rbi.org.in/test.pdf",
            "token_count": 50,
        }
        for i in range(10)
    ]

    import pyarrow as pa
    import pyarrow.parquet as pq

    chunks_file = tmp_path / "chunks.parquet"
    table = pa.Table.from_pylist(chunks)
    pq.write_table(table, chunks_file)

    fe = FakeEmbedder(dim=384)
    index_out = tmp_path / "artifacts" / "index"

    # Build index with FakeEmbedder
    store, manifest = build_index(
        chunks_path=chunks_file,
        embedder=fe,
        vector_backend="faiss",
        quantisation="fp16",
        output_index_dir=index_out,
        use_cache=False,
    )

    assert store.chunk_count == 10
    assert store.version == manifest["version"]

    # Test 1: Dense Search
    hits = store.search_dense("banking norms", k=3)
    assert len(hits) == 3
    assert hits[0].rank == 1
    assert hits[0].score <= 1.01

    # Test 2: Masked Dense Search (only is_current=True)
    hits_curr = store.search_dense("banking norms", k=10, filters=Filters(is_current=True))
    for h in hits_curr:
        c = store.metadata_store.get_chunk(h.chunk_id)
        assert c is not None
        assert c.is_current is True

    # Test 3: BM25 Search
    hits_bm25 = store.search_bm25("capital adequacy", k=3)
    assert len(hits_bm25) > 0

    # Test 4: Identifier Lookup
    found_ids = store.lookup_identifier("RBI/2025-26/102")
    assert "chunk_2" in found_ids

    # Test 5: Neighbors
    n = store.neighbors("chunk_0", window=1)
    # doc_0 has chunk_0 and chunk_1
    assert any(c.chunk_id == "chunk_0" for c in n)
    assert any(c.chunk_id == "chunk_1" for c in n)

    # Test 6: Doc Chunks
    dc = store.doc_chunks("doc_0")
    assert len(dc) == 2
    assert dc[0].ordinal <= dc[1].ordinal

    # Test 7: Integrity error on tampered file byte
    vector_file = list((index_out / store.version / "dense").glob("vectors.*.npy"))[0]
    with open(vector_file, "r+b") as f:
        f.seek(10)
        byte = f.read(1)
        f.seek(10)
        f.write(bytes([(byte[0] ^ 0xFF)]))

    with pytest.raises(IndexIntegrityError):
        IndexStore.load(index_out / store.version, verify="full")


def test_concurrency_and_read_only(tmp_path):
    chunks = [
        {
            "chunk_id": f"c_{i}",
            "doc_id": "doc_main",
            "ordinal": i,
            "text": f"Thread safety test chunk text {i}",
            "text_for_embedding": f"Thread safety test chunk text {i}",
            "doc_type": "Circular",
            "title": "Title",
            "circular_no": "RBI/2025-26/01",
            "issue_date": "2025-01-01",
            "valid_from": "2025-01-01",
            "valid_to": None,
            "is_current": True,
            "validity_confidence": "high",
            "topics": [],
            "applicability_entities": [],
            "source_url": "https://rbi.org.in/test.pdf",
            "token_count": 20,
        }
        for i in range(20)
    ]

    import pyarrow as pa
    import pyarrow.parquet as pq

    chunks_file = tmp_path / "chunks.parquet"
    pq.write_table(pa.Table.from_pylist(chunks), chunks_file)

    fe = FakeEmbedder(dim=384)
    index_out = tmp_path / "index_dir"

    store, _ = build_index(
        chunks_path=chunks_file,
        embedder=fe,
        vector_backend="numpy",
        quantisation="fp16",
        output_index_dir=index_out,
        use_cache=False,
    )

    # Multi-threaded search
    def search_worker(query_term: str):
        h_dense = store.search_dense(f"query {query_term}", k=5)
        h_bm25 = store.search_bm25(f"test {query_term}", k=5)
        return len(h_dense), len(h_bm25)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(search_worker, str(i)) for i in range(16)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            assert res[0] > 0

    # Test stats & fast load
    stats = store.stats()
    assert stats["chunk_count"] == 20
    assert "rss_mb" in stats
    assert len(store.links_for("doc_main")) == 0
    chunks_ret = store.get_chunks(["c_0", "c_1"])
    assert len(chunks_ret) == 2

    # Fast load
    loaded_fast = IndexStore.load(index_out / store.version, verify="fast")
    assert loaded_fast.chunk_count == 20
