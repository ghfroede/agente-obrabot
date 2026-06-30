#!/usr/bin/env python3
"""Smoke E2E do fluxo RDO: gerar rascunho + aprovar-finalizar PDF.

Uso Railway (recomendado):
  railway run --service api uv run python scripts/smoke_rdo.py

Variáveis:
  OBRABOT_API_URL, OBRABOT_API_KEY
  OPENCLAW_SHARED_SECRET (opcional — semeia entrada via smoke_openclaw se gerar=404)
  SMOKE_OBRA_ID (default: OBRA-SMOKE)
  SMOKE_DATA_REF (default: hoje UTC)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import UTC, datetime

import httpx


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _seed_entrada_if_needed(base: str) -> None:
    secret = os.environ.get("OPENCLAW_SHARED_SECRET", "")
    if not secret:
        return
    print("Sem entradas do dia — executando smoke_openclaw para semear...")
    result = subprocess.run(
        [sys.executable, "scripts/smoke_openclaw.py", base],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("smoke_openclaw falhou ao semear entrada")
    # Aguarda o worker processar a entrada enfileirada.
    time.sleep(8)


def _post_gerar(
    client: httpx.Client, *, base: str, headers: dict[str, str], obra_id: str, data_ref: str
) -> httpx.Response:
    return client.post(
        f"{base}/api/v1/rdo/gerar",
        headers=headers,
        json={"obra_id": obra_id, "data_ref": data_ref},
    )


def main() -> int:
    base = os.environ.get(
        "OBRABOT_API_URL", "https://api-production-8bfb.up.railway.app"
    ).rstrip("/")
    api_key = os.environ.get("OBRABOT_API_KEY", "")
    if not api_key:
        print("OBRABOT_API_KEY não configurada.", file=sys.stderr)
        return 2

    obra_id = os.environ.get("SMOKE_OBRA_ID", "OBRA-SMOKE")
    data_ref = os.environ.get("SMOKE_DATA_REF", _today())
    headers = {"X-Obrabot-API-Key": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=60.0) as client:
        gerar = _post_gerar(
            client, base=base, headers=headers, obra_id=obra_id, data_ref=data_ref
        )
        print(f"POST /rdo/gerar -> {gerar.status_code}")
        if gerar.status_code == 404:
            _seed_entrada_if_needed(base)
            gerar = _post_gerar(
                client, base=base, headers=headers, obra_id=obra_id, data_ref=data_ref
            )
            print(f"POST /rdo/gerar (retry) -> {gerar.status_code}")
        if gerar.status_code == 404:
            print(
                f"Sem entradas para {obra_id} em {data_ref}. "
                "Rode smoke_openclaw antes ou ajuste SMOKE_DATA_REF.",
                file=sys.stderr,
            )
            return 1
        gerar.raise_for_status()
        draft = gerar.json()
        documento_id = draft["documento_id"]
        print(f"Rascunho: {documento_id} ({draft.get('revisao')})")

        finalizar = client.post(
            f"{base}/api/v1/rdo/aprovar-finalizar",
            headers=headers,
            json={
                "documento_id": documento_id,
                "aprovador": "smoke-rdo",
                "comentario": "Smoke E2E GHF-222",
            },
        )
        print(f"POST /rdo/aprovar-finalizar -> {finalizar.status_code}")
        finalizar.raise_for_status()
        result = finalizar.json()

    if result.get("formato") != "pdf":
        print(f"formato inesperado: {result}", file=sys.stderr)
        return 1
    if result.get("status") != "FINALIZADO_VALIDADO":
        print(f"status inesperado: {result}", file=sys.stderr)
        return 1

    print(f"smoke-rdo ({base}): PASS — PDF em {result.get('bucket_uri', '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
