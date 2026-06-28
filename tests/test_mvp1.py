import pytest

from src.core.constants import DocumentStatus
from src.services.openai_service import _heuristic_triagem
from src.utils.filenames import build_document_filename, next_revision


@pytest.mark.asyncio
async def test_heuristic_rdo():
    out = _heuristic_triagem("Preciso registrar o RDO de hoje com alvenaria")
    assert out.tipo_documento == "rdo"


@pytest.mark.asyncio
async def test_heuristic_foto():
    out = _heuristic_triagem("Foto da concretagem do bloco B")
    assert out.tipo_documento == "foto_obra"


def test_next_revision():
    assert next_revision(["REV00", "REV01"]) == "REV02"
    assert next_revision([]) == "REV00"


def test_build_document_filename():
    name = build_document_filename(
        tipo="RDO",
        obra_id="OBRA-001",
        data_ref="2026-06-27",
        revisao="REV00",
        status=DocumentStatus.RASCUNHO_GERADO,
    )
    assert "RDO_OBRA-001" in name
    assert "DRAFT" in name
