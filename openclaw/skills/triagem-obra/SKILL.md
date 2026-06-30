---
name: triagem-obra
description: Classifica entradas de obra (RDO, fotos, áudio, orçamento, cronograma) via backend Obrabot.
---

# Skill: Triagem de Obra

Use `OBRABOT_API_URL` e `OBRABOT_API_KEY`; ver skill `obrabot-api`.

Chame o backend para classificar texto:

```
POST {OBRABOT_API_URL}/api/v1/triagem/classificar
Content-Type: application/json
X-Obrabot-API-Key: ${OBRABOT_API_KEY}

Body: { "texto": "...", "contexto": { "obra_id": "OBRA-001" } }
```

Retorne `tipo_documento`, `confianca`, `resumo` e `acao_sugerida` ao usuário.
