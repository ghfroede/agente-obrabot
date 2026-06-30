---
name: fotos
description: Gera relatório fotográfico por obra e período usando a API Obrabot.
---

# Skill: Fotos

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

## Comandos Telegram esperados

- `/gerar_relatorio_foto OBRA-001 2026-06-01 2026-06-15`: chamar `POST /api/v1/fotos/relatorio`.
- `/gerar_relatorio_foto OBRA-001 hoje hoje`: resolver datas e gerar relatório do dia.
- `/aprovar_relatorio_foto <documento_id>`: aprovação humana explícita + PDF final via `POST /api/v1/fotos/relatorio/aprovar-finalizar`.
- `/reprovar_relatorio_foto <documento_id> motivo`: chamar `POST /api/v1/aprovacoes` com `aprovado=false`.

## Gerar relatório fotográfico

```http
POST {OBRABOT_API_URL}/api/v1/fotos/relatorio
X-Obrabot-API-Key: ${OBRABOT_API_KEY}
Content-Type: application/json
```

Payload:

```json
{
  "obra_id": "OBRA-001",
  "periodo_inicio": "2026-06-01",
  "periodo_fim": "2026-06-15"
}
```

Resposta esperada: `documento_id`, `revisao`, `fotos_incluidas`, `bucket_uri` (rascunho HTML).

## Aprovar e finalizar em uma chamada

Use para `/aprovar_relatorio_foto <documento_id>` — registra aprovação humana e publica PDF no bucket.

```http
POST {OBRABOT_API_URL}/api/v1/fotos/relatorio/aprovar-finalizar
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

Resposta final: `status=FINALIZADO_VALIDADO`, `bucket_uri`, `formato=pdf`.
