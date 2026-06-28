"""Add entradas_brutas table (unified ingestion across channels)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_add_entradas_brutas"
down_revision: Union[str, None] = "004_idempotency_atomic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entradas_brutas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=512), nullable=True),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("storage_uri", sa.String(length=1200), nullable=True),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entradas_brutas_source", "entradas_brutas", ["source"], unique=False)
    op.create_index("ix_entradas_brutas_event_id", "entradas_brutas", ["event_id"], unique=False)
    op.create_index("ix_entradas_brutas_obra_id", "entradas_brutas", ["obra_id"], unique=False)
    op.create_index("ix_entradas_brutas_status", "entradas_brutas", ["status"], unique=False)
    op.create_index(
        "ix_entradas_brutas_hash_sha256", "entradas_brutas", ["hash_sha256"], unique=False
    )
    op.create_index("ix_entradas_brutas_task_id", "entradas_brutas", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_entradas_brutas_task_id", table_name="entradas_brutas")
    op.drop_index("ix_entradas_brutas_hash_sha256", table_name="entradas_brutas")
    op.drop_index("ix_entradas_brutas_status", table_name="entradas_brutas")
    op.drop_index("ix_entradas_brutas_obra_id", table_name="entradas_brutas")
    op.drop_index("ix_entradas_brutas_event_id", table_name="entradas_brutas")
    op.drop_index("ix_entradas_brutas_source", table_name="entradas_brutas")
    op.drop_table("entradas_brutas")
