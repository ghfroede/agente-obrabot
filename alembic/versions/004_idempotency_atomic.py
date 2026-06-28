"""Harden idempotency_keys for atomic claim (status, response_json, request_hash)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_idempotency_atomic"
down_revision: Union[str, None] = "003_add_idempotency_keys_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "idempotency_keys",
        sa.Column("source", sa.String(length=64), nullable=False, server_default="openclaw"),
    )
    op.add_column(
        "idempotency_keys",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
    )
    op.add_column(
        "idempotency_keys",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "idempotency_keys",
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("idempotency_keys", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "idempotency_keys",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index("ix_idempotency_keys_status", "idempotency_keys", ["status"], unique=False)
    # Migra resultado legado (Text JSON) para JSONB e remove a coluna antiga.
    op.execute(
        "UPDATE idempotency_keys SET response_json = result::jsonb "
        "WHERE result IS NOT NULL AND response_json IS NULL"
    )
    op.drop_column("idempotency_keys", "result")
    # Remove defaults de servidor usados só para backfill das linhas existentes.
    op.alter_column("idempotency_keys", "source", server_default=None)
    op.alter_column("idempotency_keys", "status", server_default=None)


def downgrade() -> None:
    op.add_column(
        "idempotency_keys",
        sa.Column("result", sa.Text(), nullable=False, server_default="{}"),
    )
    op.execute(
        "UPDATE idempotency_keys SET result = response_json::text WHERE response_json IS NOT NULL"
    )
    op.alter_column("idempotency_keys", "result", server_default=None)
    op.drop_index("ix_idempotency_keys_status", table_name="idempotency_keys")
    op.drop_column("idempotency_keys", "updated_at")
    op.drop_column("idempotency_keys", "error")
    op.drop_column("idempotency_keys", "response_json")
    op.drop_column("idempotency_keys", "request_hash")
    op.drop_column("idempotency_keys", "status")
    op.drop_column("idempotency_keys", "source")
