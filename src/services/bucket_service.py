from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from src.config.env import get_settings
from src.core.constants import GENERATED_BY, SCHEMA_VERSION
from src.core.errors import BucketConflictError
from src.utils.hashing import sha256_hex


def _get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
        region_name=settings.s3_region,
    )


def _local_root() -> Path:
    settings = get_settings()
    root = Path(settings.local_bucket_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _use_s3() -> bool:
    return get_settings().s3_configured


def _uri(key: str) -> str:
    settings = get_settings()
    return f"s3://{settings.s3_bucket_name}/{key}"


def build_entrada_bruta_key(obra_id: str, event_id: str, source: str = "telegram") -> str:
    now = datetime.now(UTC)
    return (
        f"obras/{obra_id}/01_entrada_bruta/{source}/"
        f"{now.year}/{now.month:02d}/{now.day:02d}/evt_{event_id}/envelope.json"
    )


def build_arquivo_key(obra_id: str, tipo: str, file_hash: str, ext: str) -> str:
    now = datetime.now(UTC)
    return (
        f"obras/{obra_id}/02_arquivos/{tipo}/"
        f"{now.year}/{now.month:02d}/{file_hash[:16]}.{ext.lstrip('.')}"
    )


def build_documento_key(
    obra_id: str,
    tipo: str,
    data_ref: str,
    revisao: str,
    filename: str,
    *,
    draft: bool = True,
) -> str:
    area = "03_rascunhos" if draft else "04_documentos_finais"
    return f"obras/{obra_id}/{area}/{tipo}/{data_ref}/{revisao}/{filename}"


def build_metadata_key(documento_key: str) -> str:
    base, _, name = documento_key.rpartition("/")
    stem = name.rsplit(".", 1)[0]
    return f"{base}/{stem}.metadata.json"


def _object_exists(key: str) -> bool:
    settings = get_settings()
    if _use_s3():
        client = _get_s3_client()
        try:
            client.head_object(Bucket=settings.s3_bucket_name, Key=key)
            return True
        except ClientError:
            return False
    return (_local_root() / key).exists()


def put_bytes(
    key: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
    allow_overwrite: bool = True,
) -> str:
    if not allow_overwrite and _object_exists(key):
        raise BucketConflictError(f"Objeto já existe: {key}")

    settings = get_settings()
    if _use_s3():
        client = _get_s3_client()
        client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    else:
        path = _local_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return _uri(key)


def put_json(key: str, payload: dict[str, Any], *, allow_overwrite: bool = True) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return put_bytes(key, body, content_type="application/json", allow_overwrite=allow_overwrite)


def get_bytes(key: str) -> bytes:
    settings = get_settings()
    if _use_s3():
        client = _get_s3_client()
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=key)
        body: bytes = response["Body"].read()
        return body
    return (_local_root() / key).read_bytes()


def persist_entrada_bruta(
    *,
    obra_id: str,
    event_id: str,
    envelope: dict[str, Any],
    source: str = "telegram",
) -> tuple[str, str]:
    key = build_entrada_bruta_key(obra_id, event_id, source)
    envelope = {
        **envelope,
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "received_at": datetime.now(UTC).isoformat(),
    }
    text = json.dumps(envelope, ensure_ascii=False)
    envelope["hash_sha256"] = sha256_hex(text.encode("utf-8"))
    uri = put_json(key, envelope)
    return key, uri


def persist_sidecar_metadata(documento_key: str, metadata: dict[str, Any]) -> str:
    meta_key = build_metadata_key(documento_key)
    payload = {
        **metadata,
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "documento_key": documento_key,
    }
    return put_json(meta_key, payload)
