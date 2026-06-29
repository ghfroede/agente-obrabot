"""Add GIN indexes for JSONB columns."""

from collections.abc import Sequence

from alembic import op

revision: str = "006_add_jsonb_gin_indexes"
down_revision: str | None = "005_add_entradas_brutas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_tasks_input_gin", "tasks", "input"),
    ("ix_tasks_result_gin", "tasks", "result"),
    ("ix_obras_metadata_json_gin", "obras", "metadata_json"),
    ("ix_telegram_messages_raw_payload_gin", "telegram_messages", "raw_payload"),
    ("ix_arquivos_metadata_json_gin", "arquivos", "metadata_json"),
    ("ix_documentos_metadata_json_gin", "documentos", "metadata_json"),
    ("ix_triagens_campos_extraidos_gin", "triagens", "campos_extraidos"),
    ("ix_fotos_tags_gin", "fotos", "tags"),
    ("ix_fotos_metadata_json_gin", "fotos", "metadata_json"),
    ("ix_audios_transcricoes_metadata_json_gin", "audios_transcricoes", "metadata_json"),
    ("ix_auditoria_eventos_detalhes_gin", "auditoria_eventos", "detalhes"),
    ("ix_orcamento_itens_metadata_json_gin", "orcamento_itens", "metadata_json"),
    ("ix_cronograma_atividades_metadata_json_gin", "cronograma_atividades", "metadata_json"),
    ("ix_medicoes_metadata_json_gin", "medicoes", "metadata_json"),
    ("ix_entradas_brutas_raw_payload_gin", "entradas_brutas", "raw_payload"),
    ("ix_idempotency_keys_response_json_gin", "idempotency_keys", "response_json"),
)


def upgrade() -> None:
    for index_name, table_name, column_name in INDEXES:
        op.create_index(
            index_name,
            table_name,
            [column_name],
            unique=False,
            postgresql_using="gin",
        )


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(INDEXES):
        op.drop_index(index_name, table_name=table_name)
