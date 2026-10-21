"""Unit tests for retrieval/build_index.py."""

import pyarrow as pa
import pyarrow.parquet as pq

from retrieval.build_index import (
    build_index,
    compute_version_hash,
    package_index,
    prune_old_versions,
    run_sanity_checks,
)
from retrieval.embed import FakeEmbedder


def test_compute_version_hash():
    chunks = [{"chunk_id": "c1", "text": "sample 1"}, {"chunk_id": "c2", "text": "sample 2"}]
    v1 = compute_version_hash("2.1.0", "bge", "v1", chunks, "faiss", "fp16")
    v2 = compute_version_hash("2.1.0", "bge", "v1", chunks, "faiss", "fp16")
    v3 = compute_version_hash("2.1.0", "bge", "v2", chunks, "faiss", "fp16")

    assert v1 == v2
    assert v1 != v3
    assert v1.startswith("2.1.0-bge-")


def test_build_index_and_package(tmp_path, monkeypatch):
    chunks = [
        {
            "chunk_id": f"chunk_{i}",
            "doc_id": f"doc_{i // 2}",
            "ordinal": i,
            "chunk_type": "text",
            "text": f"Regulatory sentence {i} explaining priority sector lending and capital adequacy rules.",
            "text_for_embedding": f"[Circular] Title {i} | RBI/2025-26/{100 + i} | Regulatory sentence {i}",
            "doc_type": "Circular",
            "title": f"Title {i}",
            "circular_no": f"RBI/2025-26/{100 + i}",
            "issue_date": "2025-01-10",
            "valid_from": "2025-01-10",
            "valid_to": None,
            "is_current": True,
            "validity_confidence": "high",
            "topics": ["priority_sector"],
            "applicability_entities": ["commercial_banks"],
            "source_url": "https://rbi.org.in/test.pdf",
            "token_count": 45,
        }
        for i in range(12)
    ]

    chunks_file = tmp_path / "chunks.parquet"
    pq.write_table(pa.Table.from_pylist(chunks), chunks_file)

    fe = FakeEmbedder(dim=384)
    index_out = tmp_path / "artifacts" / "index"
    dist_out = tmp_path / "artifacts" / "dist"
    pointer_file = index_out / "CURRENT"
    report_json = tmp_path / "reports" / "index_report.json"
    report_md = tmp_path / "reports" / "index_report.md"

    monkeypatch.setattr("retrieval.build_index.INDEX_DIR", index_out)
    monkeypatch.setattr("retrieval.build_index.INDEX_POINTER", pointer_file)
    monkeypatch.setattr("retrieval.build_index.DIST_DIR", dist_out)
    monkeypatch.setattr("retrieval.build_index.INDEX_REPORT_JSON", report_json)
    monkeypatch.setattr("retrieval.build_index.INDEX_REPORT_MD", report_md)

    store, manifest = build_index(
        chunks_path=chunks_file,
        embedder=fe,
        vector_backend="faiss",
        quantisation="fp16",
        output_index_dir=index_out,
        use_cache=False,
    )

    assert store.chunk_count == 12
    assert pointer_file.exists()
    assert pointer_file.read_text().strip() == store.version

    # Run sanity checks
    results = run_sanity_checks(store)
    assert results["chunk_count"] == 12
    assert results["filter_correctness"]["passed"] is True
    assert report_json.exists()
    assert report_md.exists()

    # Package index
    pkg_path = package_index(version=store.version)
    assert pkg_path.exists()
    assert (dist_out / "PENDING_PUBLISH.md").exists()

    # Prune versions
    prune_old_versions(keep_count=1)
