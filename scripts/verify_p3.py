"""Verification script for Phase 3: Embeddings, BM25, Vector Store, and Index Artifact.

Verifies:
1. docs/STATE.json contains valid phase 3 completion data.
2. INDEX_POINTER exists and names a version whose manifest validates and files match sha256 checksums.
3. IndexStore.load(verify="full") succeeds and chunk_count equals chunks.parquet.
4. Part F hard checks pass (identifier exact match 100%, filter correctness 100%, self-retrieval >= threshold).
5. reports/index_report.md exists.
"""

from __future__ import annotations

import json
import sys

import pyarrow.parquet as pq

from config.paths import (
    CHUNKS_PATH,
    INDEX_DIR,
    INDEX_POINTER,
    INDEX_REPORT_JSON,
    INDEX_REPORT_MD,
    STATE_FILE_PATH,
)
from retrieval.index_store import IndexStore


def verify_phase_3() -> None:
    errors: list[str] = []
    print("=" * 50)
    print(" Verifying Phase 3: Embeddings & Index Artifact")
    print("=" * 50)

    # 1. Check STATE.json
    if not STATE_FILE_PATH.exists():
        errors.append(f"Missing {STATE_FILE_PATH}")
    else:
        with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
        p3 = state.get("phases", {}).get("3")
        if not p3:
            errors.append("docs/STATE.json is missing phase '3'")
        elif p3.get("status") not in ("complete", "complete_degraded"):
            errors.append(f"Phase 3 status is invalid: {p3.get('status')}")
        else:
            print("✓ docs/STATE.json phase 3 status is valid")

    # 2. Check INDEX_POINTER
    if not INDEX_POINTER.exists():
        errors.append(f"INDEX_POINTER file missing: {INDEX_POINTER}")
        version_str = None
    else:
        with open(INDEX_POINTER, "r", encoding="utf-8") as f:
            version_str = f.read().strip()
        version_dir = INDEX_DIR / version_str
        if not version_dir.exists():
            errors.append(f"INDEX_POINTER references nonexistent version dir: {version_dir}")
        else:
            print(f"✓ Found active index version: {version_str}")

    # 3. Load IndexStore with full sha256 verification
    try:
        store = IndexStore.load(verify="full")
        print("✓ IndexStore.load(verify='full') succeeded with all sha256 checks passing")
    except Exception as e:
        errors.append(f"IndexStore.load failed: {e}")
        store = None

    # 4. Check chunk count matches chunks.parquet
    if store is not None and CHUNKS_PATH.exists():
        chunks_table = pq.read_table(CHUNKS_PATH)
        expected_count = len(chunks_table)
        if store.chunk_count != expected_count:
            errors.append(
                f"Index chunk count ({store.chunk_count}) != chunks.parquet count ({expected_count})"
            )
        else:
            print(
                f"✓ Index chunk count ({store.chunk_count}) strictly matches chunks.parquet ({expected_count})"
            )

    # 5. Check reports/index_report.json and .md
    if not INDEX_REPORT_MD.exists():
        errors.append(f"Missing report: {INDEX_REPORT_MD}")
    else:
        print(f"✓ Index report exists: {INDEX_REPORT_MD}")

    if not INDEX_REPORT_JSON.exists():
        errors.append(f"Missing report json: {INDEX_REPORT_JSON}")
    else:
        with open(INDEX_REPORT_JSON, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        # Part F hard checks
        ident_res = report_data.get("identifier_exact_match", {})
        if not ident_res.get("passed", False):
            errors.append(
                f"Part F Hard Check Failed: Identifier match rate = {ident_res.get('match_rate')} (requires 100%)"
            )
        else:
            print("✓ Identifier exact match passed (100%)")

        filter_res = report_data.get("filter_correctness", {})
        if not filter_res.get("passed", False):
            errors.append("Part F Hard Check Failed: Filter correctness failed")
        else:
            print("✓ Filter correctness passed (100%)")

        self_res = report_data.get("self_retrieval", {})
        if not self_res.get("dense_target_met", False):
            errors.append(
                f"Part F Check Warn/Fail: Dense recall@5 = {self_res.get('dense_recall_at_5')}"
            )
        else:
            print(f"✓ Self-retrieval (Dense) passed: {self_res.get('dense_recall_at_5'):.1%}")

        if not self_res.get("bm25_target_met", False):
            errors.append(
                f"Part F Check Warn/Fail: BM25 recall@5 = {self_res.get('bm25_recall_at_5')}"
            )
        else:
            print(f"✓ Self-retrieval (BM25) passed: {self_res.get('bm25_recall_at_5'):.1%}")

    if errors:
        print("\n❌ Phase 3 Verification FAILED:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print("\n✅ Phase 3 Verification PASSED successfully!\n")


if __name__ == "__main__":
    verify_phase_3()
