from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_allow_pending_obra_ingestion"
down_revision: str | None = "006_add_jsonb_gin_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "telegram_messages", "obra_id", existing_type=sa.String(length=32), nullable=True
    )
    op.alter_column(
        "entradas_brutas", "obra_id", existing_type=sa.String(length=32), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "entradas_brutas", "obra_id", existing_type=sa.String(length=32), nullable=False
    )
    op.alter_column(
        "telegram_messages", "obra_id", existing_type=sa.String(length=32), nullable=False
    )
