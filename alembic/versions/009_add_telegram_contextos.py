from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "009_add_telegram_contextos"
down_revision: str | None = "008_link_entries_and_operational_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_contextos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=True),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("papel", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_telegram_contextos_chat_id",
        "telegram_contextos",
        ["chat_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_contextos_thread_id",
        "telegram_contextos",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_contextos_obra_id",
        "telegram_contextos",
        ["obra_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_contextos_status",
        "telegram_contextos",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_contextos_metadata_json_gin",
        "telegram_contextos",
        ["metadata_json"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "uq_telegram_contextos_chat_root_ativo",
        "telegram_contextos",
        ["chat_id"],
        unique=True,
        postgresql_where=sa.text("thread_id IS NULL AND status = 'ativo'"),
    )
    op.create_index(
        "uq_telegram_contextos_chat_thread_ativo",
        "telegram_contextos",
        ["chat_id", "thread_id"],
        unique=True,
        postgresql_where=sa.text("thread_id IS NOT NULL AND status = 'ativo'"),
    )


def downgrade() -> None:
    op.drop_index("uq_telegram_contextos_chat_thread_ativo", table_name="telegram_contextos")
    op.drop_index("uq_telegram_contextos_chat_root_ativo", table_name="telegram_contextos")
    op.drop_index("ix_telegram_contextos_metadata_json_gin", table_name="telegram_contextos")
    op.drop_index("ix_telegram_contextos_status", table_name="telegram_contextos")
    op.drop_index("ix_telegram_contextos_obra_id", table_name="telegram_contextos")
    op.drop_index("ix_telegram_contextos_thread_id", table_name="telegram_contextos")
    op.drop_index("ix_telegram_contextos_chat_id", table_name="telegram_contextos")
    op.drop_table("telegram_contextos")
