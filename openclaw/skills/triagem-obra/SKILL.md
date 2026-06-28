---
name: triagem-obra
description: Classifica entradas de obra (RDO, fotos, áudio, orçamento, cronograma) via backend Obrabot.
---

# Skill: Triagem de Obra

Chame o backend para classificar texto:

```
POST {OBRABOT_API_URL}/api/v1/triagem/classificar
Body: { "texto": "...", "contexto": { "obra_id": "OBRA-001" } }
```

Retorne `tipo_documento`, `confianca`, `resumo` e `acao_sugerida` ao usuário.
