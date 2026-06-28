#!/usr/bin/env python3
"""Smoke test da API. Uso: uv run python scripts/smoke_api.py [BASE_URL]"""
from __future__ import annotations

import sys

import httpx

DEFAULT_URL = "http://localhost:8000"


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL).rstrip("/")
    with httpx.Client(timeout=15.0) as client:
        health = client.get(f"{base}/health")
        health.raise_for_status()
        data = health.json()
        assert data.get("status") == "healthy", data
        print(f"GET /health OK: {data}")

    print(f"smoke-api ({base}): PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
