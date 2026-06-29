#!/usr/bin/env python3
"""Cadastra/atualiza uma obra via API administrativa.

Uso:
  uv run python scripts/seed_obras.py OBRA-001 "Nome da Obra"

Variáveis:
  OBRABOT_API_URL   Base URL da API (default: http://localhost:8000)
  OBRABOT_API_KEY   API key administrativa
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("obra_id")
    parser.add_argument("nome")
    parser.add_argument("--status", default="ativa")
    args = parser.parse_args()

    base_url = os.environ.get("OBRABOT_API_URL", "http://localhost:8000").rstrip("/")
    api_key = os.environ.get("OBRABOT_API_KEY", "")
    if not api_key:
        print("OBRABOT_API_KEY não configurada.", file=sys.stderr)
        return 2

    payload = {"id": args.obra_id, "nome": args.nome, "status": args.status}
    headers = {"X-Obrabot-API-Key": api_key}
    with httpx.Client(timeout=20.0) as client:
        response = client.post(f"{base_url}/api/v1/obras", json=payload, headers=headers)
        if response.status_code >= 400:
            print(f"Erro {response.status_code}: {response.text}", file=sys.stderr)
            return 1
        obra = response.json()

    print(f"Obra cadastrada: {obra['id']} — {obra['nome']} ({obra['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
