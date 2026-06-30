---
name: cronograma
description: Importa atividades de cronograma estruturadas para o backend Obrabot.
---

# Skill: Cronograma

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Importar cronograma

```http
POST {OBRABOT_API_URL}/api/v1/cronograma/importar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "arquivo_id": null,
  "atividades": [
    {
      "codigo": "ATV-001",
      "descricao": "Estrutura do pavimento 1",
      "inicio_planejado": "2026-06-01",
      "fim_planejado": "2026-06-15",
      "percentual_planejado": 100
    }
  ]
}
```

Não invente datas ou predecessoras. Alteração de baseline exige validação humana.
