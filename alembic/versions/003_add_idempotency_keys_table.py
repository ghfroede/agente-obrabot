"""Add idempotency_keys table for request deduplication."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_add_idempotency_keys_table"
down_revision: Union[str, None] = "002_agentos_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_keys',
        sa.Column('key', sa.String(length=512), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False),
        sa.Column('obra_id', sa.String(length=255), nullable=False),
        sa.Column('result', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('key'),
        sa.Index('ix_idempotency_keys_event_id', 'event_id', unique=False),
        sa.Index('ix_idempotency_keys_obra_id', 'obra_id', unique=False),
    )


def downgrade() -> None:
    op.drop_table('idempotency_keys')
