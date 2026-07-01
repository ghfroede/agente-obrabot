from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, ValidationError
from src.db.models import CronogramaAtividade, Obra, OrcamentoItem
from src.services import audit_service, bucket_service
from src.utils.dates import parse_date, today_iso, utc_now

BASELINE_META_KEY = "baseline"


async def _get_obra(session: AsyncSession, obra_id: str) -> Obra:
    obra = await session.get(Obra, obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    return obra


def _normalize_orcamento_item(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    codigo = str(item.get("codigo") or f"ITEM-{index + 1}").strip()
    if not codigo:
        raise ValidationError(f"Item {index + 1}: codigo obrigatório")
    descricao = str(item.get("descricao") or codigo).strip()
    if not descricao:
        raise ValidationError(f"Item {codigo}: descricao obrigatória")
    quantidade = item.get("quantidade")
    valor_unitario = item.get("valor_unitario")
    qty = float(quantidade) if quantidade is not None else 0.0
    unit = float(valor_unitario) if valor_unitario is not None else 0.0
    valor_total = item.get("valor_total")
    total = float(valor_total) if valor_total is not None else qty * unit
    merged = dict(item)
    merged.update(
        {
            "codigo": codigo,
            "descricao": descricao,
            "unidade": item.get("unidade"),
            "quantidade": quantidade,
            "valor_unitario": valor_unitario,
            "valor_total": total,
        }
    )
    return merged


def _normalize_cronograma_atividade(atv: dict[str, Any], *, index: int) -> dict[str, Any]:
    codigo = str(atv.get("codigo") or f"ATV-{index + 1}").strip()
    if not codigo:
        raise ValidationError(f"Atividade {index + 1}: codigo obrigatório")
    nome = str(
        atv.get("nome") or atv.get("descricao") or codigo
    ).strip()
    inicio_raw = (
        atv.get("inicio_previsto")
        or atv.get("inicio_planejado")
        or atv.get("data_inicio")
    )
    fim_raw = (
        atv.get("fim_previsto")
        or atv.get("fim_planejado")
        or atv.get("data_fim")
    )
    percentual = atv.get("percentual_concluido", atv.get("percentual_planejado", 0))
    merged = dict(atv)
    merged.update(
        {
            "codigo": codigo,
            "nome": nome,
            "inicio_previsto": parse_date(inicio_raw) if inicio_raw else None,
            "fim_previsto": parse_date(fim_raw) if fim_raw else None,
            "percentual_concluido": float(percentual or 0),
            "codigo_orcamento": atv.get("codigo_orcamento"),
        }
    )
    return merged


def _orcamento_item_to_dict(row: OrcamentoItem) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "codigo": row.codigo,
        "descricao": row.descricao,
        "unidade": row.unidade,
        "quantidade": row.quantidade,
        "valor_unitario": row.valor_unitario,
        "valor_total": row.valor_total,
    }


def _cronograma_atividade_to_dict(row: CronogramaAtividade) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "codigo": row.codigo,
        "nome": row.nome,
        "inicio_previsto": row.inicio_previsto.isoformat() if row.inicio_previsto else None,
        "fim_previsto": row.fim_previsto.isoformat() if row.fim_previsto else None,
        "percentual_concluido": row.percentual_concluido,
        "codigo_orcamento": (row.metadata_json or {}).get("codigo_orcamento"),
    }


async def list_orcamento(session: AsyncSession, *, obra_id: str) -> dict[str, Any]:
    await _get_obra(session, obra_id)
    result = await session.execute(
        select(OrcamentoItem)
        .where(OrcamentoItem.obra_id == obra_id)
        .order_by(OrcamentoItem.codigo.asc())
    )
    itens = [_orcamento_item_to_dict(row) for row in result.scalars().all()]
    return {"obra_id": obra_id, "itens": itens, "total": len(itens)}


async def list_cronograma(session: AsyncSession, *, obra_id: str) -> dict[str, Any]:
    await _get_obra(session, obra_id)
    result = await session.execute(
        select(CronogramaAtividade)
        .where(CronogramaAtividade.obra_id == obra_id)
        .order_by(CronogramaAtividade.codigo.asc())
    )
    atividades = [_cronograma_atividade_to_dict(row) for row in result.scalars().all()]
    return {"obra_id": obra_id, "atividades": atividades, "total": len(atividades)}


