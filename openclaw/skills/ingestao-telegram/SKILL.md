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
X-OpenClaw-Timestamp: {iso8601_utc}        # ex.: 2026-06-28T12:00:00Z (janela de ±5 min)
X-OpenClaw-Event-Id: {event_id}            # DEVE ser igual ao event_id do corpo
```

Headers legados aceitos: `X-Timestamp`, `X-Event-Id`. `X-OpenClaw-Secret` (segredo estático) é **legado** — use apenas em desenvolvimento sem HMAC obrigatório.

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

> O backend recusa (401) se a assinatura, o timestamp (>5 min) ou o `X-Event-Id` (≠ `payload.event_id`) não baterem. Quando `OPENCLAW_REQUIRE_HMAC=true` ou `APP_ENV=production`, `OPENCLAW_SHARED_SECRET` vazio falha fechado.

## Payload mínimo

Quando a obra for conhecida, envie `obra_id` com uma obra previamente cadastrada no backend:

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

Se a obra não estiver clara, envie o evento sem `obra_id`. O backend salvará a entrada como `pending_obra`, não chamará IA, não criará documento oficial e retornará uma mensagem com as obras ativas para confirmação humana.

Reenvio do mesmo `event_id` + mesmo conteúdo retorna o resultado em cache (idempotência).

## Mídia (foto, áudio, documento)

O mesmo endpoint aceita mídia: inclua em `telegram` os campos nativos do Telegram — `photo` (lista de `PhotoSize`), `voice`, `audio` ou `document`, cada um com seu `file_id`. O worker baixa o binário (`getFile` → download), grava `Arquivo` + `Foto`/`AudioTranscricao`, roda visão/transcrição e enriquece a triagem (a foto/áudio viram contexto do texto classificado).

```json
{
  "event_id": "uuid-unico",
  "obra_id": "OBRA-001",
  "telegram": {
    "message_id": 2,
    "chat": { "id": 123, "type": "private" },
    "caption": "concretagem pilar P3",
    "photo": [{ "file_id": "AgAC...", "file_size": 90210 }]
  }
}
```

Requer `TELEGRAM_BOT_TOKEN` no worker. Falha ao baixar uma mídia não derruba a entrada (o raw já é persistido); o erro fica registrado na mídia.

## Resposta

`202 Accepted` com:

- `{ "status": "queued", "entrada_id": "...", "event_id": "...", "obra_id": "..." }` quando a obra existe e o processamento foi enfileirado.
- `{ "status": "pending_obra", "entrada_id": "...", "obras_disponiveis": [...], "mensagem": "..." }` quando falta obra ou o `obra_id` informado não está cadastrado.

Para resolver uma pendência, chame a API administrativa:

```
POST {OBRABOT_API_URL}/api/v1/entradas/{entrada_id}/resolver-obra
Header: X-Obrabot-API-Key: {OBRABOT_API_KEY}
Body: { "obra_id": "OBRA-001" }
```

A triagem roda de forma assíncrona no worker — não espere o resultado da classificação na resposta do webhook.
