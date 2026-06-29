from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.routes.tasks import CreateTaskRequest, TaskInput, create_task


async def test_create_task_requires_obra_id() -> None:
    session = AsyncMock()
    body = CreateTaskRequest(input=TaskInput(message="registrar RDO"))

    with pytest.raises(HTTPException) as exc:
        await create_task(body, session)

    assert exc.value.status_code == 400
    assert "obra_id" in exc.value.detail


async def test_create_task_rejects_unknown_obra() -> None:
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    body = CreateTaskRequest(input=TaskInput(message="registrar RDO", obra_id="OBRA-404"))

    with pytest.raises(HTTPException) as exc:
        await create_task(body, session)

    assert exc.value.status_code == 404
    assert "não cadastrada" in exc.value.detail
