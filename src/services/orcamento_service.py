from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CronogramaAtividade, OrcamentoItem
from src.services import audit_service
from src.utils.dates import parse_date


async def import_orcamento(
    session: AsyncSession,
    *,
    obra_id: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    count = 0
    for item in itens:
        codigo = str(item.get("codigo", f"ITEM-{count + 1}"))
        existing = await session.execute(
            select(OrcamentoItem).where(
                OrcamentoItem.obra_id == obra_id,
                OrcamentoItem.codigo == codigo,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = OrcamentoItem(
                obra_id=obra_id,
                codigo=codigo,
                descricao=str(item.get("descricao", codigo)),
            )
            session.add(row)
        row.descricao = str(item.get("descricao", row.descricao))
        row.unidade = item.get("unidade")
        row.quantidade = item.get("quantidade")
        row.valor_unitario = item.get("valor_unitario")
        qty = row.quantidade or 0
        unit = row.valor_unitario or 0
        row.valor_total = item.get("valor_total") or (qty * unit)
        row.metadata_json = item
        count += 1

    await audit_service.log_event(
        session,
        entidade="orcamento",
        entidade_id=obra_id,
        acao="importado",
        obra_id=obra_id,
        detalhes={"itens": count},
    )
    await session.commit()
    return {"obra_id": obra_id, "itens_processados": count}


async def import_cronograma(
    session: AsyncSession,
    *,
    obra_id: str,
    atividades: list[dict[str, Any]],
) -> dict[str, Any]:
    count = 0
    for atv in atividades:
        codigo = str(atv.get("codigo", f"ATV-{count + 1}"))
        row = CronogramaAtividade(
            obra_id=obra_id,
            codigo=codigo,
            nome=str(atv.get("nome", codigo)),
            inicio_previsto=parse_date(atv.get("inicio_previsto")),
            fim_previsto=parse_date(atv.get("fim_previsto")),
            percentual_concluido=float(atv.get("percentual_concluido", 0)),
            metadata_json=atv,
        )
        session.add(row)
        count += 1

    await audit_service.log_event(
        session,
        entidade="cronograma",
        entidade_id=obra_id,
        acao="importado",
        obra_id=obra_id,
        detalhes={"atividades": count},
    )
    await session.commit()
    return {"obra_id": obra_id, "atividades_processadas": count}
