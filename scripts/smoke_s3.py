#!/usr/bin/env python3
"""Smoke test do bucket (local ou MEGA S4). Uso: PYTHONPATH=. uv run python scripts/smoke_s3.py"""
from __future__ import annotations

import hashlib
import sys
import uuid

from src.core.errors import BucketConflictError
from src.services import bucket_service


def main() -> int:
    key = f"_smoke/{uuid.uuid4().hex}/test.json"
    payload = {"smoke": True, "key": key}
    uri = bucket_service.put_json(key, payload)
    print(f"put_json OK: {uri}")

    raw = bucket_service.get_bytes(key)
    assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(
        bucket_service.get_bytes(key)
    ).hexdigest()
    print("get_bytes + sha256 OK")

    assert bucket_service.head_object(key) is True
    print("head_object OK")

    bin_key = f"_smoke/{uuid.uuid4().hex}/final.bin"
    bucket_service.put_bytes(bin_key, b"final", allow_overwrite=False)
    print("put_bytes (no overwrite) OK")

    try:
        bucket_service.put_bytes(bin_key, b"overwrite", allow_overwrite=False)
        print("ERRO: sobrescrita deveria falhar", file=sys.stderr)
        return 1
    except BucketConflictError:
        print("BucketConflictError OK (sobrescrita bloqueada)")

    print("smoke-s3: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
