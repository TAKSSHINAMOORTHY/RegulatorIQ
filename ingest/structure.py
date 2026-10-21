"""Structure extraction, metadata enrichment, and near-duplicate detection."""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

import yaml
from datasketch import MinHash, MinHashLSH

from config.paths import CONFIG_DIR
from ingest.normalise import parse_issue_date
from ingest.parse.models import ParsedDocument

# Hierarchy regex patterns
RE_CHAPTER = re.compile(
    r"^\s*(CHAPTER\s+[IVXLCDM\d]+|Chapter\s*[-–]\s*[IVXLCDM\d]+)(?:\s*[-–:]\s*|\s*\n\s*)([^\n]+)?",
    re.IGNORECASE | re.MULTILINE,
)
RE_ANNEX = re.compile(
    r"^\s*(ANNEX(?:URE)?\s+[IVXLCDM\d]+|APPENDIX\s+[IVXLCDM\d]+|SCHEDULE\s+[IVXLCDM\d]+)",
    re.IGNORECASE | re.MULTILINE,
)
RE_SECTION_NUM = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9\s,\-–'\"]{3,60})", re.MULTILINE
)
RE_CLAUSE_REF = re.compile(r"^\s*(\([a-z0-9]+\))\s+", re.IGNORECASE | re.MULTILINE)
RE_SPECIAL_SECTIONS = re.compile(
    r"^\s*(Definitions|Applicability|Short title and commencement|Scope|Purpose)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Effective date regex
RE_EFFECTIVE_DATE = re.compile(
    r"(?:come\s+into\s+force|come\s+into\s+effect|with\s+effect\s+from|effective\s+from|effective\s+date\s*[:\-])\s+([A-Za-z0-9,\s\.\-]+?)(?:\.|\n|;|$)",
    re.IGNORECASE,
)

# Standard entities dictionary
ENTITY_TAXONOMY: Dict[str, List[str]] = {
    "Commercial Banks": [
        "commercial bank",
        "scheduled commercial bank",
        "scb",
        "public sector bank",
        "private sector bank",
    ],
    "NBFCs": [
        "nbfc",
        "non-banking financial company",
        "core investment company",
        "housing finance company",
    ],
    "Urban Co-operative Banks": ["ucb", "urban co-operative bank", "primary cooperative bank"],
    "Payment System Operators": [
        "pso",
        "payment system operator",
        "payment aggregator",
        "prepaid payment instrument",
    ],
    "Authorised Dealers": [
        "authorised dealer",
        "ad category",
        "ad bank",
        "authorised dealer category-i",
    ],
    "Small Finance Banks": ["small finance bank", "sfb"],
    "Payments Banks": ["payments bank"],
    "Credit Information Companies": ["credit information company", "cic"],
    "Asset Reconstruction Companies": ["asset reconstruction company", "arc"],
}


def load_topics_taxonomy() -> Dict[str, List[str]]:
    """Load topics keyword dictionary from config/topics.yaml."""
    yaml_path = CONFIG_DIR / "topics.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    topics = {}
    for key, info in data.get("topics", {}).items():
        topics[key] = [kw.lower() for kw in info.get("keywords", [])]
    return topics


def extract_effective_date(text: str) -> Optional[str]:
    """Find effective date from clauses like 'with effect from <date>'."""
    match = RE_EFFECTIVE_DATE.search(text[:3000])  # Look in preamble/first sections
    if match:
        raw_date = match.group(1).strip()
        iso_date, _ = parse_issue_date(raw_date)
        return iso_date
    return None


def extract_applicability_entities(text: str) -> List[str]:
    """Match regulated entities mentioned in document text."""
    lower_text = text.lower()
    matched = []
    for entity_name, keywords in ENTITY_TAXONOMY.items():
        if any(kw in lower_text for kw in keywords):
            matched.append(entity_name)
    return matched


def match_topics(text: str, taxonomy: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """Match topics from keyword taxonomy."""
    tax = taxonomy or load_topics_taxonomy()
    lower_text = text.lower()
    matched_topics = []
    for topic_id, keywords in tax.items():
        if any(kw in lower_text for kw in keywords):
            matched_topics.append(topic_id)
    return matched_topics


class SectionNode:
    """Represents a section in the document hierarchy."""

    def __init__(
        self,
        title: str,
        section_path: str,
        para_ref: Optional[str] = None,
        text: str = "",
        page_start: int = 1,
        page_end: int = 1,
    ):
        self.title = title
        self.section_path = section_path
        self.para_ref = para_ref
        self.text = text
        self.page_start = page_start
        self.page_end = page_end


def detect_section_tree(parsed: ParsedDocument) -> Tuple[List[SectionNode], str]:
    """Detect section hierarchy: Chapter > Section > Subclause.

    Returns:
        (sections, structure_confidence in {'high', 'medium', 'low'})
    """
    sections: List[SectionNode] = []
    current_chapter = ""
    current_section = ""
    structure_found = False

    for page in parsed.pages:
        page_no = page.page_no
        paragraphs = re.split(r"\n\s*\n", page.text)

        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue

            # Check Chapter
            chap_match = RE_CHAPTER.match(p_clean)
            if chap_match:
                chap_name = chap_match.group(1).strip()
                chap_title = chap_match.group(2) or ""
                current_chapter = f"{chap_name} - {chap_title}".strip(" -")
                structure_found = True
                continue

            # Check Annex / Schedule
            annex_match = RE_ANNEX.match(p_clean)
            if annex_match:
                current_chapter = annex_match.group(1).strip()
                current_section = ""
                structure_found = True

            # Check Section Number
            sec_match = RE_SECTION_NUM.match(p_clean)
            if sec_match:
                sec_num = sec_match.group(1)
                sec_title = sec_match.group(2).strip()
                current_section = f"{sec_num}. {sec_title}"
                structure_found = True

            # Check Named Section
            special_match = RE_SPECIAL_SECTIONS.match(p_clean)
            if special_match:
                current_section = special_match.group(1).strip()
                structure_found = True

            # Check Paragraph Reference e.g. "(a)", "para 5.2"
            clause_match = RE_CLAUSE_REF.match(p_clean)
            para_ref = None
            if clause_match:
                clause_marker = clause_match.group(1)
                if current_section and "." in current_section:
                    sec_prefix = current_section.split()[0]
                    para_ref = f"para {sec_prefix}{clause_marker}"
                else:
                    para_ref = f"para {clause_marker}"

            path_parts = [p for p in [current_chapter, current_section] if p]
            section_path = " > ".join(path_parts) if path_parts else "General"

            sections.append(
                SectionNode(
                    title=current_section or current_chapter or "General",
                    section_path=section_path,
                    para_ref=para_ref,
                    text=p_clean,
                    page_start=page_no,
                    page_end=page_no,
                )
            )

    confidence = (
        "high"
        if (structure_found and len(sections) > 5)
        else ("medium" if structure_found else "low")
    )
    return sections, confidence


class Deduplicator:
    """Exact and near-duplicate detector using SHA256 and MinHash LSH."""

    def __init__(self, threshold: float = 0.9, num_perm: int = 128):
        self.threshold = threshold
        self.num_perm = num_perm
        self.exact_hashes: Dict[str, str] = {}  # sha256 -> canonical doc_id
        self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self.minhashes: Dict[str, MinHash] = {}

    def _get_minhash(self, text: str) -> MinHash:
        words = re.findall(r"\w+", text.lower())
        m = MinHash(num_perm=self.num_perm)
        # 5-word shingles
        for i in range(max(1, len(words) - 4)):
            shingle = " ".join(words[i : i + 5])
            m.update(shingle.encode("utf-8"))
        return m

    def check_duplicate(self, doc_id: str, text: str) -> Optional[str]:
        """Check if document is an exact or near duplicate of an already registered document.

        Returns:
            canonical_doc_id if duplicate, else None
        """
        norm_text = re.sub(r"\s+", " ", text.strip().lower())
        sha = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()

        # 1. Exact match
        if sha in self.exact_hashes:
            return self.exact_hashes[sha]

        # 2. Near-duplicate match via MinHash LSH
        m = self._get_minhash(norm_text)
        candidates = self.lsh.query(m)
        if candidates:
            # Found near-duplicate
            return str(candidates[0])

        # Register new canonical document
        self.exact_hashes[sha] = doc_id
        try:
            self.lsh.insert(doc_id, m)
            self.minhashes[doc_id] = m
        except Exception:
            pass

        return None
