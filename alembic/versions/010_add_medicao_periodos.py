from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "010_medicao_periodos"
down_revision: str | None = "009_telegram_contextos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "medicao_periodos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("periodo_ref", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="aberto",
            nullable=False,
        ),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('aberto', 'em_revisao', 'aprovado', 'fechado')",
            name="ck_medicao_periodos_status",
        ),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("obra_id", "periodo_ref", name="uq_medicao_periodos_obra_periodo"),
    )
    op.create_index(
        "ix_medicao_periodos_obra_id",
        "medicao_periodos",
        ["obra_id"],
        unique=False,
    )
    op.create_index(
        "ix_medicao_periodos_periodo_ref",
        "medicao_periodos",
        ["periodo_ref"],
        unique=False,
    )
    op.create_index(
        "ix_medicao_periodos_status",
        "medicao_periodos",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_medicao_periodos_metadata_json_gin",
        "medicao_periodos",
        ["metadata_json"],
        unique=False,
        postgresql_using="gin",
    )

    op.add_column(
        "medicoes",
        sa.Column("periodo_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_medicoes_periodo_id_medicao_periodos",
        "medicoes",
        "medicao_periodos",
        ["periodo_id"],
        ["id"],
    )
    op.create_index("ix_medicoes_periodo_id", "medicoes", ["periodo_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_medicoes_periodo_id", table_name="medicoes")
    op.drop_constraint(
        "fk_medicoes_periodo_id_medicao_periodos",
        "medicoes",
        type_="foreignkey",
    )
    op.drop_column("medicoes", "periodo_id")

    op.drop_index("ix_medicao_periodos_metadata_json_gin", table_name="medicao_periodos")
    op.drop_index("ix_medicao_periodos_status", table_name="medicao_periodos")
    op.drop_index("ix_medicao_periodos_periodo_ref", table_name="medicao_periodos")
    op.drop_index("ix_medicao_periodos_obra_id", table_name="medicao_periodos")
    op.drop_table("medicao_periodos")
