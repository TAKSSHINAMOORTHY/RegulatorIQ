"""Pydantic v2 schemas for parsed documents and layout blocks."""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

ExtractionMethod = Literal["text", "ocr", "html", "docx", "xlsx"]


class ParsedBlock(BaseModel):
    """Text block with layout bounding box and typography metadata."""

    text: str
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    type: str = "text"  # "text", "heading", "table"
    font_size: float = 10.0
    is_bold: bool = False


class ParsedTable(BaseModel):
    """Extracted table converted to Markdown."""

    page_no: int
    markdown: str
    caption: Optional[str] = None


class ParsedPage(BaseModel):
    """Page representation with blocks and page number."""

    page_no: int
    text: str
    blocks: List[ParsedBlock] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """Complete parsed document output across all file formats."""

    doc_id: str
    pages: List[ParsedPage] = Field(default_factory=list)
    full_text: str = ""
    tables: List[ParsedTable] = Field(default_factory=list)
    lang: str = "en"
    is_primary_english: bool = True
    extraction_method: ExtractionMethod = "text"
    quality_score: float = 1.0
    warnings: List[str] = Field(default_factory=list)
