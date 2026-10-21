"""Regulatory-aware lexical search, tokenizer, BM25 indexing, and identifier lookup.

Implements:
1. RegulatoryTokenizer: preserves numbers, percentages, currencies, clause references,
   whole regulatory circular identifiers, and essential regulatory stopwords.
2. Dual BM25 indexes (plain + stemmed) over chunk.text_for_embedding using bm25s.
3. Inverted identifier index for exact circular/direction reference lookups.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import bm25s
import numpy as np
import snowballstemmer
import zstandard as zstd

from ingest.normalise import (
    RE_AP_DIR,
    RE_DEPT_CIRCULAR,
    RE_RBI_PREFIX,
    normalise_circular_no,
)

# Essential stopwords to KEEP (must NEVER be removed in regulatory contexts)
PROTECTED_STOPWORDS: Set[str] = {
    "not",
    "no",
    "shall",
    "may",
    "except",
    "unless",
    "without",
    "against",
    "between",
    "under",
}

# Standard English stopwords (with protected regulatory words excluded)
DEFAULT_STOPWORDS: Set[str] = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "both",
    "but",
    "by",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
} - PROTECTED_STOPWORDS

# Regex patterns for tokenization
RE_CLAUSE = re.compile(r"\b(\d+(?:\.\d+)*(?:\([a-z0-9]+\))+)", re.IGNORECASE)
RE_CLAUSE_SPLIT = re.compile(r"[\(\)]+")
RE_CURRENCY_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹)\s*(\d+(?:[,\.]\d+)*(?:\s*(?:crore|lakh|thousand))?)", re.IGNORECASE
)
RE_PERCENTAGE = re.compile(r"\b\d+(?:\.\d+)?%", re.IGNORECASE)
RE_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def canonicalise_identifier_token(text: str) -> str:
    """Turn regulatory identifiers into unified snake_case tokens.

    Examples:
        'A.P. (DIR Series) Circular No. 23' -> 'ap_dir_series_circular_23'
        'RBI/2025-26/90' -> 'rbi/2025-26/90'
        'DOR.MCS.REC.59/01.01.003/2025-26' -> 'dor.mcs.rec.59/01.01.003/2025-26'
    """
    clean = text.strip()
    ap_match = RE_AP_DIR.search(clean)
    if ap_match:
        num = ap_match.group(2)
        return f"ap_dir_series_circular_{num}"
    return clean.lower()


class RegulatoryTokenizer:
    """Specialised tokenizer for Indian banking regulation texts."""

    def __init__(self, stopwords: Optional[Set[str]] = None) -> None:
        self.stopwords = stopwords if stopwords is not None else DEFAULT_STOPWORDS
        self.stemmer = snowballstemmer.stemmer("english")

    def tokenize(self, text: str, stem: bool = False) -> List[str]:
        """Tokenize regulatory text preserving clauses, numbers, and identifiers."""
        if not text:
            return []

        tokens: List[str] = []

        # 1. Extract and preserve RBI circular identifiers
        # Check for A.P. (DIR Series)
        for m in RE_AP_DIR.finditer(text):
            tok = canonicalise_identifier_token(m.group(0))
            tokens.append(tok)
            # also extract the number
            tokens.append(m.group(2))

        # Check for RBI/ prefix identifiers
        for m in RE_RBI_PREFIX.finditer(text):
            tok = m.group(1).lower()
            tokens.append(tok)

        # Check for Department Circular identifiers
        for m in RE_DEPT_CIRCULAR.finditer(text):
            tok = m.group(1).lower()
            tokens.append(tok)

        # 2. Extract clause references like 5.2(a) -> ['5.2(a)', '5.2', 'a']
        for m in RE_CLAUSE.finditer(text):
            clause_str = m.group(1).lower()
            tokens.append(clause_str)
            # Extract parts: '5.2' and 'a'
            parts = [p for p in RE_CLAUSE_SPLIT.split(clause_str) if p]
            for p in parts:
                if p != clause_str:
                    tokens.append(p)

        # 3. Extract percentages
        for m in RE_PERCENTAGE.finditer(text):
            tokens.append(m.group(0).lower())

        # 4. Extract currency mentions ("Rs. 5 crore", "Rs. 10 lakh")
        for m in RE_CURRENCY_AMOUNT.finditer(text):
            tokens.append("rs")

        # 5. General word and symbol segmentation
        # Replace punctuation except for slashes/hyphens inside identifiers or decimals in numbers
        # Match word tokens, identifiers, currency words, numbers
        raw_words = re.findall(r"[A-Za-z0-9_%/.\-]+", text.lower())
        for word in raw_words:
            # Strip outer punctuation
            w = word.strip(".,;:()[]\"'{}")
            if not w:
                continue

            # Check if it's "rs." -> "rs"
            if w in ("rs.", "rs", "₹", "inr"):
                tokens.append("rs")
                continue

            # Skip common stopwords
            if w in self.stopwords:
                continue

            # Split compound tokens like "abc/def" if not an RBI identifier
            if "/" in w and not (w.startswith("rbi/") or "rec." in w or "co." in w):
                sub_parts = [p.strip(".,;:()") for p in w.split("/") if p.strip(".,;:()")]
                for sp in sub_parts:
                    if sp and sp not in self.stopwords:
                        tokens.append(sp)
                continue

            tokens.append(w)

        # 6. Apply Snowball English stemming if requested
        if stem:
            stemmed_tokens: List[str] = []
            for t in tokens:
                # Do not stem structured identifiers or numbers
                if "/" in t or "%" in t or RE_NUMBER.match(t) or "_" in t or "(" in t:
                    stemmed_tokens.append(t)
                else:
                    stemmed_tokens.append(self.stemmer.stemWord(t))
            return stemmed_tokens

        return tokens


class DualBM25Index:
    """Manages dual BM25 fields (plain + stemmed) with score normalisation."""

    def __init__(
        self,
        k1: float = 1.2,
        b: float = 0.75,
        tokenizer: Optional[RegulatoryTokenizer] = None,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or RegulatoryTokenizer()
        self.bm25_plain: Optional[bm25s.BM25] = None
        self.bm25_stemmed: Optional[bm25s.BM25] = None
        self.chunk_ids: List[str] = []

    def index(self, chunk_ids: List[str], texts_for_embedding: List[str]) -> None:
        """Build and fit plain and stemmed BM25 indexes."""
        self.chunk_ids = list(chunk_ids)

        # Tokenize plain
        plain_corpus = [self.tokenizer.tokenize(text, stem=False) for text in texts_for_embedding]
        self.bm25_plain = bm25s.BM25(k1=self.k1, b=self.b)
        self.bm25_plain.index(plain_corpus)

        # Tokenize stemmed
        stemmed_corpus = [self.tokenizer.tokenize(text, stem=True) for text in texts_for_embedding]
        self.bm25_stemmed = bm25s.BM25(k1=self.k1, b=self.b)
        self.bm25_stemmed.index(stemmed_corpus)

    def search(
        self,
        query: str,
        k: int = 10,
        allow_mask: Optional[np.ndarray] = None,
    ) -> Tuple[List[str], List[float], List[int]]:
        """Search both BM25 fields and combine scores deterministically.

        Returns (chunk_ids, scores, ranks).
        """
        if not self.chunk_ids or self.bm25_plain is None or self.bm25_stemmed is None:
            return [], [], []

        query_plain = self.tokenizer.tokenize(query, stem=False)
        query_stemmed = self.tokenizer.tokenize(query, stem=True)

        if not query_plain and not query_stemmed:
            return [], [], []

        # Retrieve scores across entire corpus
        plain_scores = (
            self.bm25_plain.get_scores(query_plain)
            if query_plain
            else np.zeros(len(self.chunk_ids))
        )
        stemmed_scores = (
            self.bm25_stemmed.get_scores(query_stemmed)
            if query_stemmed
            else np.zeros(len(self.chunk_ids))
        )

        # Normalise scores: divide by maximum score if positive
        max_plain = float(np.max(plain_scores)) if len(plain_scores) > 0 else 0.0
        max_stemmed = float(np.max(stemmed_scores)) if len(stemmed_scores) > 0 else 0.0

        norm_plain = (plain_scores / max_plain) if max_plain > 0.0 else plain_scores
        norm_stemmed = (stemmed_scores / max_stemmed) if max_stemmed > 0.0 else stemmed_scores

        # Final lexical score = max of normalised scores
        combined_scores = np.maximum(norm_plain, norm_stemmed)

        # Apply pre-filtering allow mask
        if allow_mask is not None:
            if len(allow_mask) != len(combined_scores):
                raise ValueError("allow_mask length does not match corpus size")
            # Set disallowed scores to -inf
            combined_scores = np.where(allow_mask, combined_scores, -np.inf)

        # Find top k matches
        total_chunks = len(self.chunk_ids)
        effective_k = min(k, total_chunks)

        if effective_k <= 0:
            return [], [], []

        # Sort indices by score descending
        sorted_indices = np.argsort(-combined_scores)[:effective_k]

        matched_ids: List[str] = []
        matched_scores: List[float] = []
        ranks: List[int] = []

        for rank, idx in enumerate(sorted_indices, start=1):
            sc = float(combined_scores[idx])
            if np.isneginf(sc):
                # Masked out or no match
                break
            matched_ids.append(self.chunk_ids[idx])
            matched_scores.append(round(sc, 5))
            ranks.append(rank)

        return matched_ids, matched_scores, ranks

    def save(self, output_dir: Path) -> None:
        """Persist BM25 plain and stemmed indexes to disk."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        plain_dir = output_dir / "bm25_plain"
        stemmed_dir = output_dir / "bm25_stemmed"

        if self.bm25_plain is not None:
            self.bm25_plain.save(str(plain_dir))
        if self.bm25_stemmed is not None:
            self.bm25_stemmed.save(str(stemmed_dir))

        meta = {
            "k1": self.k1,
            "b": self.b,
            "chunk_ids": self.chunk_ids,
        }
        with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)

    @classmethod
    def load(cls, index_dir: Path) -> DualBM25Index:
        """Load persisted BM25 indexes from disk."""
        index_dir = Path(index_dir)
        meta_file = index_dir / "meta.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"Missing BM25 metadata: {meta_file}")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        inst = cls(k1=meta.get("k1", 1.2), b=meta.get("b", 0.75))
        inst.chunk_ids = meta.get("chunk_ids", [])

        plain_dir = index_dir / "bm25_plain"
        stemmed_dir = index_dir / "bm25_stemmed"

        if plain_dir.exists():
            inst.bm25_plain = bm25s.BM25.load(str(plain_dir), load_corpus=False)
        if stemmed_dir.exists():
            inst.bm25_stemmed = bm25s.BM25.load(str(stemmed_dir), load_corpus=False)

        return inst


