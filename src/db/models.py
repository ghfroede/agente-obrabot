from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.constants import DocumentStatus


class TaskStatus(enum.StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=False),
        default=TaskStatus.QUEUED,
        index=True,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Obra(Base):
    __tablename__ = "obras"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ativa")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Arquivo(Base):
    __tablename__ = "arquivos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    telegram_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("telegram_messages.id"), nullable=True
    )
    tipo: Mapped[str] = mapped_column(String(64), index=True)
    nome_original: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tamanho_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hash_sha256: Mapped[str] = mapped_column(String(64), index=True)
    bucket_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    bucket_uri: Mapped[str] = mapped_column(String(1200), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(64), index=True)
    titulo: Mapped[str] = mapped_column(String(512))
    data_ref: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    revisao: Mapped[str] = mapped_column(String(16), default="REV00")
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=False),
        default=DocumentStatus.RECEBIDO,
        index=True,
    )
    arquivo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("arquivos.id"), nullable=True
    )
    bucket_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    bucket_uri: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Triagem(Base):
    __tablename__ = "triagens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    telegram_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("telegram_messages.id"), nullable=True
    )
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id"), nullable=True
    )
    tipo_documento: Mapped[str] = mapped_column(String(64), index=True)
    confianca: Mapped[float] = mapped_column(Float, default=0.0)
    resumo: Mapped[str] = mapped_column(Text)
    campos_extraidos: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    acao_sugerida: Mapped[str | None] = mapped_column(Text, nullable=True)
    precisa_aprovacao: Mapped[bool] = mapped_column(Boolean, default=True)
    modelo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Foto(Base):
    __tablename__ = "fotos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    arquivo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("arquivos.id"))
    data_foto: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AudioTranscricao(Base):
    __tablename__ = "audios_transcricoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    arquivo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("arquivos.id"))
    transcricao: Mapped[str] = mapped_column(Text)
    modelo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditoriaEvento(Base):
    __tablename__ = "auditoria_eventos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("obras.id"), nullable=True, index=True
    )
    entidade: Mapped[str] = mapped_column(String(64), index=True)
    entidade_id: Mapped[str] = mapped_column(String(64), index=True)
    acao: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detalhes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Aprovacao(Base):
    __tablename__ = "aprovacoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    documento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documentos.id"), index=True
    )
    aprovador: Mapped[str] = mapped_column(String(128))
    aprovado: Mapped[bool] = mapped_column(Boolean)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrcamentoItem(Base):
    __tablename__ = "orcamento_itens"
    __table_args__ = (UniqueConstraint("obra_id", "codigo", name="uq_orcamento_obra_codigo"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(64))
    descricao: Mapped[str] = mapped_column(Text)
    unidade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantidade: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CronogramaAtividade(Base):
    __tablename__ = "cronograma_atividades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(64), index=True)
    nome: Mapped[str] = mapped_column(String(512))
    inicio_previsto: Mapped[date | None] = mapped_column(Date, nullable=True)
    fim_previsto: Mapped[date | None] = mapped_column(Date, nullable=True)
    percentual_concluido: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Medicao(Base):
    __tablename__ = "medicoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[str] = mapped_column(String(32), ForeignKey("obras.id"), index=True)
    orcamento_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orcamento_itens.id"), nullable=True
    )
    periodo_ref: Mapped[str] = mapped_column(String(32), index=True)
    quantidade_medida: Mapped[float] = mapped_column(Float, default=0.0)
    valor_medido: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyKey(Base):
    """Tabela para garantir idempotência atômica de requisições (webhook, Telegram, etc.).

    Fluxo: INSERT com status ``processing`` via ON CONFLICT DO NOTHING; quem vence a
    corrida processa e atualiza para ``completed``/``failed``; quem perde lê o resultado.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(512), primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    obra_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="openclaw")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="processing", index=True
    )
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
