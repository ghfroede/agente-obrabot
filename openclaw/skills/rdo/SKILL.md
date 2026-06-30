---
name: rdo
description: Cria rascunhos, aprova e finaliza RDO usando a API Obrabot.
---

# Skill: RDO

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Gerar RDO do dia

Use este caminho para operação normal. O backend agrega as evidências persistidas do dia e cria o rascunho.

```http
POST {OBRABOT_API_URL}/api/v1/rdo/gerar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "data_ref": "2026-06-29"
}
```

Resposta inclui `documento_id`, `revisao`, `bucket_uri`, `source_entrada_ids` e `source_arquivo_ids`.

## Criar rascunho manual

```http
POST {OBRABOT_API_URL}/api/v1/rdo/rascunho
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "data_ref": "2026-06-29",
  "conteudo": {
    "servicos": [],
    "ocorrencias": [],
    "equipe": [],
    "observacoes": ""
  }
}
```

Use o rascunho manual apenas quando o conteúdo já foi revisado fora do agregador.

## Aprovar documento

```http
POST {OBRABOT_API_URL}/api/v1/aprovacoes
```

Payload:

```json
{
  "documento_id": "uuid",
  "aprovado": true,
  "aprovador": "nome do aprovador",
  "comentario": "opcional"
}
```

## Finalizar RDO

```http
POST {OBRABOT_API_URL}/api/v1/rdo/finalizar
```

Payload:

```json
{
  "documento_id": "uuid",
  "aprovador": "nome do aprovador",
  "comentario": "opcional"
}
```

Finalizar só depois de aprovação humana explícita.
