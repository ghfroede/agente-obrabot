from __future__ import annotations

from typing import Any

from src.config.env import get_settings
from src.services.openai_service import triagem_structured as classify_entry_structured


async def classify_entry(
    message: str,
    *,
    obra_id: str | None = None,
    author: str | None = None,
    channel: str = "api",
) -> dict[str, Any]:
    output = await classify_entry_structured(
        message,
        context={"obra_id": obra_id, "autor": author, "canal": channel},
    )
    result = output.model_dump()
    result["obra_id"] = obra_id
    result["autor"] = author
    result["delegar_para"] = output.acao_sugerida
    result["modo"] = "llm" if get_settings().openai_api_key else "heuristic"
    return result
