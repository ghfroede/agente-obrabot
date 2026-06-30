from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None


class TelegramChat(BaseModel):
    id: int
    type: str = "private"


class TelegramEvent(BaseModel):
  message_id: int
  chat: TelegramChat
  from_user: TelegramUser | None = Field(default=None, alias="from")
  text: str | None = None
  caption: str | None = None
  date: int | None = None
  message_thread_id: int | None = None
  photo: list[dict[str, Any]] | None = None
  document: dict[str, Any] | None = None
  voice: dict[str, Any] | None = None
  audio: dict[str, Any] | None = None

  model_config = {"populate_by_name": True}


class OpenClawTelegramPayload(BaseModel):
    event_id: str
    obra_id: str | None = Field(default=None, max_length=32)
    obra_nome: str | None = None
    telegram: TelegramEvent
    raw: dict[str, Any] = Field(default_factory=dict)


class TriagemOutput(BaseModel):
    tipo_documento: Literal[
        "rdo",
        "foto_obra",
        "audio_transcricao",
        "orcamento",
        "cronograma",
        "medicao",
        "folha_pagamento",
        "documento_generico",
        "desconhecido",
    ]
    confianca: float = Field(ge=0, le=1)
    resumo: str
    campos_extraidos: dict[str, Any] = Field(default_factory=dict)
    acao_sugerida: str
    precisa_aprovacao: bool = True


class ApprovalRequest(BaseModel):
    documento_id: str
    aprovado: bool
    comentario: str | None = None
    aprovador: str = "engenheiro"


class RdoDraftRequest(BaseModel):
    obra_id: str
    data_ref: str
    conteudo: dict[str, Any] = Field(default_factory=dict)


class RdoGenerateRequest(BaseModel):
    obra_id: str
    data_ref: str


class ResolveEntradaObraRequest(BaseModel):
    obra_id: str = Field(min_length=1, max_length=32)


class RdoApproveRequest(BaseModel):
    documento_id: str
    aprovador: str = "engenheiro"
    comentario: str | None = None


class FotoRelatorioRequest(BaseModel):
    obra_id: str
    periodo_inicio: str
    periodo_fim: str


class OrcamentoImportRequest(BaseModel):
    obra_id: str
    arquivo_id: str | None = None
    itens: list[dict[str, Any]] = Field(default_factory=list)


class CronogramaImportRequest(BaseModel):
    obra_id: str
    arquivo_id: str | None = None
    atividades: list[dict[str, Any]] = Field(default_factory=list)
