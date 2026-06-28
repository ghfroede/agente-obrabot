from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def html_to_pdf(html: str) -> bytes:
    """Converte HTML em PDF. Usa xhtml2pdf (pure Python, compatível com Railway)."""
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:
        raise RuntimeError("xhtml2pdf não instalado") from exc

    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
    if status.err:
        logger.error("Falha na geração PDF: %s erros", status.err)
        raise RuntimeError("Falha ao gerar PDF a partir do HTML")
    return buffer.getvalue()
