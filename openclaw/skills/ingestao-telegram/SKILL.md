---
name: ingestao-telegram
description: Envia eventos Telegram normalizados para o backend Obrabot.
---

# Skill: Ingestão Telegram

Encaminhe eventos para:

```
POST {OBRABOT_API_URL}/api/v1/openclaw/telegram-event
```

## Headers obrigatórios (HMAC — padrão de produção)

```
Content-Type: application/json
X-OpenClaw-Signature: {hmac_sha256_hex}
X-Timestamp: {iso8601_utc}        # ex.: 2026-06-28T12:00:00Z (janela de ±5 min)
X-Event-Id: {event_id}            # DEVE ser igual ao event_id do corpo
```

`X-OpenClaw-Secret` (segredo estático) é **legado** — use apenas em ambientes sem HMAC.

## Cálculo da assinatura

A string canônica une 5 campos com `\n`, nesta ordem, e é assinada com HMAC-SHA256 usando `OPENCLAW_SHARED_SECRET`:

```
canonical = timestamp + "\n" + event_id + "\n" + method + "\n" + path + "\n" + sha256_hex(body)
signature = hmac_sha256(secret, canonical)   # hex
```

- `method` = `POST`
- `path` = `/api/v1/openclaw/telegram-event`
- `sha256_hex(body)` = SHA-256 (hex) do corpo JSON exatamente como enviado

Pseudocódigo:

```python
import hashlib, hmac, json
body = json.dumps(payload).encode()
body_hash = hashlib.sha256(body).hexdigest()
canonical = "\n".join([timestamp, event_id, "POST", path, body_hash]).encode()
signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
```

> O backend recusa (401) se a assinatura, o timestamp (>5 min) ou o `X-Event-Id` (≠ `payload.event_id`) não baterem. Quando `OPENCLAW_SHARED_SECRET` está vazio no servidor, a verificação é ignorada (somente dev).

## Payload mínimo

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

Reenvio do mesmo `event_id` + mesmo conteúdo retorna o resultado em cache (idempotência).
