---
name: cronograma
description: Importa atividades de cronograma estruturadas para o backend Obrabot.
---

# Skill: Cronograma

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Comandos Telegram esperados

- `/importar_cronograma OBRA-001`: orientar preparação das atividades e chamar `POST /api/v1/cronograma/importar`.
- Use `codigo_orcamento` nas atividades para vincular ao item de orçamento correspondente.
- Baseline conjunto (orçamento + cronograma): `/validar_baseline` e `/aprovar_baseline` via skill `orcamento`.

## Importar cronograma

```http
POST {OBRABOT_API_URL}/api/v1/cronograma/importar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload (aceita aliases `inicio_planejado`/`fim_planejado` ou `inicio_previsto`/`fim_previsto`):

```json
{
  "obra_id": "OBRA-001",
  "arquivo_id": null,
  "atividades": [
    {
      "codigo": "ATV-001",
      "nome": "Estrutura do pavimento 1",
      "inicio_planejado": "2026-06-01",
      "fim_planejado": "2026-06-15",
      "codigo_orcamento": "03.02.001"
    }
  ]
}
```

## Listar cronograma da obra

```http
GET {OBRABOT_API_URL}/api/v1/cronograma/{obra_id}
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
```

## Validar e aprovar baseline

```http
POST {OBRABOT_API_URL}/api/v1/baseline/validar
POST {OBRABOT_API_URL}/api/v1/baseline/aprovar
```

Não invente datas ou predecessoras. Alteração de baseline exige validação humana.
