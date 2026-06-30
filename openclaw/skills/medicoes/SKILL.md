---
name: medicoes
description: Registra medições de obra usando a API Obrabot.
---

# Skill: Medições

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Registrar medição

```http
POST {OBRABOT_API_URL}/api/v1/medicoes
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "periodo_ref": "2026-06",
  "itens": [
    {
      "codigo_orcamento": "03.02.001",
      "descricao": "Concretagem de laje",
      "quantidade": 5,
      "unidade": "m3",
      "observacoes": "medição parcial"
    }
  ]
}
```

Quantidade negativa ou item sem referência deve virar pendência, não lançamento automático.
