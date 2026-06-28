import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import openai_service
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


async def test_triagem_structured_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regressão: o ramo LLM deve usar JSON mode (não Structured Outputs estrito, que
    # recusa campos_extraidos: dict[str, Any]) e validar o JSON manualmente.
    payload = {
        "tipo_documento": "rdo",
        "confianca": 0.9,
        "resumo": "rdo do dia",
        "campos_extraidos": {"servico": "alvenaria"},
        "acao_sugerida": "delegar_para_rdo",
        "precisa_aprovacao": True,
    }
    msg = SimpleNamespace(content=json.dumps(payload))
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    create = AsyncMock(return_value=resp)
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(openai_service, "_client", lambda: fake_client)

    out = await openai_service.triagem_structured("texto", context={"obra_id": "OBRA-1"})

    assert out.tipo_documento == "rdo"
    assert out.campos_extraidos == {"servico": "alvenaria"}
    assert create.await_args.kwargs["response_format"] == {"type": "json_object"}
