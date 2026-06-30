---
name: obrabot-api
description: Contratos comuns para chamar a API FastAPI do Obrabot a partir do OpenClaw.
---

# Skill: Obrabot API

Use esta skill como base para todas as chamadas HTTP ao backend Obrabot.

## Ambiente

- `OBRABOT_API_URL`: URL base da API, sem barra final.
- `OBRABOT_API_KEY`: chave para rotas protegidas.
- `OPENCLAW_SHARED_SECRET`: segredo usado apenas no webhook HMAC `/api/v1/openclaw/telegram-event`.

## Headers

Rotas protegidas, exceto `/health` e `/api/v1/openclaw/telegram-event`, exigem:

```http
Content-Type: application/json
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
```

O webhook OpenClaw usa HMAC próprio e não usa `X-Obrabot-API-Key`.

## Regras

- Nunca exponha valores de segredo em resposta ao usuário.
- Não chame banco, Redis, bucket S3 ou Railway diretamente em fluxo operacional.
- Se a API retornar `401`, pare e reporte "chave da API ausente/inválida".
- Se a API retornar `404`, reporte o recurso ausente sem criar dados por conta própria.
- Se a API retornar `202`, informe que o processamento ficou assíncrono.
