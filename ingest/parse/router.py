"""Document parser router, cleaning pipeline, and language detector."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from langdetect import DetectorFactory, detect

from config.paths import PARSED_DIR, QUARANTINE_DIR, ROOT
from ingest.clean import (
    clean_unicode,
    compute_quality_score,
    dehyphenate,
    normalise_spacing,
    remove_letterhead_boilerplate,
    remove_repeating_headers_footers,
)
from ingest.manifest import ManifestRecord
from ingest.parse.html import parse_html
from ingest.parse.models import ParsedDocument
from ingest.parse.office import parse_docx, parse_xlsx
from ingest.parse.pdf import parse_pdf

logger = logging.getLogger(__name__)

# Enforce deterministic langdetect outputs
DetectorFactory.seed = 0
PARSER_VERSION = "2.0.0"


def detect_document_language(text: str) -> tuple[str, bool]:
    """Detect language and determine if primary language is English."""
    if not text or len(text.strip()) < 20:
        return "en", True
    try:
        sample = text[:2000]
        lang = detect(sample)
        is_english = lang.startswith("en")
        return lang, is_english
    except Exception:
        return "en", True


def parse_and_clean_document(record: ManifestRecord) -> Optional[ParsedDocument]:
    """Route document to format-specific parser, clean text, and save parsed JSON."""
    doc_id = record.doc_id
    output_json_path = PARSED_DIR / f"{doc_id}.json"

    # Resumable: if already parsed, return existing parsed document
    if output_json_path.exists():
        try:
            return ParsedDocument.model_validate_json(output_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if not record.local_path:
        return None

    file_path = (
        ROOT / record.local_path
        if not Path(record.local_path).is_absolute()
        else Path(record.local_path)
    )
    if not file_path.exists():
        quarantine_file = QUARANTINE_DIR / f"{doc_id}.json"
        quarantine_file.write_text(
            json.dumps(
                {"doc_id": doc_id, "reason": "Local raw file missing", "path": str(file_path)}
            ),
            encoding="utf-8",
        )
        return None

    ext = (record.file_ext or file_path.suffix.lstrip(".")).lower()

    try:
        # Route by file extension
        if ext == "pdf":
            parsed = parse_pdf(file_path, doc_id)
        elif ext in ("html", "htm", "aspx"):
            parsed = parse_html(file_path, doc_id)
        elif ext == "docx":
            parsed = parse_docx(file_path, doc_id)
        elif ext in ("xlsx", "xls"):
            parsed = parse_xlsx(file_path, doc_id)
        else:
            quarantine_file = QUARANTINE_DIR / f"{doc_id}.json"
            quarantine_file.write_text(
                json.dumps({"doc_id": doc_id, "reason": f"Unsupported extension {ext}"}),
                encoding="utf-8",
            )
            return None

        # Clean document text
        page_texts = [p.text for p in parsed.pages]
        # 1. Remove repeating headers/footers
        cleaned_page_texts = remove_repeating_headers_footers(page_texts)

        final_pages = []
        for p, clean_txt in zip(parsed.pages, cleaned_page_texts):
            # 2. Unicode NFKC & ligatures
            clean_txt = clean_unicode(clean_txt)
            # 3. De-hyphenate line breaks
            clean_txt = dehyphenate(clean_txt)
            # 4. Spacing normalisation
            clean_txt = normalise_spacing(clean_txt)
            p.text = clean_txt
            final_pages.append(p)

        parsed.pages = final_pages
        combined_text = "\n\n".join(p.text for p in final_pages)

        # 5. Remove letterhead boilerplate from document body
        body_cleaned, boilerplate = remove_letterhead_boilerplate(combined_text)
        parsed.full_text = body_cleaned

        # 6. Language detection
        lang, is_en = detect_document_language(body_cleaned)
        parsed.lang = lang
        parsed.is_primary_english = is_en

        # 7. Quality score
        parsed.quality_score = compute_quality_score(body_cleaned)

        # Write parsed document atomically
        temp_out = output_json_path.with_suffix(".tmp")
        temp_out.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
        temp_out.replace(output_json_path)

        return parsed

    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}")
        quarantine_file = QUARANTINE_DIR / f"{doc_id}.json"
        quarantine_file.write_text(
            json.dumps({"doc_id": doc_id, "reason": str(e), "path": str(file_path)}),
            encoding="utf-8",
        )
        return None
