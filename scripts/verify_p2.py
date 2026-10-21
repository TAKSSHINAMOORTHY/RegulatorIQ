"""Verification script for Phase 2: Parsing, Cleaning, Linking, and Chunking."""

from __future__ import annotations

import sys

import pandas as pd

from config.paths import (
    CHUNKS_PATH,
    DOCUMENTS_PATH,
    LINKS_PATH,
    PARSE_REPORT_MD,
)
from ingest.normalise import is_rbi_host
from scripts.state import read_state


def verify_phase_2() -> bool:
    print("==================================================")
    print(" Verifying Phase 2: Structured Docs, Links, Chunks")
    print("==================================================")
    errors: list[str] = []

    # 1. Check STATE.json
    state = read_state()
    p2 = state.get("phases", {}).get("2")
    if not p2:
        errors.append("docs/STATE.json is missing phase '2'")
    elif p2.get("status") not in ("complete", "complete_degraded"):
        errors.append(
            f"Phase 2 status is '{p2.get('status')}', expected 'complete' or 'complete_degraded'"
        )
    else:
        print("✓ docs/STATE.json phase 2 status is valid")

    # 2. Check Parquet files
    for name, path in [
        ("documents.parquet", DOCUMENTS_PATH),
        ("links.parquet", LINKS_PATH),
        ("chunks.parquet", CHUNKS_PATH),
    ]:
        if not path.exists():
            errors.append(f"Missing required parquet file: {path}")
        else:
            print(f"✓ Found {name}: {path}")

    if errors:
        print("\n❌ Phase 2 Verification FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False

    df_docs = pd.read_parquet(DOCUMENTS_PATH)
    df_links = pd.read_parquet(LINKS_PATH)
    df_chunks = pd.read_parquet(CHUNKS_PATH)

    print(f"✓ Documents count: {len(df_docs)}")
    print(f"✓ Links count: {len(df_links)}")
    print(f"✓ Chunks count: {len(df_chunks)}")

    # 3. Check every chunk.doc_id exists in documents.parquet
    valid_doc_ids = set(df_docs["doc_id"].tolist())
    for chunk_doc_id in df_chunks["doc_id"]:
        if chunk_doc_id not in valid_doc_ids:
            errors.append(f"Orphan chunk found with doc_id={chunk_doc_id}")
            break
    print("✓ All chunk doc_ids exist in documents.parquet")

    # 4. Check chunk rules: non-empty text, source_url ending in *.rbi.org.in host, token_count <= 512
    for idx, row in df_chunks.iterrows():
        text = str(row["text"]).strip()
        url = str(row["source_url"]).strip()
        tokens = int(row["token_count"])

        if not text:
            errors.append(f"Chunk at index {idx} has empty text")
            break
        if not is_rbi_host(url):
            errors.append(f"Chunk at index {idx} has non-rbi source_url: {url}")
            break
        if tokens > 512:
            errors.append(f"Chunk at index {idx} exceeds 512 max tokens ({tokens} tokens)")
            break
    print("✓ All chunks have non-empty text, valid rbi.org.in source_url, and token_count <= 512")

    # 5. Check chunk_ids are unique
    chunk_ids = df_chunks["chunk_id"].tolist()
    if len(chunk_ids) != len(set(chunk_ids)):
        errors.append(
            f"Duplicate chunk_ids detected! ({len(chunk_ids)} total vs {len(set(chunk_ids))} unique)"
        )
    else:
        print("✓ All chunk_ids are strictly unique")

    # 6. Check reports/parse_report.md
    if not PARSE_REPORT_MD.exists():
        errors.append(f"Parse report missing: {PARSE_REPORT_MD}")
    else:
        print(f"✓ Parse report exists: {PARSE_REPORT_MD}")

    if errors:
        print("\n❌ Phase 2 Verification FAILED with errors:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("\n✅ Phase 2 Verification PASSED successfully!")
    return True


if __name__ == "__main__":
    success = verify_phase_2()
    sys.exit(0 if success else 1)
