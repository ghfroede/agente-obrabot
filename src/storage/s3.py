from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.client import BaseClient

from src.config.env import get_settings


def _get_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
        region_name=settings.s3_region,
    )


def _build_key(obra_id: str) -> str:
    now = datetime.now(UTC)
    digest = hashlib.sha256(f"{now.isoformat()}-{obra_id}".encode()).hexdigest()[:12]
    return (
        f"obras/{obra_id}/01_entrada_bruta/api/"
        f"{now.year}/{now.month:02d}/{now.day:02d}/entrada_{digest}/envelope.json"
    )


def persist_raw_entry(
    *,
    obra_id: str,
    message: str,
    metadata: dict[str, Any],
) -> str:
    """Persiste entrada bruta no bucket S3-compatible (MEGA S4)."""
    settings = get_settings()
    client = _get_client()
    key = _build_key(obra_id)
    payload = {
        "obra_id": obra_id,
        "message": message,
        "metadata": metadata,
        "received_at": datetime.now(UTC).isoformat(),
        "hash_sha256": hashlib.sha256(message.encode()).hexdigest(),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )
    return f"s3://{settings.s3_bucket_name}/{key}"
