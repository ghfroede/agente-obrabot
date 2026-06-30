from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, ValidationError
from src.db.models import Arquivo, AudioTranscricao, EntradaBruta, Foto, Obra, Triagem
from src.utils.dates import parse_date


async def aggregate_daily_rdo(
    session: AsyncSession, *, obra_id: str, data_ref: str
) -> dict[str, Any]:
    data_parsed = parse_date(data_ref)
    if data_parsed is None:
        raise ValidationError(f"data_ref inválida: {data_ref}")

    obra = await session.get(Obra, obra_id)
    if obra is None:
        raise NotFoundError(f"Obra {obra_id} não encontrada")

    entradas = await _list_entradas(session, obra_id=obra.id, data_ref=data_parsed)
    if not entradas:
        raise NotFoundError(f"Nenhuma entrada encontrada para {obra.id} em {data_ref}")

    entrada_ids = [entrada.id for entrada in entradas]
    triagens = await _list_triagens(session, obra_id=obra.id, entrada_ids=entrada_ids)
    arquivos = await _list_arquivos(session, obra_id=obra.id, entrada_ids=entrada_ids)
    fotos = await _list_fotos(session, obra_id=obra.id, data_ref=data_parsed)
    audios = await _list_audios(session, obra_id=obra.id, entrada_ids=entrada_ids)

    triagens_por_entrada = _group_triagens_by_entrada(triagens)
    arquivo_ids = _source_arquivo_ids(arquivos, fotos, audios)

    return {
        "tipo": "rdo",
        "obra": {"id": obra.id, "nome": obra.nome},
        "data_ref": data_ref,
        "source_entrada_ids": [str(entrada_id) for entrada_id in entrada_ids],
        "source_arquivo_ids": sorted(arquivo_ids),
        "resumo_operacional": {
            "entradas_count": len(entradas),
            "triagens_count": len(triagens),
            "fotos_count": len(fotos),
            "audios_count": len(audios),
            "arquivos_count": len(arquivos),
        },
        "servicos": [
            _entrada_summary(entrada, triagens_por_entrada.get(entrada.id, []))
            for entrada in entradas
        ],
        "pendencias": _collect_pendencias(triagens),
        "fotos": [_foto_summary(foto, arquivo) for foto, arquivo in fotos],
        "audios": [_audio_summary(audio, arquivo) for audio, arquivo in audios],
        "documentos_brutos": [
            _arquivo_summary(arquivo) for arquivo in arquivos if arquivo.tipo == "documento"
        ],
        "campos_editaveis": {
            "clima": None,
            "equipe": [],
            "equipamentos": [],
            "observacoes": [],
            "complementos_engenheiro": [],
        },
    }


async def _list_entradas(
    session: AsyncSession, *, obra_id: str, data_ref: date
) -> list[EntradaBruta]:
    result = await session.execute(
        select(EntradaBruta)
        .where(EntradaBruta.obra_id == obra_id, EntradaBruta.data_ref == data_ref)
        .order_by(EntradaBruta.created_at.asc())
    )
    return list(result.scalars().all())


async def _list_triagens(
    session: AsyncSession, *, obra_id: str, entrada_ids: list[uuid.UUID]
) -> list[Triagem]:
    result = await session.execute(
        select(Triagem)
        .where(Triagem.obra_id == obra_id, Triagem.entrada_id.in_(entrada_ids))
        .order_by(Triagem.created_at.asc())
    )
    return list(result.scalars().all())


async def _list_arquivos(
    session: AsyncSession, *, obra_id: str, entrada_ids: list[uuid.UUID]
) -> list[Arquivo]:
    result = await session.execute(
        select(Arquivo)
        .where(Arquivo.obra_id == obra_id, Arquivo.entrada_id.in_(entrada_ids))
        .order_by(Arquivo.created_at.asc())
    )
    return list(result.scalars().all())


