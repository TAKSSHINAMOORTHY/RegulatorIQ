"""Unit tests for PDF, HTML, and Office document parsers."""

import docx
import fitz
import openpyxl

from ingest.manifest import ManifestRecord
from ingest.parse.html import parse_html
from ingest.parse.office import parse_docx, parse_xlsx
from ingest.parse.pdf import parse_pdf
from ingest.parse.router import detect_document_language, parse_and_clean_document


def test_parse_pdf_with_table(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 100), "Reserve Bank of India Master Direction on KYC")
    page.insert_text((50, 150), "1. Applicability to all Commercial Banks.")
    doc.save(str(pdf_path))
    doc.close()

    parsed = parse_pdf(pdf_path, doc_id="test_pdf_id")
    assert parsed.doc_id == "test_pdf_id"
    assert len(parsed.pages) == 1
    assert "Master Direction on KYC" in parsed.full_text


def test_parse_html(tmp_path):
    html_path = tmp_path / "test.html"
    html_path.write_text(
        "<html><body><h1>RBI Circular</h1><p>Digital Lending Guidelines 2025.</p>"
        "<table><tr><th>Param</th><th>Value</th></tr><tr><td>Cap</td><td>50%</td></tr></table>"
        "</body></html>",
        encoding="utf-8",
    )
    parsed = parse_html(html_path, doc_id="test_html_id")
    assert "Digital Lending Guidelines" in parsed.full_text
    assert len(parsed.tables) == 1


def test_parse_docx(tmp_path):
    docx_path = tmp_path / "test.docx"
    doc = docx.Document()
    doc.add_heading("Regulatory Reporting Norms", level=1)
    doc.add_paragraph("All banks must file statutory returns on CIMS portal.")
    tbl = doc.add_table(rows=2, cols=2)
    tbl.rows[0].cells[0].text = "Header A"
    tbl.rows[0].cells[1].text = "Header B"
    tbl.rows[1].cells[0].text = "Data 1"
    tbl.rows[1].cells[1].text = "Data 2"
    doc.save(str(docx_path))

    parsed = parse_docx(docx_path, doc_id="test_docx_id")
    assert "Regulatory Reporting Norms" in parsed.full_text
    assert len(parsed.tables) == 1


def test_parse_xlsx(tmp_path):
    xlsx_path = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Returns"
    ws.append(["Bank Name", "CRAR", "NPA"])
    ws.append(["State Bank", "14.5%", "2.1%"])
    wb.save(str(xlsx_path))

    parsed = parse_xlsx(xlsx_path, doc_id="test_xlsx_id")
    assert "Returns" in parsed.full_text
    assert len(parsed.tables) == 1


def test_detect_document_language():
    en_lang, is_en = detect_document_language(
        "The Reserve Bank of India regulates commercial banking and monetary policy."
    )
    assert is_en is True
    assert en_lang.startswith("en")


def test_parse_and_clean_document(tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.parse.router.PARSED_DIR", tmp_path / "parsed")
    (tmp_path / "parsed").mkdir(parents=True, exist_ok=True)

    dummy_file = tmp_path / "test_doc.html"
    dummy_file.write_text(
        "<html><body><p>Clean regulatory text for parsing router.</p></body></html>",
        encoding="utf-8",
    )

    rec = ManifestRecord(
        doc_id="router_test_id",
        doc_type="Circular",
        title="Test Circular",
        source_page_url="https://rbi.org.in/test",
        file_url="https://rbi.org.in/test.html",
        file_ext="html",
        local_path=str(dummy_file),
    )
    parsed = parse_and_clean_document(rec)
    assert parsed is not None
    assert parsed.doc_id == "router_test_id"
    assert (tmp_path / "parsed" / "router_test_id.json").exists()
