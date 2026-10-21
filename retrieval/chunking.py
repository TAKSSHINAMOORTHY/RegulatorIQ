"""Structure-aware, deterministic chunker for RBI regulatory documents."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from ingest.manifest import ManifestRecord
from ingest.parse.models import ParsedDocument
from ingest.structure import SectionNode

CHUNKING_VERSION = "2.0.0"

# Sentence boundary regex that protects abbreviations, decimals, and dates
RE_SENTENCE_SPLIT = re.compile(
    r"(?<!\bRs)(?<!\bNo)(?<!\bSec)(?<!\bi\.e)(?<!\be\.g)(?<!\bLtd)\.(?!\d)(?:\s+|\n+)(?=[A-Z0-9\"'\(])"
)


class TokenCounter:
    """Token counter using HuggingFace tokenizer or safe approx fallback."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self.tokenizer = None
        self.is_fallback = False
        try:
            from transformers import AutoTokenizer  # type: ignore

            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        except Exception:
            self.is_fallback = True

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self.tokenizer and not self.is_fallback:
            try:
                return len(self.tokenizer.encode(text, add_special_tokens=False))
            except Exception:
                pass
        # Fallback: ceil(words * 1.3)
        words = text.split()
        return math.ceil(len(words) * 1.3)

    @property
    def label(self) -> str:
        return "approx" if self.is_fallback else f"hf:{self.model_name}"


class ChunkRecord(BaseModel):
    """Schema for chunks.parquet."""

    chunk_id: str
    doc_id: str
    ordinal: int
    chunk_type: str  # "text" | "table"
    text: str
    text_for_embedding: str
    section_path: str
    para_ref: Optional[str] = None
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    token_count: int
    token_counter: str
    doc_type: str
    title: str
    circular_no: Optional[str] = None
    issue_date: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_current: bool = True
    validity_confidence: str = "medium"
    topics: List[str] = Field(default_factory=list)
    applicability_entities: List[str] = Field(default_factory=list)
    lang: str = "en"
    source_url: str
    structure_confidence: str = "medium"
    chunking_version: str = CHUNKING_VERSION


def split_sentences_safely(text: str) -> List[str]:
    """Split text into sentences while guarding currency, abbreviations, clause numbers, and dates."""
    if not text:
        return []
    raw_pieces = RE_SENTENCE_SPLIT.split(text.strip())
    sentences = []
    for piece in raw_pieces:
        p = piece.strip()
        if p:
            if not p.endswith("."):
                p += "."
            sentences.append(p)
    return sentences if sentences else [text.strip()]


def build_contextual_header(
    doc_type: str,
    title: str,
    circular_no: Optional[str],
    issue_date: Optional[str],
    section_path: str,
) -> str:
    """[{doc_type}] {title} | {circular_no} | {issue_date} | {section_path}."""
    parts = [f"[{doc_type}] {title}"]
    if circular_no:
        parts.append(circular_no)
    if issue_date:
        parts.append(issue_date)
    if section_path and section_path != "General":
        parts.append(section_path)
    return " | ".join(parts)


