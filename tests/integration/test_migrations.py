from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_alembic_head_is_applied(db_session) -> None:
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))
    version = result.scalar_one()
    assert version == "010_medicao_periodos"
