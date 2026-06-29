from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _normalize_obra_id(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("id da obra é obrigatório")
    return normalized


class ObraCreate(BaseModel):
    id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    nome: str = Field(min_length=1, max_length=255)
    status: str = Field(default="ativa", min_length=1, max_length=32)
    metadata_json: dict[str, Any] | None = None

    @field_validator("id", mode="before")
    @classmethod
    def normalize_id(cls, value: object) -> str:
        if value is None:
            raise ValueError("id da obra é obrigatório")
        return _normalize_obra_id(str(value))

    @field_validator("nome", "status", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value).strip()


class ObraResponse(BaseModel):
    id: str
    nome: str
    slug: str
    status: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
