from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, ValidationError
from src.db.models import Medicao, MedicaoPeriodo, MedicaoPeriodoStatus, Obra, OrcamentoItem
from src.services import audit_service
from src.utils.dates import utc_now

_PERIODO_RE = re.compile(r"^(?P<ano>\d{4})-(?P<mes>\d{2})$")
_CODIGO_ALIASES: tuple[str, ...] = (
    "codigo_orcamento",
    "codigoOrcamento",
    "codigo_orçamento",
    "orcamento_codigo",
    "codigo",
)
_QUANTIDADE_ALIASES: tuple[str, ...] = (
    "quantidade_medida",
    "quantidadeMedida",
    "quantidade",
    "qtd",
    "medido",
)
_VALOR_ALIASES: tuple[str, ...] = ("valor_medido", "valorMedido", "valor")
_OBS_ALIASES: tuple[str, ...] = ("observacoes", "observações", "obs")


@dataclass(frozen=True)
class _NormalizedMedicaoItem:
    codigo_orcamento: str
    quantidade_medida: float
    valor_medido: float | None
    descricao: str | None
    unidade: str | None
    observacoes: str | None
    raw: dict[str, Any]
    orcamento_item: OrcamentoItem


async def _get_obra(session: AsyncSession, obra_id: str) -> Obra:
    obra = await session.get(Obra, obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")
    return obra


def _normalize_periodo_ref(periodo_ref: str) -> str:
    value = str(periodo_ref).strip()
    match = _PERIODO_RE.fullmatch(value)
    if match is None:
        raise ValidationError("periodo_ref deve usar o formato YYYY-MM")
    mes = int(match.group("mes"))
    if mes < 1 or mes > 12:
        raise ValidationError("periodo_ref deve ter mês entre 01 e 12")
    return value


def _status_value(status: object) -> str:
    if isinstance(status, MedicaoPeriodoStatus):
        return status.value
    return str(status)


def _first_present(item: dict[str, Any], aliases: tuple[str, ...]) -> object | None:
    for alias in aliases:
        if alias in item and item[alias] is not None:
            value: object = item[alias]
            return value
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_codigo(item: dict[str, Any], *, index: int) -> str:
    raw = _first_present(item, _CODIGO_ALIASES)
    codigo = _optional_str(raw)
    if codigo is None:
        raise ValidationError(f"Item {index + 1}: codigo_orcamento obrigatório")
    return codigo


def _required_float(
    item: dict[str, Any], aliases: tuple[str, ...], *, field: str, index: int
) -> float:
    raw = _first_present(item, aliases)
    if raw is None:
        raise ValidationError(f"Item {index + 1}: {field} obrigatório")
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Item {index + 1}: {field} inválido") from exc
    return value


def _optional_float(item: dict[str, Any], aliases: tuple[str, ...], *, index: int) -> float | None:
    raw = _first_present(item, aliases)
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Item {index + 1}: valor_medido inválido") from exc


async def _find_periodo(
    session: AsyncSession, *, obra_id: str, periodo_ref: str
) -> MedicaoPeriodo | None:
    result = await session.execute(
        select(MedicaoPeriodo).where(
            MedicaoPeriodo.obra_id == obra_id,
            MedicaoPeriodo.periodo_ref == periodo_ref,
        )
    )
    return result.scalar_one_or_none()


async def _find_orcamento_item(
    session: AsyncSession, *, obra_id: str, codigo_orcamento: str
) -> OrcamentoItem:
    result = await session.execute(
        select(OrcamentoItem).where(
            OrcamentoItem.obra_id == obra_id,
            OrcamentoItem.codigo == codigo_orcamento,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ValidationError(f"Item de orçamento {codigo_orcamento} não existe")
    return item


async def _normalize_items(
    session: AsyncSession,
    *,
    obra_id: str,
    itens: list[dict[str, Any]],
) -> list[_NormalizedMedicaoItem]:
    if not itens:
        raise ValidationError("Lista de itens vazia")

    normalized: list[_NormalizedMedicaoItem] = []
    for index, item in enumerate(itens):
        codigo = _required_codigo(item, index=index)
        quantidade = _required_float(
            item,
            _QUANTIDADE_ALIASES,
            field="quantidade_medida",
            index=index,
        )
        if quantidade < 0:
            raise ValidationError(f"Item {codigo}: quantidade_medida não pode ser negativa")
        valor_medido = _optional_float(item, _VALOR_ALIASES, index=index)
        orcamento_item = await _find_orcamento_item(
            session,
            obra_id=obra_id,
            codigo_orcamento=codigo,
        )
        normalized.append(
            _NormalizedMedicaoItem(
                codigo_orcamento=codigo,
                quantidade_medida=quantidade,
                valor_medido=valor_medido,
                descricao=_optional_str(item.get("descricao")),
                unidade=_optional_str(item.get("unidade")),
                observacoes=_optional_str(_first_present(item, _OBS_ALIASES)),
                raw=dict(item),
                orcamento_item=orcamento_item,
            )
        )
    return normalized


async def registrar_medicao(
    session: AsyncSession,
    *,
    obra_id: str,
    periodo_ref: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    obra = await _get_obra(session, obra_id)
    periodo_norm = _normalize_periodo_ref(periodo_ref)
    periodo = await _find_periodo(session, obra_id=obra_id, periodo_ref=periodo_norm)
    if periodo is not None and _status_value(periodo.status) == MedicaoPeriodoStatus.FECHADO.value:
        raise ValidationError(f"Período {periodo_norm} já fechado")

    normalized_items = await _normalize_items(session, obra_id=obra_id, itens=itens)

    if periodo is None:
        periodo = MedicaoPeriodo(
            id=uuid.uuid4(),
            obra_id=obra_id,
            periodo_ref=periodo_norm,
            status=MedicaoPeriodoStatus.ABERTO,
            metadata_json={"origem": "api"},
        )
        session.add(periodo)
        await session.flush()

    for item in normalized_items:
        med = Medicao(
            obra_id=obra_id,
            periodo_id=periodo.id,
            orcamento_item_id=item.orcamento_item.id,
            periodo_ref=periodo_norm,
            quantidade_medida=item.quantidade_medida,
            valor_medido=item.valor_medido,
            metadata_json={
                **item.raw,
                "codigo_orcamento": item.codigo_orcamento,
                "quantidade_medida": item.quantidade_medida,
                "valor_medido": item.valor_medido,
                "descricao": item.descricao,
                "unidade": item.unidade,
                "observacoes": item.observacoes,
            },
        )
        session.add(med)

    await audit_service.log_event(
        session,
        entidade="medicao",
        entidade_id=periodo_norm,
        acao="registrada",
        obra_id=obra_id,
        detalhes={
            "periodo_id": str(periodo.id),
            "itens": len(normalized_items),
            "obra_slug": obra.slug,
        },
    )
    await session.commit()
    return {
        "obra_id": obra_id,
        "periodo_ref": periodo_norm,
        "periodo_id": str(periodo.id),
        "status": _status_value(periodo.status),
        "medicoes": len(normalized_items),
    }


async def fechar_periodo(
    session: AsyncSession,
    *,
    obra_id: str,
    periodo_ref: str,
    aprovador: str,
    comentario: str | None = None,
) -> dict[str, Any]:
    await _get_obra(session, obra_id)
    periodo_norm = _normalize_periodo_ref(periodo_ref)
    periodo = await _find_periodo(session, obra_id=obra_id, periodo_ref=periodo_norm)
    if periodo is None:
        raise NotFoundError(f"Período de medição {periodo_norm} não encontrado")
    if _status_value(periodo.status) == MedicaoPeriodoStatus.FECHADO.value:
        raise ValidationError(f"Período {periodo_norm} já fechado")

    result = await session.execute(
        select(Medicao).where(
            Medicao.obra_id == obra_id,
            Medicao.periodo_ref == periodo_norm,
        )
    )
    medicoes = list(result.scalars().all())
    bloqueios: list[str] = []
    if not medicoes:
        bloqueios.append("período sem medições")
    if any(med.orcamento_item_id is None for med in medicoes):
        bloqueios.append("há item sem orçamento")
    if any(med.quantidade_medida < 0 for med in medicoes):
        bloqueios.append("há item com quantidade negativa")
    if bloqueios:
        raise ValidationError("Período não pode ser fechado: " + "; ".join(bloqueios))

    now = utc_now()
    metadata = dict(periodo.metadata_json or {})
    metadata["fechamento"] = {
        "aprovador": aprovador,
        "comentario": comentario,
        "fechado_em": now.isoformat(),
    }
    periodo.status = MedicaoPeriodoStatus.FECHADO
    periodo.closed_at = now
    periodo.updated_at = now
    periodo.metadata_json = metadata

    await audit_service.log_event(
        session,
        entidade="medicao_periodo",
        entidade_id=str(periodo.id),
        acao="fechado",
        obra_id=obra_id,
        actor=aprovador,
        detalhes={"periodo_ref": periodo_norm, "medicoes": len(medicoes), "comentario": comentario},
    )
    await session.commit()
    return {
        "obra_id": obra_id,
        "periodo_ref": periodo_norm,
        "periodo_id": str(periodo.id),
        "status": _status_value(periodo.status),
        "medicoes": len(medicoes),
    }
