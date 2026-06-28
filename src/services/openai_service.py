from __future__ import annotations

import base64
import json
import re
from typing import Any, cast

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.env import get_settings
from src.schemas.domain import TriagemOutput

TRIAGEM_SYSTEM = """Você é o Agente de Triagem da Construtora AgentOS.
Classifique a entrada do engenheiro de obra.
Responda com JSON estruturado conforme o schema TriagemOutput."""


def _client() -> AsyncOpenAI | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.llm_base_url or None)


def _heuristic_triagem(text: str) -> TriagemOutput:
    lower = text.lower()
    tipo = "desconhecido"
    if any(k in lower for k in ("rdo", "diário", "diario", "relatório diário")):
        tipo = "rdo"
    elif any(k in lower for k in ("foto", "imagem", "concretagem")):
        tipo = "foto_obra"
    elif any(k in lower for k in ("áudio", "audio", "voz")):
        tipo = "audio_transcricao"
    elif "orçamento" in lower or "orcamento" in lower:
        tipo = "orcamento"
    elif "cronograma" in lower:
        tipo = "cronograma"
    elif "medição" in lower or "medicao" in lower:
        tipo = "medicao"
    elif "folha" in lower and "pagamento" in lower:
        tipo = "folha_pagamento"

    return TriagemOutput(
        tipo_documento=cast(Any, tipo),
        confianca=0.45,
        resumo=text[:240],
        campos_extraidos={},
        acao_sugerida=f"delegar_para_{tipo}",
        precisa_aprovacao=True,
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def triagem_structured(text: str, *, context: dict[str, Any] | None = None) -> TriagemOutput:
    client = _client()
    if client is None:
        return _heuristic_triagem(text)

    settings = get_settings()
    user_content = json.dumps({"texto": text, "contexto": context or {}}, ensure_ascii=False)
    response = await client.beta.chat.completions.parse(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": TRIAGEM_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_format=TriagemOutput,
        temperature=0.1,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raw = response.choices[0].message.content or "{}"
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw.strip())
            raw = re.sub(r"\n?```$", "", raw)
        return TriagemOutput.model_validate_json(raw)
    return parsed


async def transcribe_audio(file_bytes: bytes, filename: str = "audio.ogg") -> str:
    client = _client()
    if client is None:
        return "[transcrição indisponível — configure OPENAI_API_KEY]"

    settings = get_settings()
    response = await client.audio.transcriptions.create(
        model=settings.openai_transcription_model,
        file=(filename, file_bytes),
    )
    return response.text


async def describe_image(file_bytes: bytes, *, prompt: str | None = None) -> str:
    client = _client()
    if client is None:
        return "Imagem recebida (visão indisponível sem API key)."

    settings = get_settings()
    b64 = base64.b64encode(file_bytes).decode("ascii")
    mime = "image/jpeg"
    response = await client.chat.completions.create(
        model=settings.openai_vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt or "Descreva esta foto de obra para relatório fotográfico.",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        max_tokens=500,
    )
    return response.choices[0].message.content or ""


async def embed_text(text: str) -> list[float]:
    client = _client()
    if client is None:
        return []

    settings = get_settings()
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=text,
    )
    return list(response.data[0].embedding)
