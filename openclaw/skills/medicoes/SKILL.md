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

Aliases aceitos pelo backend:

- `periodo_ref`, `periodoRef`, `periodo` ou `competencia`
- `codigo_orcamento`, `codigoOrcamento`, `orcamento_codigo` ou `codigo`
- `quantidade_medida`, `quantidadeMedida`, `quantidade`, `qtd` ou `medido`
- `valor_medido`, `valorMedido` ou `valor`

Quantidade negativa ou item sem orçamento cadastrado deve virar pendência, não lançamento automático. O período usa formato `YYYY-MM`; períodos fechados não aceitam novos lançamentos.

## Fechar período

Use somente depois de validação humana.

```http
POST {OBRABOT_API_URL}/api/v1/medicoes/fechar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "periodo_ref": "2026-06",
  "aprovador": "nome do aprovador",
  "comentario": "opcional"
}
```

O fechamento falha se o período já estiver fechado, se houver item sem orçamento ou quantidade negativa.
