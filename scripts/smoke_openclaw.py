#!/usr/bin/env python3
"""Smoke test do webhook OpenClaw (dev sem secret ou prod com HMAC)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import UTC, datetime

import httpx

PATH = "/api/v1/openclaw/telegram-event"


def _first_csv_int(name: str, default: int | None = None) -> int | None:
    values = os.environ.get(name, "")
    for item in values.split(","):
        item = item.strip()
        if item:
            return int(item)
    return default


def _sign(secret: str, timestamp: str, event_id: str, body: bytes, base: str) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([timestamp, event_id, "POST", PATH, body_hash]).encode()
    return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
    secret = os.environ.get("OPENCLAW_SHARED_SECRET", "")
    event_id = f"smoke-{uuid.uuid4().hex[:12]}"
    chat_id = _first_csv_int("TELEGRAM_ALLOWED_CHAT_IDS", 999999)
    user_id = _first_csv_int("TELEGRAM_ALLOWED_USER_IDS")
    thread_id = _first_csv_int("TELEGRAM_ALLOWED_THREAD_IDS")
    telegram: dict[str, object] = {
        "message_id": 1,
        "chat": {"id": chat_id, "type": "group" if chat_id and chat_id < 0 else "private"},
        "text": "smoke test openclaw",
    }
    if user_id is not None:
        telegram["from"] = {"id": user_id, "username": "smoke"}
    if thread_id is not None:
        telegram["message_thread_id"] = thread_id

    payload = {
        "event_id": event_id,
        "obra_id": "OBRA-SMOKE",
        "telegram": telegram,
    }
    body = json.dumps(payload).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if secret:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        headers["X-OpenClaw-Timestamp"] = ts
        headers["X-OpenClaw-Event-Id"] = event_id
        headers["X-OpenClaw-Signature"] = _sign(secret, ts, event_id, body, base)

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{base}{PATH}", content=body, headers=headers)
        print(f"POST {PATH} -> {resp.status_code}")
        if resp.status_code not in (202, 404):
            print(resp.text, file=sys.stderr)
            return 1
        if resp.status_code == 404:
            print("obra OBRA-SMOKE não existe — webhook autenticado OK")
        else:
            print(resp.json())

    print(f"smoke-openclaw ({base}): PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
