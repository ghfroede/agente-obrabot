from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008_link_entries_and_operational_metadata"
down_revision: str | None = "007_allow_pending_obra_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entradas_brutas",
        sa.Column("data_ref", sa.Date(), nullable=True),
    )
    op.add_column(
        "entradas_brutas",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_entradas_brutas_data_ref",
        "entradas_brutas",
        ["data_ref"],
        unique=False,
    )
    op.create_index(
        "ix_entradas_brutas_metadata_json_gin",
        "entradas_brutas",
        ["metadata_json"],
        unique=False,
        postgresql_using="gin",
    )

    op.add_column(
        "arquivos",
        sa.Column("entrada_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_arquivos_entrada_id_entradas_brutas",
        "arquivos",
        "entradas_brutas",
        ["entrada_id"],
        ["id"],
    )
    op.create_index("ix_arquivos_entrada_id", "arquivos", ["entrada_id"], unique=False)

    op.add_column(
        "documentos",
        sa.Column("entrada_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documentos_entrada_id_entradas_brutas",
        "documentos",
        "entradas_brutas",
        ["entrada_id"],
        ["id"],
    )
    op.create_index("ix_documentos_entrada_id", "documentos", ["entrada_id"], unique=False)

    op.add_column(
        "triagens",
        sa.Column("entrada_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_triagens_entrada_id_entradas_brutas",
        "triagens",
        "entradas_brutas",
        ["entrada_id"],
        ["id"],
    )
    op.create_index("ix_triagens_entrada_id", "triagens", ["entrada_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_triagens_entrada_id", table_name="triagens")
    op.drop_constraint(
        "fk_triagens_entrada_id_entradas_brutas", "triagens", type_="foreignkey"
    )
    op.drop_column("triagens", "entrada_id")

    op.drop_index("ix_documentos_entrada_id", table_name="documentos")
    op.drop_constraint(
        "fk_documentos_entrada_id_entradas_brutas", "documentos", type_="foreignkey"
    )
    op.drop_column("documentos", "entrada_id")

    op.drop_index("ix_arquivos_entrada_id", table_name="arquivos")
    op.drop_constraint(
        "fk_arquivos_entrada_id_entradas_brutas", "arquivos", type_="foreignkey"
    )
    op.drop_column("arquivos", "entrada_id")

    op.drop_index("ix_entradas_brutas_metadata_json_gin", table_name="entradas_brutas")
    op.drop_index("ix_entradas_brutas_data_ref", table_name="entradas_brutas")
    op.drop_column("entradas_brutas", "metadata_json")
    op.drop_column("entradas_brutas", "data_ref")
