from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.config.env import get_settings

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTEGRATION_URL = "postgresql+asyncpg://obrabot:obrabot@127.0.0.1:5432/obrabot"

TRUNCATE_TABLES = (
    "idempotency_keys",
    "auditoria_eventos",
    "aprovacoes",
    "triagens",
    "fotos",
    "audios_transcricoes",
    "arquivos",
    "documentos",
    "entradas_brutas",
    "telegram_messages",
    "medicoes",
    "medicao_periodos",
    "cronograma_atividades",
    "orcamento_itens",
    "telegram_contextos",
    "obras",
    "tasks",
)


def integration_database_url() -> str:
    return os.getenv("INTEGRATION_DATABASE_URL", DEFAULT_INTEGRATION_URL)


def _sync_database_url(async_url: str) -> str:
    url = async_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _postgres_available(sync_url: str) -> bool:
    try:
        with psycopg2.connect(sync_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


def _run_alembic_upgrade(sync_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = sync_url
    get_settings.cache_clear()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head falhou:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


@pytest.fixture(scope="session")
def integration_db_url() -> str:
    url = integration_database_url()
    if not _postgres_available(_sync_database_url(url)):
        pytest.skip("Postgres indisponível para testes de integração")
    return url


@pytest.fixture(scope="session")
def migrated_schema(integration_db_url: str) -> str:
    _run_alembic_upgrade(_sync_database_url(integration_db_url))
    return integration_db_url


@pytest_asyncio.fixture
async def integration_engine(migrated_schema: str):
    engine = create_async_engine(
        migrated_schema,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(integration_engine) -> AsyncIterator[AsyncSession]:
    async with integration_engine.begin() as conn:
        tables = ", ".join(TRUNCATE_TABLES)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    session_factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
