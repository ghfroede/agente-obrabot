from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.env import get_settings
from src.db.models import IdempotencyKey, Obra, Triagem
from src.schemas.domain import TriagemOutput
from src.utils.filenames import obra_slug


async def ensure_obra(
    session: AsyncSession,
    obra_id: str,
    nome: str | None = None,
) -> Obra:
    result = await session.execute(select(Obra).where(Obra.id == obra_id))
    obra = result.scalar_one_or_none()
    if obra is None:
        obra = Obra(
            id=obra_id,
            nome=nome or obra_id,
            slug=obra_slug(nome or obra_id),
            status="ativa",
        )
        session.add(obra)
        await session.flush()
    elif nome and obra.nome != nome:
        obra.nome = nome
        obra.slug = obra_slug(nome)
    return obra

async def save_triagem(
    session: AsyncSession,
    *,
    obra_id: str,
    output: TriagemOutput,
    telegram_message_id: uuid.UUID | None = None,
    documento_id: uuid.UUID | None = None,
) -> Triagem:
    row = Triagem(
        obra_id=obra_id,
        telegram_message_id=telegram_message_id,
        documento_id=documento_id,
        tipo_documento=output.tipo_documento,
        confianca=output.confianca,
        resumo=output.resumo,
        campos_extraidos=output.campos_extraidos,
        acao_sugerida=output.acao_sugerida,
        precisa_aprovacao=output.precisa_aprovacao,
        modelo=get_settings().openai_model if get_settings().openai_api_key else "heuristic",
    )
    session.add(row)
    await session.flush()
    return row

def idempotency_key(event_id: str, content_hash: str, obra_id: str) -> str:
    return f"{event_id}:{content_hash}:{obra_id}"


async def claim_idempotency(
    session: AsyncSession,
    *,
    event_id: str,
    content_hash: str,
    obra_id: str,
    source: str = "openclaw",
) -> IdempotencyKey | None:
    """Reivindica a chave atomicamente via INSERT ... ON CONFLICT DO NOTHING.

    Retorna ``None`` quando esta requisição venceu a corrida (deve processar);
    retorna a linha existente quando houve conflito (já em processamento/concluída).
    """
    key = idempotency_key(event_id, content_hash, obra_id)
    stmt = (
        pg_insert(IdempotencyKey)
        .values(
            key=key,
            event_id=event_id,
            obra_id=obra_id,
            source=source,
            status="processing",
            request_hash=content_hash,
        )
        .on_conflict_do_nothing(index_elements=["key"])
        .returning(IdempotencyKey.key)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is not None:
        return None
    existing = await session.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    return existing.scalar_one()


async def complete_idempotency(
    session: AsyncSession,
    *,
    event_id: str,
    content_hash: str,
    obra_id: str,
    result: dict[str, Any],
) -> None:
    """Marca a chave como concluída e guarda a resposta."""
    key = idempotency_key(event_id, content_hash, obra_id)
    await session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == key)
        .values(status="completed", response_json=result, updated_at=datetime.now(UTC))
    )


async def fail_idempotency(
    session: AsyncSession,
    *,
    event_id: str,
    content_hash: str,
    obra_id: str,
    error: str,
) -> None:
    """Marca a chave como falha para permitir reprocessamento futuro."""
    key = idempotency_key(event_id, content_hash, obra_id)
    await session.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == key)
        .values(status="failed", error=error[:500], updated_at=datetime.now(UTC))
    )
