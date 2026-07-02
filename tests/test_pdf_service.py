from __future__ import annotations

from src.services.pdf_service import html_to_pdf


def test_html_to_pdf_produces_pdf_bytes() -> None:
    pdf = html_to_pdf("<html><body><p>RDO teste</p></body></html>")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100
