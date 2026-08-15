"""Self-check mínimo: manejo de PDF sin texto extraíble."""
import io

from pypdf import PdfWriter

from summarize import process_pdf


def test_process_pdf_empty_text():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    result = process_pdf(buf.getvalue(), "vacio.pdf")
    assert result["title"] == "vacio.pdf"
    assert result["source_url"] is None
    assert result["summary"]


if __name__ == "__main__":
    test_process_pdf_empty_text()
    print("OK")
