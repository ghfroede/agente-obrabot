from __future__ import annotations

import json
import re
from typing import Any

import httpx

from src.config.env import get_settings

DOCUMENT_TYPES = [
    "RDO",
    "foto_obra",
    "audio_apontamento",
    "medicao",
    "orcamento",
    "cronograma",
    "folha_apontamento",
    "nota_fiscal",
    "pedido_compra",
    "contrato",
    "projeto",
    "relatorio_tecnico",
    "ocorrencia_seguranca",
    "nao_conformidade",
    "documento_administrativo",
    "duvida_operacional",
    "desconhecido",
]

TRIAGEM_SYSTEM_PROMPT = """Você é o Agente de Triagem da Construtora AgentOS.
Classifique a entrada do engenheiro e extraia metadados estruturados.
Responda SOMENTE com JSON válido no formato:
{
  "tipo_documento": "<um dos tipos permitidos>",
  "obra_id": "<OBRA-XXX ou null>",
  "data_referencia": "<YYYY-MM-DD ou null>",
  "autor": "<nome ou null>",
  "resumo": "<resumo curto>",
  "pendencias": ["<lista de campos faltantes>"],
  "confianca": <0.0 a 1.0>,
  "delegar_para": "<agente especialista sugerido>"
}
Tipos permitidos: """ + ", ".join(DOCUMENT_TYPES)


def _parse_json_response(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
    parsed: dict[str, Any] = json.loads(content)
    return parsed


def _heuristic_classify(message: str, obra_id: str | None) -> dict[str, Any]:
    lower = message.lower()
    tipo = "desconhecido"
    if any(k in lower for k in ("rdo", "diário", "diario", "relatório diário")):
        tipo = "RDO"
    elif any(k in lower for k in ("foto", "imagem", "concretagem", "alvenaria")):
        tipo = "foto_obra"
    elif any(k in lower for k in ("áudio", "audio", "voz")):
        tipo = "audio_apontamento"
    elif "orçamento" in lower or "orcamento" in lower:
        tipo = "orcamento"
    elif "cronograma" in lower:
        tipo = "cronograma"
    elif "medição" in lower or "medicao" in lower:
        tipo = "medicao"

    pendencias: list[str] = []
    if not obra_id:
        pendencias.append("obra_id")

    return {
        "tipo_documento": tipo,
        "obra_id": obra_id,
        "data_referencia": None,
        "autor": None,
        "resumo": message[:200],
        "pendencias": pendencias,
        "confianca": 0.4,
        "delegar_para": f"agente_{tipo.lower()}",
        "modo": "heuristic",
    }


async def classify_entry(
    message: str,
    *,
    obra_id: str | None = None,
    author: str | None = None,
    channel: str = "api",
) -> dict[str, Any]:
    settings = get_settings()
    user_payload = {
        "mensagem": message,
        "obra_id": obra_id,
        "autor": author,
        "canal": channel,
    }

    if not settings.openai_api_key:
        result = _heuristic_classify(message, obra_id)
        result["autor"] = author
        return result

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": TRIAGEM_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = _parse_json_response(content)
        parsed["modo"] = "llm"
        if author and not parsed.get("autor"):
            parsed["autor"] = author
        return parsed
