"""Query analysis and deterministic planning for regulatory search.

Extracts structured query plans (identifiers, dates, temporal intent, doc types,
entities, topics, intents, warnings) and produces additive query variants using
domain-specific abbreviations and synonyms without requiring LLM execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from config.paths import CONFIG_DIR
from ingest.normalise import (
    RE_AP_DIR,
    RE_DEPT_CIRCULAR,
    RE_RBI_PREFIX,
    normalise_circular_no,
)

# Month names mapping
MONTHS_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# Regex for textual dates e.g. "1 April 2023", "April 1, 2023", "01-Apr-2023"
RE_TEXT_DATE_DMY = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-_]+([A-Za-z]{3,9})[\s\-_,]+(20\d\d|19\d\d)\b",
    re.IGNORECASE,
)
RE_TEXT_DATE_MDY = re.compile(
    r"\b([A-Za-z]{3,9})[\s\-_]+(\d{1,2})(?:st|nd|rd|th)?[\s\-_,]+(20\d\d|19\d\d)\b",
    re.IGNORECASE,
)

# ISO date: YYYY-MM-DD
RE_ISO_DATE = re.compile(r"\b(20\d\d|19\d\d)-(\d{2})-(\d{2})\b")

# Numeric date: e.g. 11.11.2025, 03/04/2023, 25-05-2022
RE_NUM_DATE = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](20\d\d|19\d\d)\b")

# Financial Year regex e.g. FY 2024-25, FY 2024-2025, FY24-25
RE_FY = re.compile(
    r"\b(?:FY|financial\s+year)\s*[:\-]?\s*(20\d\d)[-\/](20\d\d|\d{2})\b", re.IGNORECASE
)

# Temporal phrase regexes
PHRASES_CURRENT = [
    r"\bcurrent\b",
    r"\blatest\b",
    r"\bnow\b",
    r"\bstill\s+in\s+force\b",
    r"\bpresently\b",
    r"\bas\s+on\s+date\b",
    r"\bapplicable\s+today\b",
    r"\bin\s+force\b",
    r"\bactive\b",
]
RE_CURRENT = re.compile("|".join(PHRASES_CURRENT), re.IGNORECASE)

PHRASES_HISTORY = [
    r"\bearlier\b",
    r"\bprevious\b",
    r"\bold\b",
    r"\bbefore\b",
    r"\bsuperseded\b",
    r"\bwithdrawn\b",
    r"\bprior\s+to\b",
    r"\brepealed\b",
    r"\bhistory\b",
]
RE_HISTORY = re.compile("|".join(PHRASES_HISTORY), re.IGNORECASE)

# Document type regexes
DOC_TYPE_PATTERNS = [
    ("Master Direction", re.compile(r"\bmaster\s+direction[s]?\b", re.IGNORECASE)),
    ("Master Circular", re.compile(r"\bmaster\s+circular[s]?\b", re.IGNORECASE)),
    (
        "Amendment Direction",
        re.compile(r"\bamendment(?:\s+direction[s]?|\s+circular[s]?)?\b", re.IGNORECASE),
    ),
    ("Press Release", re.compile(r"\bpress\s+release[s]?\b", re.IGNORECASE)),
    ("Notification", re.compile(r"\bnotification[s]?\b", re.IGNORECASE)),
    ("Circular", re.compile(r"\bcircular[s]?\b", re.IGNORECASE)),
    ("FAQ", re.compile(r"\bfaqs?\b|\bfrequently\s+asked\s+questions?\b", re.IGNORECASE)),
    ("Guideline", re.compile(r"\bguidelines?\b|\bframework\b", re.IGNORECASE)),
]

# Entity pattern hints
ENTITY_PATTERNS = [
    (
        "banks",
        re.compile(
            r"\b(?:banks?|banking\s+institutions?|commercial\s+banks?|scheduled\s+commercial\s+banks?|scb|scbs|public\s+sector\s+banks?|private\s+banks?|small\s+finance\s+banks?|sfb|sfbs|payment\s+banks?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "NBFCs",
        re.compile(
            r"\b(?:nbfc|nbfcs|non[\-\s]banking\s+financial\s+compan(?:y|ies)|nbfc[\-\s]nd|nbfc[\-\s]d|nbfc[\-\s]mfi|nbfc[\-\s]icc)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "UCBs",
        re.compile(
            r"\b(?:ucb|ucbs|urban\s+co[\-\s]operative\s+banks?|co[\-\s]operative\s+banks?|dccb|stcb|primary\s+cooperative\s+banks?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "payment system operators",
        re.compile(
            r"\b(?:payment\s+system\s+operators?|pso|psos|payment\s+aggregators?|pa|pg|payment\s+gateways?|ppi|prepaid\s+payment\s+instruments?|npci|upi|atm\s+operators?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "authorised dealers",
        re.compile(
            r"\b(?:authorised\s+dealers?|authorized\s+dealers?|ad\s+banks?|ad[\-\s]i|ad[\-\s]category[\-\s]i|ad[\-\s]ii)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ARCs",
        re.compile(r"\b(?:arc|arcs|asset\s+reconstruction\s+compan(?:y|ies))\b", re.IGNORECASE),
    ),
    ("CICs", re.compile(r"\b(?:cic|cics|credit\s+information\s+compan(?:y|ies))\b", re.IGNORECASE)),
    ("HFCs", re.compile(r"\b(?:hfc|hfcs|housing\s+finance\s+compan(?:y|ies))\b", re.IGNORECASE)),
]

# Intent classification patterns
INTENT_PATTERNS = [
    (
        "lookup",
        re.compile(
            r"\b(?:circular\s+no|rbi/\d|notification\s+no|number|ref\s+no|master\s+direction\s+on)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "definition",
        re.compile(
            r"\b(?:what\s+is|what\s+are|define|meaning\s+of|stands\s+for|definition\s+of|term)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "threshold",
        re.compile(
            r"\b(?:limit|limits|cap|caps|threshold|thresholds|minimum|maximum|ratio|crr|slr|lcr|car|crar|percentage|%|crore|lakh|ceiling|prescribed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "timeline",
        re.compile(
            r"\b(?:when|deadline|timeline|effective\s+date|commencement|period|duration|due\s+date|grace\s+period|frequency)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "comparison",
        re.compile(
            r"\b(?:difference\s+between|compare|comparison|versus|vs|distinction|differ)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "applicability",
        re.compile(
            r"\b(?:applicable\s+to|applies\s+to|applicability|who\s+does|eligible|eligibility|scope|exemption|exempted)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "validity",
        re.compile(
            r"\b(?:still\s+in\s+force|valid|validity|superseded|repealed|withdrawn|active|in\s+force|current\s+status)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "procedure",
        re.compile(
            r"\b(?:how\s+to|process|procedure|steps|filing|apply|submission|reporting\s+process|mechanism)\b",
            re.IGNORECASE,
        ),
    ),
]


@dataclass
class QueryPlan:
    """Deterministic structured query plan for regulatory retrieval."""

    raw: str
    normalised: str
    identifiers: List[str] = field(default_factory=list)
    years: List[int] = field(default_factory=list)
    explicit_dates: List[str] = field(default_factory=list)
    as_of_date: Optional[str] = None
    wants_current: bool = False
    wants_history: bool = False
    doc_type_hints: List[str] = field(default_factory=list)
    entity_hints: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    query_variants: List[str] = field(default_factory=list)
    intents: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class QueryAnalyzer:
    """Thread-safe, stateless query analysis engine."""

    def __init__(self) -> None:
        self.abbreviations: Dict[str, str] = self._load_abbreviations()
        self.reverse_abbreviations: Dict[str, str] = {
            v.lower(): k for k, v in self.abbreviations.items()
        }
        self.synonyms: Dict[str, List[str]] = self._load_synonyms()
        self.topics: Dict[str, Dict[str, Any]] = self._load_topics()

    def _load_abbreviations(self) -> Dict[str, str]:
        path = CONFIG_DIR / "abbreviations.yaml"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                raw_abbr = data.get("abbreviations", {})
                return (
                    {str(k): str(v) for k, v in raw_abbr.items()}
                    if isinstance(raw_abbr, dict)
                    else {}
                )
        except Exception:
            return {}

    def _load_synonyms(self) -> Dict[str, List[str]]:
        path = CONFIG_DIR / "synonyms.yaml"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                raw_syn = data.get("synonyms", {})
                return (
                    {str(k): [str(x) for x in v] for k, v in raw_syn.items()}
                    if isinstance(raw_syn, dict)
                    else {}
                )
        except Exception:
            return {}

    def _load_topics(self) -> Dict[str, Dict[str, Any]]:
        path = CONFIG_DIR / "topics.yaml"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                raw_topics = data.get("topics", {})
                return dict(raw_topics) if isinstance(raw_topics, dict) else {}
        except Exception:
            return {}

    def parse_dates_and_years(
        self, text: str
    ) -> Tuple[List[str], Optional[str], List[int], List[str]]:
        """Parse explicit dates, as_of_date, years, and ambiguous date warnings."""
        explicit_dates: List[str] = []
        as_of_date: Optional[str] = None
        years_set: Set[int] = set()
        warnings: List[str] = []

        # 1. Financial Years e.g. FY 2024-25
        for m in RE_FY.finditer(text):
            y1_str, y2_str = m.group(1), m.group(2)
            try:
                y1 = int(y1_str)
                if len(y2_str) == 2:
                    y2 = int(str(y1)[:2] + y2_str)
                else:
                    y2 = int(y2_str)
                years_set.add(y1)
                years_set.add(y2)
            except ValueError:
                pass

        # 2. As of / As on dates e.g. "as of 1 April 2023", "as on date 31.03.2024"
        as_of_match = re.search(
            r"\b(?:as\s+of|as\s+on)\s+(?:date\s+)?([A-Za-z0-9,\s\.\-\/]+?)(?:\s+(?:what|how|is|was|the|did|which)|\s*$)",
            text,
            re.IGNORECASE,
        )
        as_of_candidate_str = as_of_match.group(1).strip() if as_of_match else None

        # 3. ISO dates YYYY-MM-DD
        for m in RE_ISO_DATE.finditer(text):
            y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                dt = date(y, mm, dd).isoformat()
                explicit_dates.append(dt)
                years_set.add(y)
            except ValueError:
                pass

        # 4. Textual dates: "1 April 2023" or "April 1, 2023"
        for m in RE_TEXT_DATE_DMY.finditer(text):
            d_str, mon_str, y_str = m.group(1), m.group(2).lower(), m.group(3)
            mon = MONTHS_MAP.get(mon_str[:3])
            if mon:
                try:
                    dt = date(int(y_str), mon, int(d_str)).isoformat()
                    explicit_dates.append(dt)
                    years_set.add(int(y_str))
                except ValueError:
                    pass

        for m in RE_TEXT_DATE_MDY.finditer(text):
            mon_str, d_str, y_str = m.group(1).lower(), m.group(2), m.group(3)
            mon = MONTHS_MAP.get(mon_str[:3])
            if mon:
                try:
                    dt = date(int(y_str), mon, int(d_str)).isoformat()
                    explicit_dates.append(dt)
                    years_set.add(int(y_str))
                except ValueError:
                    pass

        # 5. Numeric dates: e.g. 11.11.2025 or 03/04/2023
        for m in RE_NUM_DATE.finditer(text):
            # Check if this part was already captured by ISO date
            matched_str = m.group(0)
            p1, p2, y_int = int(m.group(1)), int(m.group(2)), int(m.group(3))

            # Disambiguation check
            # If p1 <= 12 and p2 <= 12 and p1 != p2: ambiguous! Drop and record warning
            if p1 <= 12 and p2 <= 12 and p1 != p2:
                warnings.append(f"Ambiguous date '{matched_str}' dropped")
                continue

            # Otherwise, Indian regulatory convention is DD/MM/YYYY
            # If p1 > 12: p1 is day, p2 is month
            # If p1 == p2: day = month = p1
            # If p2 > 12: malformed or MM/DD/YYYY, let's validate
            try:
                if p1 <= 31 and p2 <= 12:
                    dt = date(y_int, p2, p1).isoformat()
                    explicit_dates.append(dt)
                    years_set.add(y_int)
                elif p2 <= 31 and p1 <= 12:
                    dt = date(y_int, p1, p2).isoformat()
                    explicit_dates.append(dt)
                    years_set.add(y_int)
            except ValueError:
                warnings.append(f"Malformed date '{matched_str}' dropped")

        # 6. Standalone 4-digit years between 1990 and 2035 (e.g. "in 2021")
        for m in re.finditer(r"\b(19\d\d|20[0-3]\d)\b", text):
            # Ignore if it is part of an identifier like 2025-26
            val = int(m.group(1))
            # Check context around match to avoid circular suffixes
            start = m.start()
            end = m.end()
            prev_char = text[start - 1] if start > 0 else " "
            next_char = text[end] if end < len(text) else " "
            if prev_char in "/-." or next_char in "/-.":
                continue
            years_set.add(val)

        # 7. Resolve as_of_date
        if as_of_candidate_str:
            # Check if any explicit date was extracted from that candidate string
            for ed in explicit_dates:
                # E.g. "2023-04-01" vs "1 April 2023"
                ed_parts = ed.split("-")
                if ed_parts[0] in as_of_candidate_str:
                    as_of_date = ed
                    break
            if not as_of_date and explicit_dates:
                as_of_date = explicit_dates[0]

        # Deduplicate and sort explicit dates
        explicit_dates = sorted(list(set(explicit_dates)))
        years = sorted(list(years_set))

        return explicit_dates, as_of_date, years, warnings

    def extract_identifiers(self, text: str, store: Optional[Any] = None) -> List[str]:
        """Extract and normalise official RBI circular/direction identifiers."""
        identifiers: List[str] = []

        # RBI prefix e.g. RBI/2025-26/90
        for m in RE_RBI_PREFIX.finditer(text):
            norm = normalise_circular_no(m.group(1))
            if norm and norm not in identifiers:
                identifiers.append(norm)

        # Department circular e.g. DOR.MCS.REC.59/01.01.003/2025-26
        for m in RE_DEPT_CIRCULAR.finditer(text):
            norm = normalise_circular_no(m.group(1))
            if norm and norm not in identifiers:
                identifiers.append(norm)

        # A.P. (DIR Series)
        for m in RE_AP_DIR.finditer(text):
            norm = normalise_circular_no(m.group(0))
            if norm and norm not in identifiers:
                identifiers.append(norm)

        # If store is available, also test lookup_identifier on candidate phrases
        if store is not None and hasattr(store, "lookup_identifier"):
            words = text.split()
            for w in words:
                cleaned = w.strip(".,;:()[]\"'{}")
                if len(cleaned) >= 5 and any(c.isdigit() for c in cleaned):
                    hits = store.lookup_identifier(cleaned)
                    if hits:
                        norm = normalise_circular_no(cleaned) or cleaned.upper()
                        if norm not in identifiers:
                            identifiers.append(norm)

        return identifiers

    def detect_intents(self, text: str) -> List[str]:
        """Classify query intent based on deterministic regulatory patterns."""
        intents: List[str] = []
        for name, pattern in INTENT_PATTERNS:
            if pattern.search(text):
                intents.append(name)
        if not intents:
            intents.append("lookup")
        return intents

    def detect_doc_types(self, text: str) -> List[str]:
        """Detect document type hints from query text."""
        doc_types: List[str] = []
        for name, pattern in DOC_TYPE_PATTERNS:
            if pattern.search(text):
                doc_types.append(name)
        return doc_types

    def detect_entities(self, text: str) -> List[str]:
        """Detect regulated entity hints."""
        entities: List[str] = []
        for name, pattern in ENTITY_PATTERNS:
            if pattern.search(text):
                entities.append(name)
        return entities

    def detect_topics(self, text: str) -> List[str]:
        """Map query text to topic categories from topics.yaml."""
        matched: List[str] = []
        lower = text.lower()
        for topic_key, topic_data in self.topics.items():
            keywords = topic_data.get("keywords", [])
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw.lower()) + r"\b", lower):
                    matched.append(topic_key)
                    break
        return matched

    def build_query_variants(self, text: str) -> List[str]:
        """Generate additive query variants via abbreviation and synonym expansions.

        Expansion is strictly additive (added as subsequent variants), never replaces original.
        """
        variants: List[str] = [text.strip()]
        lower = text.lower()

        # 1. Abbreviation expansions: Acronym -> Full form
        expanded_text = text
        has_abbr_expansion = False
        for abbr, full in self.abbreviations.items():
            pattern = re.compile(r"\b" + re.escape(abbr) + r"(?:s|'s)?\b", re.IGNORECASE)
            if pattern.search(text):
                # Replace acronym with full expansion
                expanded_text = pattern.sub(full, expanded_text)
                has_abbr_expansion = True

        if has_abbr_expansion and expanded_text.strip() != text.strip():
            if expanded_text.strip() not in variants:
                variants.append(expanded_text.strip())

        # Also add single acronym expansions if there are multiple
        for abbr, full in self.abbreviations.items():
            pattern = re.compile(r"\b" + re.escape(abbr) + r"(?:s|'s)?\b", re.IGNORECASE)
            if pattern.search(text):
                single_exp = pattern.sub(full, text).strip()
                if single_exp not in variants:
                    variants.append(single_exp)

        # 2. Reverse expansion: Full form -> Acronym
        collapsed_text = text
        has_rev_expansion = False
        for full_lower, abbr in self.reverse_abbreviations.items():
            pattern = re.compile(r"\b" + re.escape(full_lower) + r"(?:s|'s)?\b", re.IGNORECASE)
            if pattern.search(lower):
                collapsed_text = pattern.sub(abbr, collapsed_text)
                has_rev_expansion = True

        if has_rev_expansion and collapsed_text.strip() != text.strip():
            if collapsed_text.strip() not in variants:
                variants.append(collapsed_text.strip())

        return variants

    def analyze(self, query: str, store: Optional[Any] = None) -> QueryPlan:
        """Analyze a user query and return a deterministic QueryPlan."""
        raw = query.strip() if query else ""
        normalised = re.sub(r"\s+", " ", raw).strip()

        # Date and year parsing
        explicit_dates, as_of_date, years, warnings = self.parse_dates_and_years(raw)

        # Temporal intent
        wants_current = bool(RE_CURRENT.search(raw)) or (as_of_date is not None)
        wants_history = bool(RE_HISTORY.search(raw))

        # Identifiers
        identifiers = self.extract_identifiers(raw, store=store)

        # Document types, entities, topics
        doc_type_hints = self.detect_doc_types(raw)
        entity_hints = self.detect_entities(raw)
        topics = self.detect_topics(raw)

        # Query variants
        query_variants = self.build_query_variants(raw)

        # Intents
        intents = self.detect_intents(raw)

        return QueryPlan(
            raw=raw,
            normalised=normalised,
            identifiers=identifiers,
            years=years,
            explicit_dates=explicit_dates,
            as_of_date=as_of_date,
            wants_current=wants_current,
            wants_history=wants_history,
            doc_type_hints=doc_type_hints,
            entity_hints=entity_hints,
            topics=topics,
            query_variants=query_variants,
            intents=intents,
            warnings=warnings,
        )


# Global singleton instance for easy import
_ANALYZER = QueryAnalyzer()


def analyze_query(query: str, store: Optional[Any] = None) -> QueryPlan:
    """Public helper function to analyze a query."""
    return _ANALYZER.analyze(query, store=store)
