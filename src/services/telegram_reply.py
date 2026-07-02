from __future__ import annotations

import logging
from typing import Any

from src.core.constants import PENDING_OBRA_STATUS
from src.db.models import EntradaBruta
from src.services import telegram_media_service

logger = logging.getLogger(__name__)


def pending_obra_message(
    obras: list[dict[str, str]], *, requested_obra_id: str | None = None
) -> str:
    prefix = (
        f"A obra {requested_obra_id} não está cadastrada. "
        if requested_obra_id
        else "Recebi a mensagem, mas preciso confirmar a obra antes de processar. "
    )
    if not obras:
        return (
            f"{prefix}Nenhuma obra ativa está cadastrada. "
            "Cadastre uma obra antes de gerar documento oficial."
        )
    if len(obras) == 1:
        obra = obras[0]
        return (
            f"{prefix}"
            f"Use {obra['id']} ({obra['nome']}) ou responda com o ID da obra."
        )
    ids = ", ".join(f"{obra['id']} ({obra['nome']})" for obra in obras[:5])
    return (
        f"{prefix}"
        f"Obras ativas: {ids}. Responda com o ID da obra."
    )


def build_telegram_reply(entrada: EntradaBruta, result: dict[str, Any]) -> tuple[int, str] | None:
    """Monta (chat_id, texto) de status para o engenheiro a partir do payload Telegram."""
    raw = entrada.raw_payload or {}
    telegram = raw.get("telegram")
    if not isinstance(telegram, dict):
        return None
    chat = telegram.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None

    if result.get("status") == PENDING_OBRA_STATUS:
        return int(chat["id"]), str(result.get("mensagem") or "Confirme a obra para processar.")

    tipo = result.get("tipo_documento", "desconhecido")
    proximo = "aguardando aprovação" if result.get("precisa_aprovacao", True) else "registrado"
    documento_id = str(result.get("documento_id", ""))
    short_id = documento_id[:8] if documento_id else "?"
    obra_id = str(result.get("obra_id") or "")
    texto = f"✅ Recebido. Tipo: {tipo}. Status: {proximo}. Documento {short_id}."
    if obra_id:
        texto += f"\nPara consolidar o RDO do dia: /gerar_rdo {obra_id} hoje"
        texto += f"\nPara relatório fotográfico: /gerar_relatorio_foto {obra_id} hoje hoje"
    if tipo == "rdo" and documento_id:
        texto += f"\nApós revisar o rascunho: /aprovar_rdo {documento_id}"
    if tipo == "relatorio_fotografico" and documento_id:
        texto += f"\nApós revisar o relatório: /aprovar_relatorio_foto {documento_id}"
    if tipo in ("orcamento", "cronograma") and obra_id:
        texto += f"\nPara validar baseline: /validar_baseline {obra_id}"
    return int(chat["id"]), texto


async def send_telegram_reply(chat_id: int, texto: str) -> None:
    """Envia resposta de status (best-effort) — falha de rede não derruba o pipeline."""
    try:
        await telegram_media_service.send_message(chat_id, texto)
    except Exception:
        logger.warning(
            "telegram reply failed",
            extra={"chat_id": chat_id},
            exc_info=True,
        )
