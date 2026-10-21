"""Full processing pipeline: parse, clean, structure, link, and chunk official RBI documents."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from config.paths import (
    CHUNKS_PATH,
    DOCUMENTS_PATH,
    LINKS_PATH,
    PARSE_REPORT_JSON,
    PARSE_REPORT_MD,
    PROCESSED_DATA_DIR,
)
from ingest.links import (
    LinkEdge,
    compute_document_validity,
    extract_references_from_text,
)
from ingest.manifest import load_manifest_records
from ingest.parse.router import parse_and_clean_document
from ingest.structure import (
    Deduplicator,
    detect_section_tree,
    extract_applicability_entities,
    extract_effective_date,
    load_topics_taxonomy,
    match_topics,
)
from retrieval.chunking import (
    CHUNKING_VERSION,
    ChunkRecord,
    TokenCounter,
    chunk_document,
)
from scripts.state import update_phase

logger = logging.getLogger("process")


def run_full_processing() -> Dict[str, Any]:
    """Execute complete Phase 2 pipeline from raw files to Parquet datasets and audit reports."""
    print("🚀 Starting Phase 2 Processing: Parse, Clean, Enrich, Link, and Chunk...")
    records = load_manifest_records()
    ok_records = [r for r in records if r.status == "ok"]
    if not ok_records:
        raise RuntimeError("No status=ok records found in manifest to process!")

    token_counter = TokenCounter()
    deduplicator = Deduplicator()
    topics_taxonomy = load_topics_taxonomy()

    # Step 1: Parse and Clean
    print(f"📖 Step 1/4: Parsing and cleaning {len(ok_records)} documents...")
    parsed_docs = []
    quarantined_count = 0

    for r in ok_records:
        parsed = parse_and_clean_document(r)
        if parsed:
            parsed_docs.append((r, parsed))
        else:
            quarantined_count += 1

    parsed_ratio = len(parsed_docs) / len(ok_records) if ok_records else 0.0

    # Step 2: Build Lookup Maps for Linking
    known_circulars: Dict[str, str] = {}
    known_titles: Dict[str, tuple[str, int | None]] = {}
    for r, _ in parsed_docs:
        if r.circular_no_normalised:
            known_circulars[r.circular_no_normalised] = r.doc_id
        if r.title:
            known_titles[r.title.lower()] = (r.doc_id, r.year)

    # Step 3: Reference Extraction and Graph
    print("🔗 Step 2/4: Extracting references and supersession graph...")
    all_edges: List[LinkEdge] = []
    for r, parsed in parsed_docs:
        edges = extract_references_from_text(
            text=parsed.full_text,
            doc_id=r.doc_id,
            known_circulars=known_circulars,
            known_titles=known_titles,
        )
        all_edges.extend(edges)

        # Page hint supersession edge from manifest
        if r.superseded_hint and "superseded" in r.superseded_hint.lower():
            all_edges.append(
                LinkEdge(
                    src_doc_id=r.doc_id,
                    relation="supersedes",
                    dst_ref_text="Official Page Hint",
                    dst_doc_id=None,
                    evidence_text=r.superseded_hint,
                    confidence=1.0,
                    resolved=False,
                    method="page_hint",
                )
            )

    validity_info, anomalies = compute_document_validity([r for r, _ in parsed_docs], all_edges)

    # Step 4: Chunking and Metadata Assembly
    print("✂️ Step 3/4: Generating structured chunks and document records...")
    doc_records: List[Dict[str, Any]] = []
    all_chunks: List[ChunkRecord] = []

    for r, parsed in parsed_docs:
        sections, struct_conf = detect_section_tree(parsed)
        topics = match_topics(parsed.full_text, topics_taxonomy)
        entities = extract_applicability_entities(parsed.full_text)
        eff_date = extract_effective_date(parsed.full_text) or r.issue_date
        val_meta = validity_info.get(r.doc_id, {})

        # Deduplication
        dup_of = deduplicator.check_duplicate(r.doc_id, parsed.full_text)

        doc_dict = {
            "doc_id": r.doc_id,
            "doc_type": r.doc_type,
            "title": r.title,
            "circular_no": r.circular_no,
            "circular_no_normalised": r.circular_no_normalised,
            "department": r.department,
            "issue_date": r.issue_date,
            "year": r.year,
            "effective_date": eff_date,
            "valid_from": val_meta.get("valid_from"),
            "valid_to": val_meta.get("valid_to"),
            "is_current": val_meta.get("is_current", True),
            "validity_confidence": val_meta.get("validity_confidence", "medium"),
            "topics": topics,
            "applicability_entities": entities,
            "duplicate_of": dup_of,
            "is_primary_english": parsed.is_primary_english,
            "lang": parsed.lang,
            "quality_score": parsed.quality_score,
            "structure_confidence": struct_conf,
            "source_url": r.source_page_url or r.file_url,
        }
        doc_records.append(doc_dict)

        # Do not chunk duplicates or Hindi-only documents
        if dup_of is None and parsed.is_primary_english:
            doc_chunks = chunk_document(
                parsed=parsed,
                manifest=r,
                sections=sections,
                validity_info=val_meta,
                topics=topics,
                entities=entities,
                token_counter=token_counter,
            )
            all_chunks.extend(doc_chunks)

    # Step 5: Save Parquet Datasets (pyarrow zstd)
    print("💾 Step 4/4: Writing documents.parquet, links.parquet, and chunks.parquet...")
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    df_docs = pd.DataFrame(doc_records)
    df_docs.to_parquet(DOCUMENTS_PATH, compression="zstd", index=False)

    df_links = pd.DataFrame([e.model_dump() for e in all_edges]) if all_edges else pd.DataFrame()
    df_links.to_parquet(LINKS_PATH, compression="zstd", index=False)

    df_chunks = pd.DataFrame([c.model_dump() for c in all_chunks])
    df_chunks.to_parquet(CHUNKS_PATH, compression="zstd", index=False)

    # Step 6: Compute Stats and Verification Gates
    token_counts = [c.token_count for c in all_chunks] if all_chunks else [0]
    p50 = float(np.percentile(token_counts, 50))
    p95 = float(np.percentile(token_counts, 95))
    max_tokens = int(max(token_counts))

    current_docs = sum(1 for d in doc_records if d["is_current"])
    superseded_docs = len(doc_records) - current_docs
    unresolved_edges = sum(1 for e in all_edges if not e.resolved)

    # Quality Gates Verification
    degraded_reasons: List[str] = []
    if parsed_ratio < 0.95:
        degraded_reasons.append(f"Parsed ratio ({parsed_ratio:.2%}) is below 95% threshold")
    if max_tokens > 512:
        raise ValueError(f"HARD GATE VIOLATION: max chunk token count ({max_tokens}) > 512!")
    for c in all_chunks:
        if not c.text.strip():
            raise ValueError(f"HARD GATE VIOLATION: Empty chunk text found (chunk_id={c.chunk_id})")
        if not c.source_url:
            raise ValueError(f"HARD GATE VIOLATION: Missing source_url (chunk_id={c.chunk_id})")

    # Generate Parse Report
    report_data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "doc_count": len(doc_records),
        "chunk_count": len(all_chunks),
        "parsed_ratio": round(parsed_ratio, 4),
        "quarantined_count": quarantined_count,
        "current_doc_count": current_docs,
        "superseded_doc_count": superseded_docs,
        "edges_count": len(all_edges),
        "unresolved_edges_count": unresolved_edges,
        "token_stats": {
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "max": max_tokens,
        },
        "tokenizer_name": token_counter.model_name,
        "tokenizer_fallback": token_counter.is_fallback,
        "chunking_version": CHUNKING_VERSION,
        "degraded_reasons": degraded_reasons,
    }

    PARSE_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(PARSE_REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    md_report = f"""# 📑 RegulatorIQ Document Parsing, Linking & Chunking Report

