from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.schemas.domain import OpenClawTelegramPayload, TelegramChat, TelegramEvent
from src.services import telegram_context_service


def test_parse_obra_prefix() -> None:
    assert telegram_context_service.parse_obra_prefix("OBRA-001: concretagem") == "OBRA-001"
    assert telegram_context_service.parse_obra_prefix(" obra-abc - inspeção") == "OBRA-ABC"
    assert telegram_context_service.parse_obra_prefix("sem obra") is None


async def test_resolve_telegram_obra_uses_thread_context() -> None:
    contexto = SimpleNamespace(obra_id="OBRA-002", thread_id=99)
    obra = SimpleNamespace(id="OBRA-002")
    result = MagicMock()
    result.scalar_one_or_none.return_value = contexto
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=obra)
    payload = OpenClawTelegramPayload(
        event_id="evt-1",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=10, type="supergroup"),
            message_thread_id=99,
            text="Concretagem concluída",
        ),
    )

    resolution = await telegram_context_service.resolve_telegram_obra(
        session, payload, "Concretagem concluída"
    )

    assert resolution.obra == obra
    assert resolution.requested_obra_id == "OBRA-002"
    assert resolution.source == "contexto_thread"


async def test_resolve_telegram_obra_missing_context() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    payload = OpenClawTelegramPayload(
        event_id="evt-1",
        telegram=TelegramEvent(
            message_id=1,
            chat=TelegramChat(id=10, type="group"),
            text="Concretagem concluída",
        ),
    )

    resolution = await telegram_context_service.resolve_telegram_obra(
        session, payload, "Concretagem concluída"
    )

    assert resolution.obra is None
    assert resolution.requested_obra_id is None
    assert resolution.source == "missing"
