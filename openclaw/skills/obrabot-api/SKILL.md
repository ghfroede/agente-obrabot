---
name: obrabot-api
description: Contratos comuns para chamar a API FastAPI do Obrabot a partir do OpenClaw.
---

# Skill: Obrabot API

Use esta skill como base para todas as chamadas HTTP ao backend Obrabot.

## Ambiente

- `OBRABOT_API_URL`: URL base da API, sem barra final.
- `OBRABOT_API_KEY`: chave para rotas protegidas.
- `OPENCLAW_SHARED_SECRET`: segredo do webhook HMAC `/api/v1/openclaw/telegram-event`.

## Headers

Rotas protegidas (exceto `/health` e OpenClaw):

```http
Content-Type: application/json
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
```

## Índice de rotas por domínio

| Domínio | Rotas | Skill |
|---------|-------|-------|
| RDO | `POST /api/v1/rdo/gerar`, `/aprovar-finalizar` | `rdo` |
| Fotos | `POST /api/v1/fotos/relatorio`, `/aprovar-finalizar` | `fotos` |
| Orçamento | `GET/POST /api/v1/orcamento/...` | `orcamento` |
| Cronograma | `GET/POST /api/v1/cronograma/...` | `cronograma` |
| Baseline | `POST /api/v1/baseline/validar`, `/aprovar` | `orcamento` |
| Medições | `POST /api/v1/medicoes`, `/fechar` | `medicoes` |
| Obras | `GET/POST /api/v1/obras` | — |
| Aprovações | `POST /api/v1/aprovacoes` | `documentos` |

Referência completa: repositório `docs/api-reference.md`.

## Regras

- Nunca exponha segredos na resposta ao usuário.
- Não acesse banco, Redis, bucket ou Railway diretamente.
- `401` → chave API ausente/inválida.
- `404` → recurso ausente; não invente dados.
- `202` → processamento assíncrono (ingestão).
- Documentos finais (PDF) só após aprovação humana explícita.