async def validate_baseline(session: AsyncSession, *, obra_id: str) -> dict[str, Any]:
    obra = await _get_obra(session, obra_id)
    orc_result = await session.execute(
        select(func.count()).select_from(OrcamentoItem).where(OrcamentoItem.obra_id == obra_id)
    )
    cron_result = await session.execute(
        select(func.count())
        .select_from(CronogramaAtividade)
        .where(CronogramaAtividade.obra_id == obra_id)
    )
    orc_count = int(orc_result.scalar_one())
    cron_count = int(cron_result.scalar_one())

    avisos: list[str] = []
    bloqueios: list[str] = []
    if orc_count == 0:
        bloqueios.append("Orçamento sem itens importados")
    if cron_count == 0:
        bloqueios.append("Cronograma sem atividades importadas")

    orc_codigos = set(
        (
            await session.execute(
                select(OrcamentoItem.codigo).where(OrcamentoItem.obra_id == obra_id)
            )
        )
        .scalars()
        .all()
    )
    cron_rows = (
        await session.execute(
            select(CronogramaAtividade).where(CronogramaAtividade.obra_id == obra_id)
        )
    ).scalars().all()

    for atv in cron_rows:
        if atv.inicio_previsto and atv.fim_previsto and atv.fim_previsto < atv.inicio_previsto:
            avisos.append(f"Atividade {atv.codigo}: fim anterior ao início")
        codigo_orc = (atv.metadata_json or {}).get("codigo_orcamento")
        if codigo_orc and codigo_orc not in orc_codigos:
            avisos.append(
                f"Atividade {atv.codigo}: codigo_orcamento {codigo_orc} não existe no orçamento"
            )

    for row in (
        await session.execute(
            select(OrcamentoItem).where(OrcamentoItem.obra_id == obra_id)
        )
    ).scalars().all():
        if row.quantidade is None or row.valor_unitario is None:
            avisos.append(f"Item {row.codigo}: quantidade ou valor unitário ausente")

    baseline_meta = (obra.metadata_json or {}).get(BASELINE_META_KEY) or {}
    pronto = len(bloqueios) == 0
    return {
        "obra_id": obra_id,
        "orcamento_itens": orc_count,
        "cronograma_atividades": cron_count,
        "baseline_status": baseline_meta.get("status", "pendente"),
        "pronto_para_aprovacao": pronto,
        "bloqueios": bloqueios,
        "avisos": avisos,
    }


async def import_orcamento(
    session: AsyncSession,
    *,
    obra_id: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    obra = await _get_obra(session, obra_id)
    if not itens:
        raise ValidationError("Lista de itens vazia")

    count = 0
    avisos: list[str] = []
    for index, raw in enumerate(itens):
        item = _normalize_orcamento_item(raw, index=index)
        if item.get("quantidade") is None or item.get("valor_unitario") is None:
            avisos.append(f"Item {item['codigo']}: quantidade ou valor unitário ausente")
        codigo = item["codigo"]
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
                descricao=item["descricao"],
            )
            session.add(row)
        row.descricao = item["descricao"]
        row.unidade = item.get("unidade")
        row.quantidade = item.get("quantidade")
        row.valor_unitario = item.get("valor_unitario")
        qty = float(row.quantidade or 0)
        unit = float(row.valor_unitario or 0)
        row.valor_total = item.get("valor_total") or (qty * unit)
        row.metadata_json = item
        count += 1

    await audit_service.log_event(
        session,
        entidade="orcamento",
        entidade_id=obra_id,
        acao="importado",
        obra_id=obra_id,
        detalhes={"itens": count, "avisos": avisos},
    )
    await session.commit()
    return {
        "obra_id": obra_id,
        "itens_processados": count,
        "avisos": avisos,
        "obra_slug": obra.slug,
    }


def _json_safe_metadata(data: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, date):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe


