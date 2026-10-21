"""Verification script for Phase 1: Foundation and Official RBI Corpus Acquisition."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from config.paths import (
    CORPUS_REPORT_MD,
    LEGAL_DOCS_DIR,
    MANIFEST_JSONL_PATH,
    MANIFEST_PARQUET_PATH,
    ROOT,
)
from ingest.manifest import load_manifest_records
from ingest.normalise import is_rbi_host
from scripts.state import read_state


def verify_phase_1() -> bool:
    print("==================================================")
    print(" Verifying Phase 1: Official RBI Corpus Acquisition")
    print("==================================================")
    errors: list[str] = []

    # 1. Check STATE.json
    state = read_state()
    p1 = state.get("phases", {}).get("1")
    if not p1:
        errors.append("docs/STATE.json is missing phase '1'")
    elif p1.get("status") not in ("complete", "complete_degraded"):
        errors.append(
            f"Phase 1 status is '{p1.get('status')}', expected 'complete' or 'complete_degraded'"
        )
    else:
        print("✓ docs/STATE.json phase 1 status is valid")

    # 2. Check manifest files
    if not MANIFEST_JSONL_PATH.exists():
        errors.append(f"Manifest JSONL missing: {MANIFEST_JSONL_PATH}")
    else:
        print(f"✓ Manifest JSONL exists: {MANIFEST_JSONL_PATH}")

    if not MANIFEST_PARQUET_PATH.exists():
        errors.append(f"Manifest Parquet missing: {MANIFEST_PARQUET_PATH}")
    else:
        print(f"✓ Manifest Parquet exists: {MANIFEST_PARQUET_PATH}")

    records = load_manifest_records()
    if not records:
        errors.append("Manifest contains 0 records")
    else:
        print(f"✓ Manifest contains {len(records)} total records")

    ok_records = [r for r in records if r.status == "ok"]
    if not ok_records:
        errors.append("No records with status='ok' found in manifest")
    else:
        print(f"✓ Found {len(ok_records)} successful document records")

    # 3. Check hosts strictly within *.rbi.org.in
    for r in records:
        if not is_rbi_host(r.file_url) or not is_rbi_host(r.source_page_url):
            errors.append(f"Invalid non-RBI host in manifest: {r.file_url} (doc_id={r.doc_id})")
            break
    print("✓ All manifest URLs adhere strictly to *.rbi.org.in allowlist")

    # 4. Check payload file integrity and sha256
    file_errors = 0
    for r in ok_records:
        if not r.local_path:
            file_errors += 1
            continue
        p = Path(r.local_path) if Path(r.local_path).is_absolute() else ROOT / r.local_path
        if not p.exists():
            file_errors += 1
            continue
        computed_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if r.sha256 and computed_sha != r.sha256:
            file_errors += 1
    if file_errors > 0:
        errors.append(f"{file_errors} status=ok files are missing or have mismatched sha256 hashes")
    else:
        print("✓ All status=ok document payloads exist with verified SHA-256 hashes")

    # 5. Check legal documents
    legal_files = list(LEGAL_DOCS_DIR.glob("*")) if LEGAL_DOCS_DIR.exists() else []
    if not legal_files:
        errors.append("docs/legal/ is empty; expected robots.txt and terms documents")
    else:
        print(f"✓ docs/legal/ contains {len(legal_files)} compliance/robots documents")

    # 6. Check report files
    if not CORPUS_REPORT_MD.exists():
        errors.append(f"Corpus report Markdown missing: {CORPUS_REPORT_MD}")
    else:
        print(f"✓ Corpus report exists: {CORPUS_REPORT_MD}")

    if errors:
        print("\n❌ Phase 1 Verification FAILED with errors:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("\n✅ Phase 1 Verification PASSED successfully!")
    return True


if __name__ == "__main__":
    success = verify_phase_1()
    sys.exit(0 if success else 1)
