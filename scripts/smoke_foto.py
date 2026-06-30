#!/usr/bin/env python3
"""Smoke E2E do relatório fotográfico: gerar rascunho + aprovar-finalizar PDF.

Uso Railway (recomendado):
  railway run --service api uv run python scripts/smoke_foto.py

Variáveis:
  OBRABOT_API_URL, OBRABOT_API_KEY
  SMOKE_OBRA_ID (default: OBRA-SMOKE)
  SMOKE_PERIODO_INICIO / SMOKE_PERIODO_FIM (default: hoje UTC)
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import httpx


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def main() -> int:
    base = os.environ.get(
        "OBRABOT_API_URL", "https://api-production-8bfb.up.railway.app"
    ).rstrip("/")
    api_key = os.environ.get("OBRABOT_API_KEY", "")
    if not api_key:
        print("OBRABOT_API_KEY não configurada.", file=sys.stderr)
        return 2

    obra_id = os.environ.get("SMOKE_OBRA_ID", "OBRA-SMOKE")
    periodo = os.environ.get("SMOKE_PERIODO_INICIO", _today())
    periodo_fim = os.environ.get("SMOKE_PERIODO_FIM", periodo)
    headers = {"X-Obrabot-API-Key": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=60.0) as client:
        gerar = client.post(
            f"{base}/api/v1/fotos/relatorio",
            headers=headers,
            json={
                "obra_id": obra_id,
                "periodo_inicio": periodo,
                "periodo_fim": periodo_fim,
            },
        )
        print(f"POST /fotos/relatorio -> {gerar.status_code}")
        gerar.raise_for_status()
        draft = gerar.json()
        documento_id = draft["documento_id"]
        print(
            f"Rascunho: {documento_id} ({draft.get('revisao')}) "
            f"— {draft.get('fotos_incluidas', 0)} foto(s)"
        )

        finalizar = client.post(
            f"{base}/api/v1/fotos/relatorio/aprovar-finalizar",
            headers=headers,
            json={
                "documento_id": documento_id,
                "aprovador": "smoke-foto",
                "comentario": "Smoke E2E GHF-223",
            },
        )
        print(f"POST /fotos/relatorio/aprovar-finalizar -> {finalizar.status_code}")
        finalizar.raise_for_status()
        result = finalizar.json()

    if result.get("formato") != "pdf":
        print(f"formato inesperado: {result}", file=sys.stderr)
        return 1
    if result.get("status") != "FINALIZADO_VALIDADO":
        print(f"status inesperado: {result}", file=sys.stderr)
        return 1

    print(f"smoke-foto ({base}): PASS — PDF em {result.get('bucket_uri', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
