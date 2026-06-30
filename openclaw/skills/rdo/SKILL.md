---
name: rdo
description: Cria rascunhos, aprova e finaliza RDO usando a API Obrabot.
---

# Skill: RDO

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Comandos Telegram esperados

- `/gerar_rdo OBRA-001 hoje`: resolver a data, chamar `POST /api/v1/rdo/gerar` e devolver o `documento_id`.
- `/aprovar_rdo <documento_id>`: confirmar aprovação humana explícita e chamar `POST /api/v1/rdo/aprovar-finalizar`.
- `/reprovar_rdo <documento_id> motivo`: chamar `POST /api/v1/aprovacoes` com `aprovado=false`.
- `/finalizar_rdo <documento_id>`: usar apenas quando o RDO já estiver aprovado; chamar `POST /api/v1/rdo/finalizar`.

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
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
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

## Aprovar e finalizar RDO em uma chamada

Use este caminho para o comando Telegram `/aprovar_rdo <documento_id>`, pois ele registra a aprovação humana e publica o PDF final no bucket sem exigir duas chamadas do OpenClaw.

```http
POST {OBRABOT_API_URL}/api/v1/rdo/aprovar-finalizar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "documento_id": "uuid",
  "aprovador": "nome do aprovador",
  "comentario": "opcional"
}
```

Só use quando a conversa tiver aprovação humana explícita para aquele `documento_id`. A resposta final contém `status=FINALIZADO_VALIDADO`, `bucket_uri`, `formato=pdf` e dados da aprovação.

## Finalizar RDO

```http
POST {OBRABOT_API_URL}/api/v1/rdo/finalizar
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
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
