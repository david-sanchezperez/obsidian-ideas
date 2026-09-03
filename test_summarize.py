"""Self-check mínimo: manejo de PDF sin texto extraíble."""
import io

from pypdf import PdfWriter

from summarize import extract_manual_tags, extract_urls, process_pdf


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


def test_extract_urls():
    msg = "mira esto https://a.com/x y también https://b.com/y https://a.com/x"
    assert extract_urls(msg) == ["https://a.com/x", "https://b.com/y"]
    assert extract_urls("sin enlaces aquí") == []


if __name__ == "__main__":
    test_process_pdf_empty_text()
    test_extract_manual_tags()
    test_extract_urls()
    print("OK")
