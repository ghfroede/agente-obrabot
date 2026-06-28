"""Expand schema for AgentOS document management."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_agentos_schema"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

document_status = sa.Enum(
    "RECEBIDO",
    "TRIADO",
    "PROCESSADO",
    "RASCUNHO_GERADO",
    "EM_REVISAO",
    "APROVADO",
    "REPROVADO",
    "CORRIGIDO",
    "FINALIZADO_VALIDADO",
    "PUBLICADO_BUCKET",
    "CANCELADO",
    "SUBSTITUIDO",
    "ERRO_PROCESSAMENTO",
    name="document_status",
    native_enum=False,
)


def upgrade() -> None:
    op.add_column("obras", sa.Column("slug", sa.String(length=120), nullable=True))
    op.add_column("obras", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        "obras",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.execute("UPDATE obras SET slug = id WHERE slug IS NULL")
    op.alter_column("obras", "slug", nullable=False)
    op.create_index("ix_obras_slug", "obras", ["slug"], unique=False)

    op.create_table(
        "telegram_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_telegram_messages_obra_id", "telegram_messages", ["obra_id"])
    op.create_index("ix_telegram_messages_chat_id", "telegram_messages", ["chat_id"])

    op.create_table(
        "arquivos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("telegram_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tipo", sa.String(length=64), nullable=False),
        sa.Column("nome_original", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("bucket_key", sa.String(length=1024), nullable=False),
        sa.Column("bucket_uri", sa.String(length=1200), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["telegram_message_id"], ["telegram_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_arquivos_obra_id", "arquivos", ["obra_id"])
    op.create_index("ix_arquivos_hash_sha256", "arquivos", ["hash_sha256"])

    op.create_table(
        "documentos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("tipo", sa.String(length=64), nullable=False),
        sa.Column("titulo", sa.String(length=512), nullable=False),
        sa.Column("data_ref", sa.Date(), nullable=True),
        sa.Column("revisao", sa.String(length=16), nullable=False),
        sa.Column("status", document_status, nullable=False),
        sa.Column("arquivo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bucket_key", sa.String(length=1024), nullable=True),
        sa.Column("bucket_uri", sa.String(length=1200), nullable=True),
        sa.Column("hash_sha256", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["arquivo_id"], ["arquivos.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documentos_obra_id", "documentos", ["obra_id"])
    op.create_index("ix_documentos_status", "documentos", ["status"])

    op.create_table(
        "triagens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("telegram_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("documento_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tipo_documento", sa.String(length=64), nullable=False),
        sa.Column("confianca", sa.Float(), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=False),
        sa.Column("campos_extraidos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acao_sugerida", sa.Text(), nullable=True),
        sa.Column("precisa_aprovacao", sa.Boolean(), nullable=False),
        sa.Column("modelo", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["telegram_message_id"], ["telegram_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "fotos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("arquivo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_foto", sa.Date(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["arquivo_id"], ["arquivos.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audios_transcricoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("arquivo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcricao", sa.Text(), nullable=False),
        sa.Column("modelo", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["arquivo_id"], ["arquivos.id"]),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "auditoria_eventos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=True),
        sa.Column("entidade", sa.String(length=64), nullable=False),
        sa.Column("entidade_id", sa.String(length=64), nullable=False),
        sa.Column("acao", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("detalhes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "aprovacoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("documento_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aprovador", sa.String(length=128), nullable=False),
        sa.Column("aprovado", sa.Boolean(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "orcamento_itens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("unidade", sa.String(length=32), nullable=True),
        sa.Column("quantidade", sa.Float(), nullable=True),
        sa.Column("valor_unitario", sa.Float(), nullable=True),
        sa.Column("valor_total", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("obra_id", "codigo", name="uq_orcamento_obra_codigo"),
    )

    op.create_table(
        "cronograma_atividades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("codigo", sa.String(length=64), nullable=False),
        sa.Column("nome", sa.String(length=512), nullable=False),
        sa.Column("inicio_previsto", sa.Date(), nullable=True),
        sa.Column("fim_previsto", sa.Date(), nullable=True),
        sa.Column("percentual_concluido", sa.Float(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "medicoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obra_id", sa.String(length=32), nullable=False),
        sa.Column("orcamento_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("periodo_ref", sa.String(length=32), nullable=False),
        sa.Column("quantidade_medida", sa.Float(), nullable=False),
        sa.Column("valor_medido", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"]),
        sa.ForeignKeyConstraint(["orcamento_item_id"], ["orcamento_itens.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("medicoes")
    op.drop_table("cronograma_atividades")
    op.drop_table("orcamento_itens")
    op.drop_table("aprovacoes")
    op.drop_table("auditoria_eventos")
    op.drop_table("audios_transcricoes")
    op.drop_table("fotos")
    op.drop_table("triagens")
    op.drop_index("ix_documentos_status", table_name="documentos")
    op.drop_index("ix_documentos_obra_id", table_name="documentos")
    op.drop_table("documentos")
    op.drop_index("ix_arquivos_hash_sha256", table_name="arquivos")
    op.drop_index("ix_arquivos_obra_id", table_name="arquivos")
    op.drop_table("arquivos")
    op.drop_index("ix_telegram_messages_chat_id", table_name="telegram_messages")
    op.drop_index("ix_telegram_messages_obra_id", table_name="telegram_messages")
    op.drop_table("telegram_messages")
    op.drop_index("ix_obras_slug", table_name="obras")
    op.drop_column("obras", "updated_at")
    op.drop_column("obras", "metadata_json")
    op.drop_column("obras", "slug")
