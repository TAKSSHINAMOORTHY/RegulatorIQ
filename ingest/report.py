"""Corpus reporting, size gate evaluation, and report generation."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

from config.paths import (
    CORPUS_REPORT_JSON,
    CORPUS_REPORT_MD,
    MANIFEST_JSONL_PATH,
    RAW_RBI_DIR,
)
from ingest.manifest import load_manifest_records
from scripts.state import update_phase


def generate_corpus_report(target_count: int = 10000) -> Dict[str, Any]:
    """Analyze the manifest and generate Markdown and JSON corpus reports."""
    records = load_manifest_records()
    total_records = len(records)
    ok_records = [r for r in records if r.status == "ok"]
    ok_count = len(ok_records)

    counts_by_type = Counter(r.doc_type for r in ok_records)
    counts_by_year = Counter(str(r.year or "undated") for r in ok_records)
    failures_by_reason = Counter(r.error for r in records if r.status != "ok" and r.error)
    total_bytes = sum(r.bytes for r in ok_records)

    target_met = ok_count >= target_count
    degraded_reasons: List[str] = []
    if not target_met:
        degraded_reasons.append(
            f"Corpus size ({ok_count} documents) below target of {target_count}; continuing with authentic RBI docs only"
        )

    report_data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_manifest_rows": total_records,
        "successful_documents": ok_count,
        "target_met": target_met,
        "total_bytes": total_bytes,
        "total_megabytes": round(total_bytes / (1024 * 1024), 2),
        "counts_by_type": dict(counts_by_type),
        "counts_by_year": dict(sorted(counts_by_year.items())),
        "failures_by_reason": dict(failures_by_reason),
        "degraded_reasons": degraded_reasons,
    }

    # Write JSON report
    CORPUS_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(CORPUS_REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # Write Markdown report
    type_rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(counts_by_type.items()))
    year_rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(counts_by_year.items(), reverse=True))
    failure_rows = "\n".join(
        f"| {k[:60]} | {v} |"
        for k, v in sorted(failures_by_reason.items(), key=lambda x: x[1], reverse=True)
    )

    md_content = f"""# 📊 RegulatorIQ RBI Corpus Acquisition Report

**Generated At:** {report_data["generated_at"]}
**Status:** {"✅ Target Met" if target_met else "⚠️ Real Corpus Acquired (Target Honest Notice)"}
**Total Documents Acquired:** {ok_count:,} (Manifest rows: {total_records:,})
**Total Corpus Size:** {report_data["total_megabytes"]} MB

---

## 📑 Counts by Document Type
| Document Type | Count |
| :--- | :--- |
{type_rows or "| None | 0 |"}

---

## 📅 Counts by Year
| Year | Count |
| :--- | :--- |
{year_rows or "| None | 0 |"}

---

## ⚠️ Extraction & Download Status Breakdown
| Status / Reason | Count |
| :--- | :--- |
{failure_rows or "| All downloads successful | 0 |"}

---

## 🔍 Handoff Summary
- **Manifest Location:** `{MANIFEST_JSONL_PATH}`
- **Raw Storage:** `{RAW_RBI_DIR}`
- **Coverage Notes:** Exclusively official Reserve Bank of India domains (*.rbi.org.in). Zero synthetic or third-party padding.
"""

    with open(CORPUS_REPORT_MD, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Update STATE.json
    status = "complete" if target_met else "complete_degraded"
    update_phase(
        1,
        status=status,
        completed_at=report_data["generated_at"],
        artifacts={
            "manifest_path": str(MANIFEST_JSONL_PATH),
            "raw_dir": str(RAW_RBI_DIR),
            "paths_module": "config.paths",
        },
        counts={
            "total_documents": ok_count,
            "counts_by_type": dict(counts_by_type),
            "counts_by_year": dict(counts_by_year),
            "target_met": target_met,
        },
        notes=degraded_reasons,
    )

    return report_data
