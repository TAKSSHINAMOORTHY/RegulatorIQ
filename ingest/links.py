"""Supersession and reference graph extraction and document validity computation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field

from config.paths import CONFIG_DIR, LINK_ANOMALIES_MD
from ingest.manifest import ManifestRecord
from ingest.normalise import (
    RE_AP_DIR,
    RE_DEPT_CIRCULAR,
    RE_RBI_PREFIX,
    normalise_circular_no,
)

logger = logging.getLogger(__name__)


class LinkEdge(BaseModel):
    """Schema for a reference or supersession edge in links.parquet."""

    src_doc_id: str
    relation: str  # "supersedes", "withdraws", "amends", "refers", "updates"
    dst_ref_text: str
    dst_doc_id: Optional[str] = None
    evidence_text: str = Field(..., max_length=350)
    evidence_char_start: int = 0
    evidence_char_end: int = 0
    confidence: float = 1.0
    resolved: bool = False
    method: str = "number_match"  # "number_match" | "title_fuzzy" | "page_hint"


def load_relations_config() -> Dict[str, Any]:
    """Load trigger phrases and negations from config/relations.yaml."""
    cfg_file = CONFIG_DIR / "relations.yaml"
    if not cfg_file.exists():
        return {
            "supersedes": {"triggers": ["supersede", "superseded", "replaces"], "negations": []},
            "withdraws": {"triggers": ["withdrawn", "stands withdrawn"], "negations": []},
            "amends": {"triggers": ["amend", "amendment to"], "negations": []},
            "refers": {"triggers": ["refer to", "reference is invited"], "negations": []},
        }
    with open(cfg_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return dict(data.get("relations", {})) if isinstance(data, dict) else {}


def classify_relation_in_window(
    window_text: str,
    relations_cfg: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Classify relation based on trigger phrases in a +-200 character window around a reference.

    Applies negation filtering so phrases like 'no circular has been superseded'
    never yield a false relation.
    """
    cfg = relations_cfg or load_relations_config()
    lower_win = window_text.lower()

    # Pre-check: priority order supersedes > withdraws > amends > refers
    order = ["supersedes", "withdraws", "amends", "refers"]
    for rel in order:
        rel_info = cfg.get(rel, {})
        triggers = rel_info.get("triggers", [])
        negations = rel_info.get("negations", [])

        # If any negation phrase is present in the window, do not match this relation
        if any(neg in lower_win for neg in negations):
            continue

        for trigger in triggers:
            if trigger in lower_win:
                return rel

    return None


def extract_references_from_text(
    text: str,
    doc_id: str,
    known_circulars: Dict[str, str],  # normalised_circ_no -> doc_id
    known_titles: Dict[str, Tuple[str, Optional[int]]],  # clean_title -> (doc_id, year)
    relations_cfg: Optional[Dict[str, Any]] = None,
) -> List[LinkEdge]:
    """Extract circular and title references from text with quoted evidence spans."""
    edges: List[LinkEdge] = []
    cfg = relations_cfg or load_relations_config()

    # Find circular number patterns in text
    all_patterns = [RE_RBI_PREFIX, RE_DEPT_CIRCULAR, RE_AP_DIR]
    found_spans: List[Tuple[int, int, str]] = []

    for pat in all_patterns:
        for match in pat.finditer(text):
            found_spans.append((match.start(), match.end(), match.group(0)))

    for start_pos, end_pos, ref_raw in found_spans:
        circ_norm = normalise_circular_no(ref_raw)
        if not circ_norm:
            continue

        # Sentence-bounded window around reference
        prev_break = max(
            text.rfind(". ", max(0, start_pos - 120), start_pos),
            text.rfind("\n", max(0, start_pos - 120), start_pos),
        )
        win_start = prev_break + 2 if prev_break != -1 else max(0, start_pos - 60)

        next_period = text.find(". ", end_pos, min(len(text), end_pos + 120))
        next_newline = text.find("\n", end_pos, min(len(text), end_pos + 120))
        breaks = [b for b in [next_period, next_newline] if b != -1]
        win_end = min(breaks) if breaks else min(len(text), end_pos + 60)

        window = text[win_start:win_end]

        relation = classify_relation_in_window(window, cfg) or "refers"

        # Evidence text: concise quoted snippet
        ev_start = max(0, start_pos - 80)
        ev_end = min(len(text), end_pos + 80)
        evidence = text[ev_start:ev_end].strip().replace("\n", " ")[:300]

        dst_id = known_circulars.get(circ_norm)
        resolved = dst_id is not None

        # Do not add self-loops
        if dst_id == doc_id:
            continue

        edge = LinkEdge(
            src_doc_id=doc_id,
            relation=relation,
            dst_ref_text=circ_norm,
            dst_doc_id=dst_id,
            evidence_text=evidence,
            evidence_char_start=start_pos,
            evidence_char_end=end_pos,
            confidence=0.95 if resolved else 0.70,
            resolved=resolved,
            method="number_match",
        )
        edges.append(edge)

    return edges


