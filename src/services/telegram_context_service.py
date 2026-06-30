from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.db.models import Obra, TelegramContexto
from src.schemas.domain import OpenClawTelegramPayload
from src.schemas.telegram_contextos import TelegramContextoCreate

OBRA_PREFIX_RE = re.compile(r"^\s*(?P<obra_id>OBRA-[A-Z0-9][A-Z0-9_-]{0,26})\s*[:\-–—]?", re.I)


@dataclass(frozen=True)
class ObraResolution:
    obra: Obra | None
    requested_obra_id: str | None
    source: str


def parse_obra_prefix(text: str | None) -> str | None:
    if not text:
        return None
    match = OBRA_PREFIX_RE.match(text)
    if match is None:
        return None
    return match.group("obra_id").strip().upper()


async def list_contextos(session: AsyncSession) -> list[TelegramContexto]:
    result = await session.execute(
        select(TelegramContexto).order_by(
            TelegramContexto.chat_id.asc(),
            TelegramContexto.thread_id.asc().nullsfirst(),
            TelegramContexto.created_at.asc(),
        )
    )
    return list(result.scalars().all())


async def upsert_contexto(
    session: AsyncSession, payload: TelegramContextoCreate
) -> TelegramContexto:
    obra = await session.get(Obra, payload.obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {payload.obra_id} não encontrada")

    result = await session.execute(
        select(TelegramContexto).where(
            TelegramContexto.chat_id == payload.chat_id,
            TelegramContexto.thread_id.is_(None)
            if payload.thread_id is None
            else TelegramContexto.thread_id == payload.thread_id,
        )
    )
    contexto = result.scalar_one_or_none()
    if contexto is None:
        contexto = TelegramContexto(
            chat_id=payload.chat_id,
            thread_id=payload.thread_id,
            obra_id=payload.obra_id,
            papel=payload.papel,
            status=payload.status,
            metadata_json=payload.metadata_json,
        )
        session.add(contexto)
        await session.flush()
        return contexto

    contexto.obra_id = payload.obra_id
    contexto.papel = payload.papel
    contexto.status = payload.status
    contexto.metadata_json = payload.metadata_json
    await session.flush()
    return contexto


async def resolve_telegram_obra(
    session: AsyncSession, payload: OpenClawTelegramPayload, text: str
) -> ObraResolution:
    payload_obra_id = (payload.obra_id or "").strip().upper()
    if payload_obra_id:
        obra = await session.get(Obra, payload_obra_id)
        return ObraResolution(obra=obra, requested_obra_id=payload_obra_id, source="payload")

    prefix_obra_id = parse_obra_prefix(text)
    if prefix_obra_id:
        obra = await session.get(Obra, prefix_obra_id)
        return ObraResolution(obra=obra, requested_obra_id=prefix_obra_id, source="prefixo")

    contexto = await find_active_contexto(
        session,
        chat_id=payload.telegram.chat.id,
        thread_id=payload.telegram.message_thread_id,
    )
    if contexto is None:
        return ObraResolution(obra=None, requested_obra_id=None, source="missing")

    obra = await session.get(Obra, contexto.obra_id)
    return ObraResolution(
        obra=obra,
        requested_obra_id=contexto.obra_id,
        source="contexto_thread" if contexto.thread_id is not None else "contexto_chat",
    )


async def find_active_contexto(
    session: AsyncSession, *, chat_id: int, thread_id: int | None
) -> TelegramContexto | None:
    if thread_id is not None:
        result = await session.execute(
            select(TelegramContexto).where(
                TelegramContexto.chat_id == chat_id,
                TelegramContexto.thread_id == thread_id,
                TelegramContexto.status == "ativo",
            )
        )
        contexto = result.scalar_one_or_none()
        if contexto is not None:
            return contexto

    result = await session.execute(
        select(TelegramContexto).where(
            TelegramContexto.chat_id == chat_id,
            TelegramContexto.thread_id.is_(None),
            TelegramContexto.status == "ativo",
        )
    )
    return result.scalar_one_or_none()
