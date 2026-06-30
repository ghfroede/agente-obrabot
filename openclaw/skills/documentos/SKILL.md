---
name: documentos
description: Consulta documentos, resolve entrada sem obra e aprova/reprova documentos no Obrabot.
---

# Skill: Documentos

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Listar obras

```http
GET {OBRABOT_API_URL}/api/v1/obras
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
```

## Criar/atualizar obra

```http
POST {OBRABOT_API_URL}/api/v1/obras
```

Payload:

```json
{
  "id": "OBRA-001",
  "nome": "Obra Exemplo",
  "status": "ativa",
  "metadata_json": {}
}
```

## Resolver obra de uma entrada pendente

```http
POST {OBRABOT_API_URL}/api/v1/entradas/{entrada_id}/resolver-obra
```

Payload:

```json
{
  "obra_id": "OBRA-001"
}
```

## Consultar documento

```http
GET {OBRABOT_API_URL}/api/v1/documentos/{documento_id}
```

## Aprovar ou reprovar documento

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

Aprovação exige autorização humana explícita na conversa.
