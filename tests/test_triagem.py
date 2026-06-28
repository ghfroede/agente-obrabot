from src.services.openai_service import _heuristic_triagem


def test_heuristic_classify_rdo():
    result = _heuristic_triagem("Gerar RDO de hoje")
    assert result.tipo_documento == "rdo"
    assert result.confianca >= 0.4


def test_heuristic_classify_foto():
    result = _heuristic_triagem("Segue foto da concretagem da laje")
    assert result.tipo_documento == "foto_obra"


def test_heuristic_orcamento():
    result = _heuristic_triagem("Atualizar orçamento da fundação")
    assert result.tipo_documento == "orcamento"