def chunk_section(
    section: SectionNode,
    token_counter: TokenCounter,
    target_tokens: int = 400,
    max_tokens: int = 512,
    min_tokens: int = 80,
    overlap_tokens: int = 60,
) -> List[Tuple[str, int, int]]:
    """Chunk section text with token boundaries.

    Returns:
        List of (chunk_text, token_count, char_start)
    """
    text = section.text.strip()
    if not text:
        return []

    tokens = token_counter.count(text)
    if tokens <= max_tokens:
        return [(text, tokens, 0)]

    sentences = split_sentences_safely(text)
    chunks: List[Tuple[str, int, int]] = []
    current_sentences: List[str] = []
    current_tokens = 0
    char_cursor = 0

    for sent in sentences:
        sent_tokens = token_counter.count(sent)
        # If single sentence exceeds max_tokens, split by sub-phrases
        if sent_tokens > max_tokens:
            words = sent.split()
            sub_chunk = []
            sub_count = 0
            for w in words:
                sub_chunk.append(w)
                sub_count = token_counter.count(" ".join(sub_chunk))
                if sub_count >= target_tokens:
                    sub_text = " ".join(sub_chunk)
                    chunks.append((sub_text, sub_count, char_cursor))
                    char_cursor += len(sub_text) + 1
                    sub_chunk = []
                    sub_count = 0
            if sub_chunk:
                sub_text = " ".join(sub_chunk)
                chunks.append((sub_text, token_counter.count(sub_text), char_cursor))
                char_cursor += len(sub_text) + 1
            continue

        if current_tokens + sent_tokens > max_tokens and current_sentences:
            chunk_str = " ".join(current_sentences)
            chunks.append((chunk_str, current_tokens, char_cursor))
            char_cursor += len(chunk_str) + 1

            # Keep overlap sentences within section
            overlap_sentences: List[str] = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tok = token_counter.count(s)
                if overlap_count + s_tok <= overlap_tokens:
                    overlap_sentences.insert(0, s)
                    overlap_count += s_tok
                else:
                    break

            current_sentences = overlap_sentences + [sent]
            current_tokens = overlap_count + sent_tokens
        else:
            current_sentences.append(sent)
            current_tokens += sent_tokens

    if current_sentences:
        chunk_str = " ".join(current_sentences)
        # If last chunk is very small and previous chunk exists, merge if under max_tokens
        if chunks and current_tokens < min_tokens:
            prev_str, prev_tok, prev_cursor = chunks[-1]
            if prev_tok + current_tokens <= max_tokens:
                chunks[-1] = (f"{prev_str} {chunk_str}", prev_tok + current_tokens, prev_cursor)
            else:
                chunks.append((chunk_str, current_tokens, char_cursor))
        else:
            chunks.append((chunk_str, current_tokens, char_cursor))

    return chunks


