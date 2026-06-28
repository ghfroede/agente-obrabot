"""Remove dados de teste de uma obra (DB + bucket S3).

Uso (produção via Railway):
  railway run --service api python scripts/cleanup_obra_teste.py OBRA-TESTE
  railway run --service api python scripts/cleanup_obra_teste.py OBRA-TESTE --dry-run
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import boto3
from sqlalchemy import delete, select, text

from src.config.env import get_settings
from src.db.client import SyncSessionLocal
from src.db.models import (
    Aprovacao,
    Arquivo,
    AudioTranscricao,
    AuditoriaEvento,
    CronogramaAtividade,
    Documento,
    EntradaBruta,
    Foto,
    IdempotencyKey,
    Medicao,
    Obra,
    OrcamentoItem,
    Task,
    TelegramMessage,
    Triagem,
)


def _s3_client() -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
        region_name=settings.s3_region,
    )


def delete_s3_prefix(obra_id: str, *, dry_run: bool) -> int:
    settings = get_settings()
    if not settings.s3_configured:
        print("S3 não configurado — pulando limpeza de bucket.")
        return 0

    prefix = f"obras/{obra_id}/"
    client = _s3_client()
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket_name, Prefix=prefix):
        keys = [obj["Key"] for obj in page.get("Contents", [])]
        if not keys:
            continue
        if dry_run:
            for key in keys:
                print(f"  [dry-run] s3://{settings.s3_bucket_name}/{key}")
            deleted += len(keys)
            continue
        for i in range(0, len(keys), 1000):
            batch = keys[i : i + 1000]
            client.delete_objects(
                Bucket=settings.s3_bucket_name,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
            deleted += len(batch)
    return deleted


def cleanup_db(obra_id: str, *, dry_run: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    with SyncSessionLocal() as session:
        obra = session.execute(select(Obra).where(Obra.id == obra_id)).scalar_one_or_none()
        if obra is None:
            print(f"Obra '{obra_id}' não encontrada no banco.")
            return counts

        doc_ids = list(
            session.execute(select(Documento.id).where(Documento.obra_id == obra_id)).scalars()
        )
        task_ids = list(
            session.execute(
                select(EntradaBruta.task_id).where(
                    EntradaBruta.obra_id == obra_id, EntradaBruta.task_id.is_not(None)
                )
            ).scalars()
        )

        steps: list[tuple[str, Any]] = []
        if doc_ids:
            steps.append(
                ("aprovacoes", delete(Aprovacao).where(Aprovacao.documento_id.in_(doc_ids)))
            )
        steps.extend(
            [
                ("triagens", delete(Triagem).where(Triagem.obra_id == obra_id)),
                ("fotos", delete(Foto).where(Foto.obra_id == obra_id)),
                (
                    "audios_transcricoes",
                    delete(AudioTranscricao).where(AudioTranscricao.obra_id == obra_id),
                ),
                ("documentos", delete(Documento).where(Documento.obra_id == obra_id)),
                ("arquivos", delete(Arquivo).where(Arquivo.obra_id == obra_id)),
                (
                    "telegram_messages",
                    delete(TelegramMessage).where(TelegramMessage.obra_id == obra_id),
                ),
                ("entradas_brutas", delete(EntradaBruta).where(EntradaBruta.obra_id == obra_id)),
                (
                    "auditoria_eventos",
                    delete(AuditoriaEvento).where(AuditoriaEvento.obra_id == obra_id),
                ),
                ("medicoes", delete(Medicao).where(Medicao.obra_id == obra_id)),
                ("orcamento_itens", delete(OrcamentoItem).where(OrcamentoItem.obra_id == obra_id)),
                (
                    "cronograma_atividades",
                    delete(CronogramaAtividade).where(CronogramaAtividade.obra_id == obra_id),
                ),
                (
                    "idempotency_keys",
                    delete(IdempotencyKey).where(IdempotencyKey.obra_id == obra_id),
                ),
            ]
        )
        if task_ids:
            steps.append(("tasks", delete(Task).where(Task.id.in_(task_ids))))
        steps.append(("obras", delete(Obra).where(Obra.id == obra_id)))

        if dry_run:
            for name, _ in steps:
                counts[name] = 0
                print(f"  [dry-run] DELETE {name} (obra={obra_id})")
            return counts

        for name, stmt in steps:
            result = session.execute(stmt)
            counts[name] = result.rowcount or 0
            print(f"  {name}: {counts[name]} removidos")

        session.commit()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpa dados de teste de uma obra.")
    parser.add_argument(
        "obra_id",
        default="OBRA-TESTE",
        nargs="?",
        help="ID da obra (default: OBRA-TESTE)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Apenas listar o que seria removido")
    args = parser.parse_args()

    print(f"=== Limpeza obra '{args.obra_id}' (dry_run={args.dry_run}) ===")
    print("DB:")
    db_counts = cleanup_db(args.obra_id, dry_run=args.dry_run)
    print("S3:")
    s3_count = delete_s3_prefix(args.obra_id, dry_run=args.dry_run)
    print(f"  objetos S3: {s3_count}")

    if not args.dry_run and db_counts:
        with SyncSessionLocal() as session:
            remaining = session.execute(
                text("SELECT COUNT(*) FROM obras WHERE id = :id"), {"id": args.obra_id}
            ).scalar()
        print(f"Verificação: obras restantes com id={args.obra_id!r}: {remaining}")

    print("Concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
