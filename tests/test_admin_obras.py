from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.errors import NotFoundError
from src.services import obra_service


async def test_set_status_updates_obra(monkeypatch: pytest.MonkeyPatch) -> None:
    obra = SimpleNamespace(id="OBRA-001", status="ativa")
    session = AsyncMock()
    session.get = AsyncMock(return_value=obra)

    result = await obra_service.set_status(session, "OBRA-001", "inativa")

    assert result.status == "inativa"
    session.flush.assert_awaited_once()


async def test_set_status_raises_when_missing() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError):
        await obra_service.set_status(session, "INEXISTENTE", "inativa")
