"""HTML circular parser using selectolax and trafilatura."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import trafilatura
from bs4 import BeautifulSoup
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ingest.parse.models import ParsedBlock, ParsedDocument, ParsedPage, ParsedTable
from ingest.parse.pdf import table_to_markdown

logger = logging.getLogger(__name__)


def parse_html(file_path: Path, doc_id: str) -> ParsedDocument:
    """Extract clean main content text and tables from HTML circulars."""
    raw_html = file_path.read_text(encoding="utf-8", errors="replace")
    tree = HTMLParser(raw_html)
    warnings: List[str] = []
    tables: List[ParsedTable] = []

    # 1. Extract HTML tables
    soup = BeautifulSoup(raw_html, "html.parser")
    for page_no, tbl in enumerate(soup.find_all("table"), start=1):
        rows: List[List[str]] = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if len(rows) >= 2:
            md = table_to_markdown(rows)
            if md:
                tables.append(ParsedTable(page_no=page_no, markdown=md))

    # 2. Extract main text using trafilatura
    extracted_text = trafilatura.extract(
        raw_html,
        include_links=True,
        include_tables=False,
        output_format="txt",
    )

    # Fallback to selectolax / bs4 body extraction if trafilatura returns little text
    if not extracted_text or len(extracted_text.strip()) < 50:
        body_node = tree.body
        if body_node:
            # Strip scripts and styles
            for tag in body_node.css("script, style, nav, footer, header"):
                tag.decompose()
            extracted_text = body_node.text(separator="\n\n", strip=True)
        else:
            extracted_text = soup.get_text("\n\n", strip=True)
        warnings.append("Used selectolax/bs4 fallback for HTML content")

    blocks = [
        ParsedBlock(text=para.strip(), type="text")
        for para in extracted_text.split("\n\n")
        if para.strip()
    ]

    page = ParsedPage(
        page_no=1,
        text=extracted_text,
        blocks=blocks,
    )

    return ParsedDocument(
        doc_id=doc_id,
        pages=[page],
        full_text=extracted_text,
        tables=tables,
        extraction_method="html",
        warnings=warnings,
    )
