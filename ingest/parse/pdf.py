"""PDF parsing using PyMuPDF (fitz) and pdfplumber."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Sequence

import fitz  # PyMuPDF
import pdfplumber

from ingest.parse.models import ParsedBlock, ParsedDocument, ParsedPage, ParsedTable

logger = logging.getLogger(__name__)


def table_to_markdown(table: Sequence[Sequence[Any]]) -> str:
    """Convert raw 2D string list into GitHub-flavored Markdown table."""
    if not table or not any(table):
        return ""
    clean_rows: List[List[str]] = []
    for row in table:
        clean_row = [str(cell or "").strip().replace("\n", " ").replace("|", "\\|") for cell in row]
        clean_rows.append(clean_row)

    if not clean_rows:
        return ""

    headers = clean_rows[0]
    separator = ["---"] * len(headers)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in clean_rows[1:]:
        # Pad row if columns are missing
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(row[: len(headers)]) + " |")

    return "\n".join(lines)


def parse_pdf(file_path: Path, doc_id: str) -> ParsedDocument:
    """Extract structured pages, reading-order repaired blocks, and tables from PDF."""
    pages: List[ParsedPage] = []
    tables: List[ParsedTable] = []
    all_page_texts: List[str] = []
    warnings: List[str] = []

    # 1. Extract text and blocks via PyMuPDF
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        warnings.append(f"PyMuPDF open error: {e}")
        return ParsedDocument(
            doc_id=doc_id,
            warnings=warnings,
            extraction_method="text",
            quality_score=0.0,
        )

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        rect = page.rect
        width = rect.width
        raw_blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)

        # Reading-order repair for two-column pages:
        # Detect if blocks span both left and right sides
        has_two_columns = False
        midpoint = width / 2.0
        left_blocks = [b for b in raw_blocks if b[0] < midpoint and b[2] <= midpoint + 20]
        right_blocks = [b for b in raw_blocks if b[0] >= midpoint - 20]
        if len(left_blocks) >= 2 and len(right_blocks) >= 2:
            has_two_columns = True

        # Sort blocks: by column band if two-column, otherwise by vertical y0
        if has_two_columns:
            sorted_blocks = sorted(raw_blocks, key=lambda b: (0 if b[0] < midpoint else 1, b[1]))
        else:
            sorted_blocks = sorted(raw_blocks, key=lambda b: b[1])

        parsed_blocks: List[ParsedBlock] = []
        page_text_pieces: List[str] = []

        for b in sorted_blocks:
            x0, y0, x1, y1, text, _, b_type = b
            clean_text = text.strip()
            if not clean_text:
                continue

            parsed_blocks.append(
                ParsedBlock(
                    text=clean_text,
                    bbox=(x0, y0, x1, y1),
                    type="text" if b_type == 0 else "image",
                )
            )
            page_text_pieces.append(clean_text)

        joined_page_text = "\n\n".join(page_text_pieces)
        all_page_texts.append(joined_page_text)
        pages.append(
            ParsedPage(
                page_no=page_idx + 1,
                text=joined_page_text,
                blocks=parsed_blocks,
            )
        )

    # 2. Extract tables via pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_idx, p in enumerate(pdf.pages):
                extracted = p.extract_tables()
                for t in extracted:
                    md = table_to_markdown(t)
                    if md:
                        tables.append(ParsedTable(page_no=page_idx + 1, markdown=md))
    except Exception as e:
        warnings.append(f"Table extraction notice: {e}")

    full_text = "\n\n--- Page Break ---\n\n".join(all_page_texts)

    return ParsedDocument(
        doc_id=doc_id,
        pages=pages,
        full_text=full_text,
        tables=tables,
        extraction_method="text",
        warnings=warnings,
    )
