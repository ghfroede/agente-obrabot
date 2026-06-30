---
name: fotos
description: Gera relatório fotográfico por obra e período usando a API Obrabot.
---

# Skill: Fotos

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

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

Resposta esperada: documento de rascunho com quantidade de fotos incluídas. PDF final depende de aprovação humana.