class IdentifierIndex:
    """Inverted index mapping normalized circular and direction identifiers to chunk IDs."""

    def __init__(self, mapping: Optional[Dict[str, List[str]]] = None) -> None:
        self.mapping: Dict[str, List[str]] = mapping or {}

    def add(self, identifier: str, chunk_id: str) -> None:
        """Add an identifier to chunk mapping."""
        if not identifier or not chunk_id:
            return
        key = self._canonical_key(identifier)
        if key not in self.mapping:
            self.mapping[key] = []
        if chunk_id not in self.mapping[key]:
            self.mapping[key].append(chunk_id)

    def lookup(self, text: str) -> List[str]:
        """Look up chunk IDs by circular number or identifier."""
        if not text:
            return []

        # Try canonical key direct match
        key = self._canonical_key(text)
        if key in self.mapping:
            return list(self.mapping[key])

        # Try normalise_circular_no
        norm = normalise_circular_no(text)
        if norm:
            norm_key = self._canonical_key(norm)
            if norm_key in self.mapping:
                return list(self.mapping[norm_key])

        return []

    def _canonical_key(self, text: str) -> str:
        """Generate normalized search key."""
        # Check if A.P. DIR series
        ap_match = RE_AP_DIR.search(text)
        if ap_match:
            return f"ap_dir_series_circular_{ap_match.group(2)}"
        return text.strip().lower().replace(" ", "")

    def save(self, filepath: Path) -> None:
        """Save compressed inverted index using zstandard."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = json.dumps(self.mapping).encode("utf-8")
        cctx = zstd.ZstdCompressor(level=3)
        compressed = cctx.compress(raw_bytes)
        with open(filepath, "wb") as f:
            f.write(compressed)

    @classmethod
    def load(cls, filepath: Path) -> IdentifierIndex:
        """Load compressed inverted index."""
        filepath = Path(filepath)
        if not filepath.exists():
            return cls({})
        with open(filepath, "rb") as f:
            compressed = f.read()
        dctx = zstd.ZstdDecompressor()
        decompressed = dctx.decompress(compressed)
        mapping = json.loads(decompressed.decode("utf-8"))
        return cls(mapping=mapping)


def build_identifier_index_from_chunks(chunks_records: List[Dict[str, Any]]) -> IdentifierIndex:
    """Build an inverted identifier index from chunk records."""
    index = IdentifierIndex()

    for chunk in chunks_records:
        chunk_id = chunk["chunk_id"]
        circular_no = chunk.get("circular_no")
        text = chunk.get("text", "")
        title = chunk.get("title", "")

        # 1. Circular number from metadata
        if circular_no:
            index.add(circular_no, chunk_id)
            norm_no = normalise_circular_no(circular_no)
            if norm_no and norm_no != circular_no:
                index.add(norm_no, chunk_id)

        # 2. Extract identifiers from chunk text and title
        combined_text = f"{title} {text}"
        for m in RE_RBI_PREFIX.finditer(combined_text):
            index.add(m.group(1), chunk_id)
        for m in RE_DEPT_CIRCULAR.finditer(combined_text):
            index.add(m.group(1), chunk_id)
        for m in RE_AP_DIR.finditer(combined_text):
            index.add(m.group(0), chunk_id)

    return index
