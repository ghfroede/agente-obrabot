
from src.agent.triagem import DOCUMENT_TYPES, _heuristic_classify


def test_heuristic_classify_rdo():
    result = _heuristic_classify("Gerar RDO de hoje", "OBRA-001")
    assert result["tipo_documento"] == "RDO"
    assert result["obra_id"] == "OBRA-001"
    assert result["confianca"] >= 0.4


def test_heuristic_classify_foto():
    result = _heuristic_classify("Segue foto da concretagem da laje", None)
    assert result["tipo_documento"] == "foto_obra"
    assert "obra_id" in result["pendencias"]


def test_document_types_include_rdo():
    assert "RDO" in DOCUMENT_TYPES
    assert "orcamento" in DOCUMENT_TYPES
