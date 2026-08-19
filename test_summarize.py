"""Self-check mínimo: manejo de PDF sin texto extraíble."""
import io

from pypdf import PdfWriter

from summarize import extract_manual_tags, process_pdf


def test_process_pdf_empty_text():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    result = process_pdf(buf.getvalue(), "vacio.pdf")
    assert result["title"] == "vacio.pdf"
    assert result["source_url"] is None
    assert result["summary"]


def test_extract_manual_tags():
    assert extract_manual_tags("interesante artículo #learning #todo") == ["todo", "learning"]
    assert extract_manual_tags("sin tags aquí") == []
    assert extract_manual_tags("#no-existe #learning") == ["learning"]


if __name__ == "__main__":
    test_process_pdf_empty_text()
    test_extract_manual_tags()
    print("OK")
