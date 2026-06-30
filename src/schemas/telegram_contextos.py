from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _normalize_obra_id(value: object) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise ValueError("obra_id é obrigatório")
    return normalized


class TelegramContextoCreate(BaseModel):
    chat_id: int
    thread_id: int | None = None
    obra_id: str = Field(min_length=1, max_length=32)
    papel: str = Field(default="engenheiro", min_length=1, max_length=64)
    status: str = Field(default="ativo", min_length=1, max_length=32)
    metadata_json: dict[str, Any] | None = None

    @field_validator("obra_id", mode="before")
    @classmethod
    def normalize_obra_id(cls, value: object) -> str:
        return _normalize_obra_id(value)

    @field_validator("papel", "status", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value).strip()


class TelegramContextoResponse(BaseModel):
    id: str
    chat_id: int
    thread_id: int | None = None
    obra_id: str
    papel: str
    status: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
