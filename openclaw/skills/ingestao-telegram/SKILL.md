---
name: ingestao-telegram
description: Envia eventos Telegram normalizados para o backend Obrabot.
---

# Skill: Ingestão Telegram

Encaminhe eventos para:

```
POST {OBRABOT_API_URL}/api/v1/openclaw/telegram-event
Header: X-OpenClaw-Secret: {OPENCLAW_SHARED_SECRET}
```

Payload mínimo:

```json
{
  "event_id": "uuid-unico",
  "obra_id": "OBRA-001",
  "telegram": {
    "message_id": 1,
    "chat": { "id": 123, "type": "private" },
    "text": "mensagem do engenheiro"
  }
}
```
