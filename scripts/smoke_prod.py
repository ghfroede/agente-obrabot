#!/usr/bin/env python3
"""Smoke E2E de produção: health + webhook OpenClaw assinado.

Uso local (com env de produção exportadas):
  OBRABOT_API_URL=https://api-production-8bfb.up.railway.app \\
  OPENCLAW_SHARED_SECRET=... \\
  TELEGRAM_ALLOWED_CHAT_IDS=... \\
  TELEGRAM_ALLOWED_USER_IDS=... \\
  uv run python scripts/smoke_prod.py

Uso Railway (recomendado — injeta vars do serviço api):
  railway run --service api uv run python scripts/smoke_prod.py
"""
from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    base = os.environ.get(
        "OBRABOT_API_URL", "https://api-production-8bfb.up.railway.app"
    ).rstrip("/")
    steps = [
        [sys.executable, "scripts/smoke_api.py", base],
        [sys.executable, "scripts/smoke_openclaw.py", base],
    ]
    for cmd in steps:
        print(f"\n>>> {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            return result.returncode
    print(f"\nsmoke-prod ({base}): PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