async def import_cronograma(
    session: AsyncSession,
    *,
    obra_id: str,
    atividades: list[dict[str, Any]],
) -> dict[str, Any]:
    obra = await _get_obra(session, obra_id)
    if not atividades:
        raise ValidationError("Lista de atividades vazia")

    count = 0
    avisos: list[str] = []
    for index, raw in enumerate(atividades):
        atv = _normalize_cronograma_atividade(raw, index=index)
        if atv["inicio_previsto"] is None or atv["fim_previsto"] is None:
            avisos.append(f"Atividade {atv['codigo']}: datas previstas incompletas")
        codigo = atv["codigo"]
        existing = await session.execute(
            select(CronogramaAtividade)
            .where(
                CronogramaAtividade.obra_id == obra_id,
                CronogramaAtividade.codigo == codigo,
            )
            .order_by(CronogramaAtividade.created_at.desc())
            .limit(1)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = CronogramaAtividade(
                obra_id=obra_id,
                codigo=codigo,
                nome=atv["nome"],
            )
            session.add(row)
        row.nome = atv["nome"]
        row.inicio_previsto = atv["inicio_previsto"]
        row.fim_previsto = atv["fim_previsto"]
        row.percentual_concluido = atv["percentual_concluido"]
        row.metadata_json = _json_safe_metadata(atv)
        count += 1

    await audit_service.log_event(
        session,
        entidade="cronograma",
        entidade_id=obra_id,
        acao="importado",
        obra_id=obra_id,
        detalhes={"atividades": count, "avisos": avisos},
    )
    await session.commit()
    return {
        "obra_id": obra_id,
        "atividades_processadas": count,
        "avisos": avisos,
        "obra_slug": obra.slug,
    }


def _build_baseline_snapshot(
    *,
    obra: Obra,
    orcamento: list[dict[str, Any]],
    cronograma: list[dict[str, Any]],
    aprovador: str,
    comentario: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "obra_id": obra.id,
        "obra_nome": obra.nome,
        "aprovado_em": utc_now().isoformat(),
        "aprovador": aprovador,
        "comentario": comentario,
        "orcamento": orcamento,
        "cronograma": cronograma,
    }


async def approve_baseline(
    session: AsyncSession,
    *,
    obra_id: str,
    aprovador: str,
    comentario: str | None = None,
) -> dict[str, Any]:
    validacao = await validate_baseline(session, obra_id=obra_id)
    if not validacao["pronto_para_aprovacao"]:
        raise ValidationError(
            "Baseline não está pronto: " + "; ".join(validacao["bloqueios"])
        )

    obra = await _get_obra(session, obra_id)
    orcamento = (await list_orcamento(session, obra_id=obra_id))["itens"]
    cronograma = (await list_cronograma(session, obra_id=obra_id))["atividades"]
    snapshot = _build_baseline_snapshot(
        obra=obra,
        orcamento=orcamento,
        cronograma=cronograma,
        aprovador=aprovador,
        comentario=comentario,
    )
    body = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
    data_ref = today_iso()
    key = bucket_service.build_baseline_key(
        obra_id, data_ref, slug=obra.slug, final=True
    )
    uri = bucket_service.put_bytes(
        key, body, content_type="application/json", allow_overwrite=True
    )

    metadata = dict(obra.metadata_json or {})
    metadata[BASELINE_META_KEY] = {
        "status": "validado",
        "aprovado_por": aprovador,
        "aprovado_em": utc_now().isoformat(),
        "comentario": comentario,
        "orcamento_itens": len(orcamento),
        "cronograma_atividades": len(cronograma),
        "bucket_key": key,
        "bucket_uri": uri,
        "data_ref": data_ref,
    }
    obra.metadata_json = metadata
    obra.updated_at = utc_now()

    await audit_service.log_event(
        session,
        entidade="baseline",
        entidade_id=obra_id,
        acao="aprovado",
        obra_id=obra_id,
        actor=aprovador,
        detalhes={
            "orcamento_itens": len(orcamento),
            "cronograma_atividades": len(cronograma),
            "bucket_key": key,
        },
    )
    await session.commit()
    return {
        "obra_id": obra_id,
        "status": "validado",
        "bucket_uri": uri,
        "orcamento_itens": len(orcamento),
        "cronograma_atividades": len(cronograma),
        "avisos": validacao["avisos"],
    }


async def baseline_context_for_rdo(
    session: AsyncSession, *, obra_id: str
) -> dict[str, Any] | None:
    obra = await session.get(Obra, obra_id)
    if obra is None:
        return None
    baseline_meta = (obra.metadata_json or {}).get(BASELINE_META_KEY)
    if not baseline_meta or baseline_meta.get("status") != "validado":
        return None

    orc_count = int(
        (
            await session.execute(
                select(func.count()).select_from(OrcamentoItem).where(
                    OrcamentoItem.obra_id == obra_id
                )
            )
        ).scalar_one()
    )
    cron_rows = (
        await session.execute(
            select(CronogramaAtividade).where(CronogramaAtividade.obra_id == obra_id)
        )
    ).scalars().all()
    hoje = date.today()
    atividades_no_periodo = [
        _cronograma_atividade_to_dict(row)
        for row in cron_rows
        if row.inicio_previsto and row.fim_previsto
        and row.inicio_previsto <= hoje <= row.fim_previsto
    ]
    return {
        "status": baseline_meta.get("status"),
        "aprovado_em": baseline_meta.get("aprovado_em"),
        "orcamento_itens": orc_count,
        "cronograma_atividades": len(cron_rows),
        "atividades_no_periodo": atividades_no_periodo,
        "bucket_uri": baseline_meta.get("bucket_uri"),
    }