def compute_document_validity(
    records: List[ManifestRecord],
    edges: List[LinkEdge],
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Compute validity for each document: valid_from, valid_to, is_current, validity_confidence.

    Cycle detection: Detects cycles (A supersedes B and B supersedes A) and logs them to
    reports/link_anomalies.md.
    """
    doc_map = {r.doc_id: r for r in records}
    validity_info: Dict[str, Dict[str, Any]] = {}
    anomalies: List[str] = []

    # Map of document -> list of (superseding_doc_id, issue_date)
    superseded_by: Dict[str, List[Tuple[str, str]]] = {r.doc_id: [] for r in records}

    # Track superseding pairs for cycle detection
    supersedes_pairs: set[tuple[str, str]] = set()

    for edge in edges:
        if edge.relation in ("supersedes", "withdraws") and edge.resolved and edge.dst_doc_id:
            # src_doc supersedes dst_doc!
            src_rec = doc_map.get(edge.src_doc_id)
            src_date = src_rec.issue_date if src_rec else None
            superseded_by[edge.dst_doc_id].append((edge.src_doc_id, src_date or "9999-99-99"))

            supersedes_pairs.add((edge.src_doc_id, edge.dst_doc_id))
            # Check cycle: does dst_doc also supersede src_doc?
            if (edge.dst_doc_id, edge.src_doc_id) in supersedes_pairs:
                msg = f"Contradiction/Cycle detected: {edge.src_doc_id} and {edge.dst_doc_id} mutually supersede each other."
                anomalies.append(msg)
                logger.warning(msg)

    # Compute validity per document
    for r in records:
        valid_from = r.issue_date
        valid_to = None
        is_current = True
        confidence = "medium"

        # Check page hint
        has_page_hint = bool(r.superseded_hint and "superseded" in r.superseded_hint.lower())

        successors = superseded_by.get(r.doc_id, [])
        if successors:
            # Earliest superseding document determines valid_to
            successors_sorted = sorted(successors, key=lambda x: x[1])
            earliest_successor_id, earliest_date = successors_sorted[0]
            valid_to = earliest_date if earliest_date != "9999-99-99" else None
            is_current = False
            confidence = "high"
        elif has_page_hint:
            is_current = False
            confidence = "high"
        else:
            is_current = True
            confidence = "high"

        validity_info[r.doc_id] = {
            "valid_from": valid_from,
            "valid_to": valid_to,
            "is_current": is_current,
            "validity_confidence": confidence,
        }

    # Write anomalies report
    LINK_ANOMALIES_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(LINK_ANOMALIES_MD, "w", encoding="utf-8") as f:
        f.write("# ⚠️ RegulatorIQ Supersession Link Anomalies Report\n\n")
        if anomalies:
            for a in anomalies:
                f.write(f"- {a}\n")
        else:
            f.write("No cycles or mutual supersession contradictions detected in the graph.\n")

    return validity_info, anomalies
