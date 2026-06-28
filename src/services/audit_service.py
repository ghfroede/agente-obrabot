from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditoriaEvento


async def log_event(
    session: AsyncSession,
    *,
    entidade: str,
    entidade_id: str,
    acao: str,
    obra_id: str | None = None,
    actor: str | None = None,
    detalhes: dict[str, Any] | None = None,
) -> AuditoriaEvento:
    event = AuditoriaEvento(
        obra_id=obra_id,
        entidade=entidade,
        entidade_id=entidade_id,
        acao=acao,
        actor=actor,
        detalhes=detalhes,
    )
    session.add(event)
    await session.flush()
    return event