**Generated At:** {report_data["generated_at"]}
**Total Documents Processed:** {len(doc_records)}
**Total Chunks Generated:** {len(all_chunks):,}
**Parsed Ratio:** {parsed_ratio:.1%}
**Quarantined Documents:** {quarantined_count}

---

## 📊 Chunking & Token Statistics
- **Tokenizer:** `{token_counter.model_name}` (Fallback: `{token_counter.is_fallback}`)
- **Median Tokens (p50):** {p50:.1f}
- **95th Percentile Tokens (p95):** {p95:.1f}
- **Maximum Tokens:** {max_tokens} (Hard Limit: 512 ✅)

---

## 🏛️ Supersession & Graph Statistics
- **Current Rules in Force:** {current_docs}
- **Superseded / Withdrawn Rules:** {superseded_docs}
- **Reference & Supersession Edges:** {len(all_edges)}
- **Unresolved Edges:** {unresolved_edges}

---

## 📁 Output Artifacts
- **Documents Dataset:** `{DOCUMENTS_PATH}`
- **Chunks Dataset:** `{CHUNKS_PATH}`
- **Links Dataset:** `{LINKS_PATH}`
"""
    with open(PARSE_REPORT_MD, "w", encoding="utf-8") as f:
        f.write(md_report)

    # Update docs/STATE.json
    update_phase(
        2,
        status="complete" if not degraded_reasons else "complete_degraded",
        completed_at=report_data["generated_at"],
        artifacts={
            "documents_path": str(DOCUMENTS_PATH),
            "chunks_path": str(CHUNKS_PATH),
            "links_path": str(LINKS_PATH),
            "chunk_count": len(all_chunks),
            "doc_count": len(doc_records),
            "token_stats": report_data["token_stats"],
            "tokenizer_name": token_counter.model_name,
            "tokenizer_fallback": token_counter.is_fallback,
            "chunking_version": CHUNKING_VERSION,
            "current_doc_count": current_docs,
            "superseded_doc_count": superseded_docs,
            "unresolved_edge_count": unresolved_edges,
            "degraded_reasons": degraded_reasons,
        },
        counts={
            "documents": len(doc_records),
            "chunks": len(all_chunks),
            "edges": len(all_edges),
        },
        notes=degraded_reasons,
    )

    print("✅ Phase 2 Processing Completed Successfully!")
    return report_data


if __name__ == "__main__":
    run_full_processing()
