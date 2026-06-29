from __future__ import annotations

from typing import Any

from src.agent.triagem import classify_entry
from src.config.env import get_settings
from src.storage.s3 import persist_raw_entry


async def run_ceo_pipeline(task_input: dict[str, Any]) -> dict[str, Any]:
    """Orquestra persistência bruta (PRIMEIRO!) e depois triagem e delegação."""
    settings = get_settings()
    message = str(task_input.get("message", "")).strip()
    if not message:
        raise ValueError("Campo 'message' é obrigatório")

    obra_id = task_input.get("obra_id")
    if not obra_id:
        raise ValueError("Campo 'obra_id' é obrigatório para triagem oficial")
    author = task_input.get("author")
    channel = task_input.get("channel", "api")

    # ===== 1. Persistir raw no S3 PRIMEIRO (Fonte de verdade para auditoria) =====
    storage_uri: str | None = None
    if settings.s3_configured:
        storage_uri = persist_raw_entry(
            obra_id=str(obra_id),
            message=message,
            metadata={
                "author": author,
                "channel": channel,
                "triagem_pendente": True,
            },
        )
    # Se S3 não estiver configurado, ainda assim continua (fallback para banco)
    # mas em produção, S3 deve estar configurado

    # ===== 2. Classificar DEPOIS (agora o raw já está persistido) =====
    triagem = await classify_entry(
        message,
        obra_id=obra_id,
        author=author,
        channel=channel,
    )

    specialist = triagem.get("delegar_para", "agente_triagem")
    needs_clarification = bool(triagem.get("pendencias"))

    return {
        "agent": settings.agent_name,
        "acao": "triagem_concluida",
        "triagem": triagem,
        "storage_uri": storage_uri,
        "delegacao": {
            "especialista": specialist,
            "precisa_esclarecimento": needs_clarification,
            "pendencias": triagem.get("pendencias", []),
        },
        "proximo_passo": (
            "solicitar_dados_faltantes"
            if needs_clarification
            else "encaminhar_especialista"
        ),
    }