async def _list_fotos(
    session: AsyncSession, *, obra_id: str, data_ref: date
) -> list[tuple[Foto, Arquivo]]:
    result = await session.execute(
        select(Foto, Arquivo)
        .join(Arquivo, Foto.arquivo_id == Arquivo.id)
        .where(Foto.obra_id == obra_id, Foto.data_foto == data_ref)
        .order_by(Foto.created_at.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def _list_audios(
    session: AsyncSession, *, obra_id: str, entrada_ids: list[uuid.UUID]
) -> list[tuple[AudioTranscricao, Arquivo]]:
    result = await session.execute(
        select(AudioTranscricao, Arquivo)
        .join(Arquivo, AudioTranscricao.arquivo_id == Arquivo.id)
        .where(Arquivo.obra_id == obra_id, Arquivo.entrada_id.in_(entrada_ids))
        .order_by(AudioTranscricao.created_at.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


def _group_triagens_by_entrada(triagens: list[Triagem]) -> dict[uuid.UUID, list[Triagem]]:
    grouped: dict[uuid.UUID, list[Triagem]] = {}
    for triagem in triagens:
        if triagem.entrada_id is None:
            continue
        grouped.setdefault(triagem.entrada_id, []).append(triagem)
    return grouped


def _source_arquivo_ids(
    arquivos: list[Arquivo],
    fotos: list[tuple[Foto, Arquivo]],
    audios: list[tuple[AudioTranscricao, Arquivo]],
) -> set[str]:
    ids = {str(arquivo.id) for arquivo in arquivos}
    ids.update(str(arquivo.id) for _, arquivo in fotos)
    ids.update(str(arquivo.id) for _, arquivo in audios)
    return ids


def _entrada_summary(entrada: EntradaBruta, triagens: list[Triagem]) -> dict[str, Any]:
    return {
        "entrada_id": str(entrada.id),
        "source": entrada.source,
        "status": entrada.status,
        "author": entrada.author,
        "created_at": entrada.created_at.isoformat() if entrada.created_at else None,
        "text": entrada.text,
        "storage_uri": entrada.storage_uri,
        "triagens": [_triagem_summary(triagem) for triagem in triagens],
    }


def _triagem_summary(triagem: Triagem) -> dict[str, Any]:
    return {
        "triagem_id": str(triagem.id),
        "documento_id": str(triagem.documento_id) if triagem.documento_id else None,
        "tipo_documento": triagem.tipo_documento,
        "confianca": triagem.confianca,
        "resumo": triagem.resumo,
        "created_at": triagem.created_at.isoformat() if triagem.created_at else None,
        "campos_extraidos": triagem.campos_extraidos or {},
        "acao_sugerida": triagem.acao_sugerida,
        "precisa_aprovacao": triagem.precisa_aprovacao,
    }


def _collect_pendencias(triagens: list[Triagem]) -> list[str]:
    pendencias: list[str] = []
    for triagem in triagens:
        campos = triagem.campos_extraidos or {}
        raw = campos.get("pendencias")
        if isinstance(raw, list):
            pendencias.extend(str(item) for item in raw if str(item).strip())
        elif isinstance(raw, str) and raw.strip():
            pendencias.append(raw.strip())
    return pendencias


def _foto_summary(foto: Foto, arquivo: Arquivo) -> dict[str, Any]:
    return {
        "foto_id": str(foto.id),
        "arquivo_id": str(arquivo.id),
        "entrada_id": str(arquivo.entrada_id) if arquivo.entrada_id else None,
        "data_foto": foto.data_foto.isoformat() if foto.data_foto else None,
        "created_at": foto.created_at.isoformat() if foto.created_at else None,
        "descricao": foto.descricao,
        "bucket_uri": arquivo.bucket_uri,
    }


def _audio_summary(audio: AudioTranscricao, arquivo: Arquivo) -> dict[str, Any]:
    return {
        "audio_id": str(audio.id),
        "arquivo_id": str(arquivo.id),
        "entrada_id": str(arquivo.entrada_id) if arquivo.entrada_id else None,
        "created_at": audio.created_at.isoformat() if audio.created_at else None,
        "transcricao": audio.transcricao,
        "bucket_uri": arquivo.bucket_uri,
    }


def _arquivo_summary(arquivo: Arquivo) -> dict[str, Any]:
    return {
        "arquivo_id": str(arquivo.id),
        "entrada_id": str(arquivo.entrada_id) if arquivo.entrada_id else None,
        "tipo": arquivo.tipo,
        "nome_original": arquivo.nome_original,
        "mime_type": arquivo.mime_type,
        "created_at": arquivo.created_at.isoformat() if arquivo.created_at else None,
        "bucket_uri": arquivo.bucket_uri,
        "hash_sha256": arquivo.hash_sha256,
    }
