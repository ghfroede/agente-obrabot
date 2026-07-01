---
name: orcamento
description: Importa itens de orçamento estruturados para o backend Obrabot.
---

# Skill: Orçamento

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Comandos Telegram esperados

- `/importar_orcamento OBRA-001`: orientar preparação dos itens e chamar `POST /api/v1/orcamento/importar`.
- `/validar_baseline OBRA-001`: chamar `POST /api/v1/baseline/validar`.
- `/aprovar_baseline OBRA-001`: após validação humana, chamar `POST /api/v1/baseline/aprovar`.

## Importar orçamento

```http
POST {OBRABOT_API_URL}/api/v1/orcamento/importar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "arquivo_id": null,
  "itens": [
    {
      "codigo": "03.02.001",
      "descricao": "Concretagem de laje",
      "unidade": "m3",
      "quantidade": 10,
      "valor_unitario": 1000
    }
  ]
}
```

## Listar orçamento da obra

```http
GET {OBRABOT_API_URL}/api/v1/orcamento/{obra_id}
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
```

Não invente código, quantidade ou valor. Se os dados vierem de planilha/PDF, peça validação humana antes de importar.
