#!/usr/bin/env python3
"""Smoke E2E de orçamento + cronograma + baseline validado.

Uso Railway:
  railway run --service api uv run python scripts/smoke_orcamento.py
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

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
    headers = {"X-Obrabot-API-Key": api_key, "Content-Type": "application/json"}
    hoje = _today()
    fim = (datetime.now(UTC).date() + timedelta(days=14)).isoformat()

    with httpx.Client(timeout=60.0) as client:
        orc = client.post(
            f"{base}/api/v1/orcamento/importar",
            headers=headers,
            json={
                "obra_id": obra_id,
                "itens": [
                    {
                        "codigo": "03.02.001",
                        "descricao": "Concretagem de laje — smoke",
                        "unidade": "m3",
                        "quantidade": 12,
                        "valor_unitario": 850,
                    },
                    {
                        "codigo": "04.01.010",
                        "descricao": "Alvenaria estrutural — smoke",
                        "unidade": "m2",
                        "quantidade": 40,
                        "valor_unitario": 120,
                    },
                ],
            },
        )
        print(f"POST /orcamento/importar -> {orc.status_code}")
        orc.raise_for_status()

        cron = client.post(
            f"{base}/api/v1/cronograma/importar",
            headers=headers,
            json={
                "obra_id": obra_id,
                "atividades": [
                    {
                        "codigo": "ATV-SMOKE-01",
                        "nome": "Estrutura pavimento térreo",
                        "inicio_planejado": hoje,
                        "fim_planejado": fim,
                        "codigo_orcamento": "03.02.001",
                    },
                    {
                        "codigo": "ATV-SMOKE-02",
                        "nome": "Alvenaria bloco A",
                        "inicio_previsto": hoje,
                        "fim_previsto": fim,
                        "codigo_orcamento": "04.01.010",
                    },
                ],
            },
        )
        print(f"POST /cronograma/importar -> {cron.status_code}")
        cron.raise_for_status()

        validar = client.post(
            f"{base}/api/v1/baseline/validar",
            headers=headers,
            json={"obra_id": obra_id},
        )
        print(f"POST /baseline/validar -> {validar.status_code}")
        validar.raise_for_status()
        report = validar.json()
        if not report.get("pronto_para_aprovacao"):
            print(f"baseline não pronto: {report}", file=sys.stderr)
            return 1

        aprovar = client.post(
            f"{base}/api/v1/baseline/aprovar",
            headers=headers,
            json={
                "obra_id": obra_id,
                "aprovador": "smoke-orcamento",
                "comentario": "Smoke E2E GHF-226",
            },
        )
        print(f"POST /baseline/aprovar -> {aprovar.status_code}")
        aprovar.raise_for_status()
        result = aprovar.json()

    if result.get("status") != "validado":
        print(f"status inesperado: {result}", file=sys.stderr)
        return 1
    if not result.get("bucket_uri"):
        print(f"sem bucket_uri: {result}", file=sys.stderr)
        return 1

    print(f"smoke-orcamento ({base}): PASS — baseline em {result['bucket_uri']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