def chunk_table(
    table_markdown: str,
    token_counter: TokenCounter,
    max_tokens: int = 420,
) -> List[Tuple[str, int]]:
    """Split oversized tables row-by-row repeating the header row in each piece."""
    lines = [line.strip() for line in table_markdown.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        # Not a formatted markdown table; split lines directly
        words = table_markdown.split()
        line_pieces: List[Tuple[str, int]] = []
        for i in range(0, len(words), 300):
            sub = " ".join(words[i : i + 300])
            line_pieces.append((sub, token_counter.count(sub)))
        return line_pieces or [(table_markdown, token_counter.count(table_markdown))]

    header_lines = lines[:2]
    header_text = "\n".join(header_lines)
    header_tokens = token_counter.count(header_text)

    data_rows = lines[2:]
    pieces: List[Tuple[str, int]] = []
    current_rows: List[str] = []
    current_tokens = header_tokens

    for row in data_rows:
        row_tokens = token_counter.count(row)
        if current_tokens + row_tokens > max_tokens and current_rows:
            piece_text = header_text + "\n" + "\n".join(current_rows)
            pieces.append((piece_text, current_tokens))
            current_rows = [row]
            current_tokens = header_tokens + row_tokens
        else:
            current_rows.append(row)
            current_tokens += row_tokens

    if current_rows:
        piece_text = header_text + "\n" + "\n".join(current_rows)
        pieces.append((piece_text, current_tokens))

    return pieces


def chunk_document(
    parsed: ParsedDocument,
    manifest: ManifestRecord,
    sections: List[SectionNode],
    validity_info: Dict[str, Any],
    topics: List[str],
    entities: List[str],
    token_counter: TokenCounter,
) -> List[ChunkRecord]:
    """Generate structured, deterministic chunks from a parsed document."""
    chunks: List[ChunkRecord] = []
    ordinal = 0
    doc_id = parsed.doc_id

    # Exclude Hindi-only documents from chunks
    if not parsed.is_primary_english:
        return []

    # 1. Chunk tables as chunk_type="table" (split oversized tables row-by-row)
    for tbl in parsed.tables:
        table_pieces = chunk_table(tbl.markdown, token_counter, max_tokens=420)
        for piece_idx, (tbl_text, _) in enumerate(table_pieces):
            ordinal += 1
            caption_suffix = f" (Part {piece_idx + 1})" if len(table_pieces) > 1 else ""
            caption = (tbl.caption or "Table") + caption_suffix
            header = build_contextual_header(
                doc_type=manifest.doc_type,
                title=manifest.title,
                circular_no=manifest.circular_no_normalised or manifest.circular_no,
                issue_date=manifest.issue_date,
                section_path=caption,
            )
            embedding_text = f"{header}\n\n{tbl_text}"
            tok_count = token_counter.count(embedding_text)

            # Hard cap guarantee <= 512
            if tok_count > 512:
                words = tbl_text.split()
                tbl_text = " ".join(words[:320])
                embedding_text = f"{header}\n\n{tbl_text}"
                tok_count = token_counter.count(embedding_text)

            chunk_id = hashlib.sha1(
                f"{doc_id}_{ordinal}_{tbl_text[:64]}".encode("utf-8")
            ).hexdigest()

            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    ordinal=ordinal,
                    chunk_type="table",
                    text=tbl_text,
                    text_for_embedding=embedding_text,
                    section_path=caption,
                    para_ref=None,
                    page_start=tbl.page_no,
                    page_end=tbl.page_no,
                    char_start=0,
                    char_end=len(tbl_text),
                    token_count=tok_count,
                    token_counter=token_counter.label,
                    doc_type=manifest.doc_type,
                    title=manifest.title,
                    circular_no=manifest.circular_no_normalised or manifest.circular_no,
                    issue_date=manifest.issue_date,
                    valid_from=validity_info.get("valid_from"),
                    valid_to=validity_info.get("valid_to"),
                    is_current=validity_info.get("is_current", True),
                    validity_confidence=validity_info.get("validity_confidence", "medium"),
                    topics=topics,
                    applicability_entities=entities,
                    lang=parsed.lang,
                    source_url=manifest.source_page_url or manifest.file_url,
                    structure_confidence="high",
                )
            )

    # 2. Chunk text sections
    for sec in sections:
        section_pieces = chunk_section(sec, token_counter, target_tokens=360, max_tokens=440)
        for piece_text, _, char_offset in section_pieces:
            ordinal += 1
            header = build_contextual_header(
                doc_type=manifest.doc_type,
                title=manifest.title,
                circular_no=manifest.circular_no_normalised or manifest.circular_no,
                issue_date=manifest.issue_date,
                section_path=sec.section_path,
            )
            embedding_text = f"{header}\n\n{piece_text}"
            tok_count = token_counter.count(embedding_text)

            # Hard cap guarantee <= 512
            if tok_count > 512:
                words = piece_text.split()
                piece_text = " ".join(words[:320])
                embedding_text = f"{header}\n\n{piece_text}"
                tok_count = token_counter.count(embedding_text)

            chunk_id = hashlib.sha1(
                f"{doc_id}_{ordinal}_{piece_text[:64]}".encode("utf-8")
            ).hexdigest()

            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    ordinal=ordinal,
                    chunk_type="text",
                    text=piece_text,
                    text_for_embedding=embedding_text,
                    section_path=sec.section_path,
                    para_ref=sec.para_ref,
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                    char_start=char_offset,
                    char_end=char_offset + len(piece_text),
                    token_count=tok_count,
                    token_counter=token_counter.label,
                    doc_type=manifest.doc_type,
                    title=manifest.title,
                    circular_no=manifest.circular_no_normalised or manifest.circular_no,
                    issue_date=manifest.issue_date,
                    valid_from=validity_info.get("valid_from"),
                    valid_to=validity_info.get("valid_to"),
                    is_current=validity_info.get("is_current", True),
                    validity_confidence=validity_info.get("validity_confidence", "medium"),
                    topics=topics,
                    applicability_entities=entities,
                    lang=parsed.lang,
                    source_url=manifest.source_page_url or manifest.file_url,
                    structure_confidence="medium",
                )
            )

    return chunks
