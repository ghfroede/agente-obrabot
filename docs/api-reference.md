# Referência da API — Obrabot

Base URL local: `http://localhost:8000`  
Produção: `https://api-production-8bfb.up.railway.app`

## Autenticação

| Contexto | Mecanismo |
|----------|-----------|
| Rotas protegidas | Header `X-Obrabot-API-Key: <OBRABOT_API_KEY>` |
| `/health` | Sem autenticação |
| `/api/v1/openclaw/telegram-event` | HMAC (`X-OpenClaw-Signature`, `X-OpenClaw-Timestamp`, `X-OpenClaw-Event-Id`) |
| `/admin/*` | Cookie de sessão (login em `/admin/login`) |

Em produção (`APP_ENV=production`), `/docs` e `/openapi.json` estão desabilitados.

---

## Saúde

### `GET /health`

Retorna status de app, PostgreSQL e Redis.

```json
{"status": "ok", "postgres": "ok", "redis": "ok"}
```

---

## Tarefas (ingestão API)

### `POST /tasks`

Cria `Task` + `EntradaBruta` e enfileira processamento. **202 Accepted.**

```json
{
  "input": {
    "message": "Hoje executamos alvenaria no pav 2",
    "obra_id": "OBRA-001",
    "author": "Engenheiro 01"
  }
}
```

### `GET /tasks/{task_id}`

Consulta status e resultado (`queued`, `processing`, `completed`, `failed`).

---

## OpenClaw / Telegram

### `POST /api/v1/openclaw/telegram-event`

Webhook assinado por HMAC. Cria `TelegramMessage` + `EntradaBruta` → **202**.

Payload (exemplo):

```json
{
  "event_id": "evt-unique-id",
  "obra_id": "OBRA-001",
  "telegram": {
    "message_id": 123,
    "date": 1719859200,
    "chat": {"id": -1001234567890, "type": "group"},
    "from": {"id": 1526067084},
    "text": "OBRA-001: concretagem concluída"
  }
}
```

Respostas comuns:

| Status | Significado |
|--------|-------------|
| 202 | Aceito e enfileirado |
| 401 | HMAC inválido ou allowlist |
| 404 | Obra não encontrada (smoke pode tratar como OK de auth) |
| 429 | Rate limit |

---

## Obras

### `GET /api/v1/obras`

Lista obras cadastradas.

### `POST /api/v1/obras`

```json
{"id": "OBRA-001", "nome": "Residencial Aurora"}
```

---

## Contexto Telegram

### `GET /api/v1/telegram-contextos`

Lista mapeamentos chat → obra.

### `POST /api/v1/telegram-contextos`

```json
{
  "chat_id": -1001234567890,
  "thread_id": null,
  "obra_id": "OBRA-001",
  "papel": "engenheiro",
  "status": "ativo"
}
```

---

## Entradas

### `POST /api/v1/entradas/{entrada_id}/resolver-obra`

Resolve entrada `pending_obra` e reenfileira processamento.

```json
{"obra_id": "OBRA-001"}
```

---

## RDO

### `POST /api/v1/rdo/gerar`

Agrega evidências do dia e cria rascunho.

```json
{"obra_id": "OBRA-001", "data_ref": "2026-06-30"}
```

Resposta inclui `documento_id`, `revisao`, `bucket_uri`, `source_entrada_ids`.

**404** se não houver entradas para a data.

### `POST /api/v1/rdo/rascunho`

Rascunho manual (conteúdo já revisado).

### `POST /api/v1/rdo/aprovar-finalizar`

Aprovação humana + PDF final em uma chamada (fluxo Telegram `/aprovar_rdo`).

```json
{
  "documento_id": "uuid",
  "aprovador": "Engenheiro Responsável",
  "comentario": "opcional"
}
```

Resposta: `status=FINALIZADO_VALIDADO`, `formato=pdf`, `bucket_uri`.

### `POST /api/v1/rdo/finalizar`

Finaliza RDO já aprovado (sem criar nova aprovação).

---

## Relatório fotográfico

### `POST /api/v1/fotos/relatorio`

```json
{
  "obra_id": "OBRA-001",
  "periodo_inicio": "2026-06-01",
  "periodo_fim": "2026-06-15"
}
```

Resposta: `documento_id`, `fotos_incluidas`, `revisao`, `bucket_uri` (rascunho HTML).

### `POST /api/v1/fotos/relatorio/aprovar-finalizar`

```json
{
  "documento_id": "uuid",
  "aprovador": "Engenheiro",
  "comentario": "opcional"
}
```

Gera PDF com imagens embutidas em `04_documentos_finais/relatorio_fotografico/`.

---

## Orçamento

### `GET /api/v1/orcamento/{obra_id}`

Lista itens importados.

### `POST /api/v1/orcamento/importar`

```json
{
  "obra_id": "OBRA-001",
  "itens": [
    {
      "codigo": "03.02.001",
      "descricao": "Concretagem de laje",
      "unidade": "m3",
      "quantidade": 10,
      "valor_unitario": 1000
    }
  ]
}
```

Upsert por `obra_id` + `codigo`. Retorna `avisos` para campos incompletos.

---

## Cronograma

### `GET /api/v1/cronograma/{obra_id}`

Lista atividades.

### `POST /api/v1/cronograma/importar`

Aceita aliases de campo:

| Alias aceito | Campo canônico |
|--------------|----------------|
| `descricao` | `nome` |
| `inicio_planejado`, `data_inicio` | `inicio_previsto` |
| `fim_planejado`, `data_fim` | `fim_previsto` |
| `percentual_planejado` | `percentual_concluido` |

```json
{
  "obra_id": "OBRA-001",
  "atividades": [
    {
      "codigo": "ATV-001",
      "nome": "Estrutura pavimento 1",
      "inicio_planejado": "2026-06-01",
      "fim_planejado": "2026-06-15",
      "codigo_orcamento": "03.02.001"
    }
  ]
}
```

---

## Baseline

### `POST /api/v1/baseline/validar`

```json
{"obra_id": "OBRA-001"}
```

Retorna `pronto_para_aprovacao`, `bloqueios`, `avisos`, contagens.

### `POST /api/v1/baseline/aprovar`

Exige baseline pronto (orçamento + cronograma importados).

```json
{
  "obra_id": "OBRA-001",
  "aprovador": "Engenheiro",
  "comentario": "Baseline REV00 aprovado"
}
```

Publica JSON em `07_planejamento/baseline/` e atualiza `obra.metadata_json.baseline`.

---

## Medições

### `POST /api/v1/medicoes`

```json
{
  "obra_id": "OBRA-001",
  "periodo_ref": "2026-06",
  "itens": [
    {
      "codigo": "03.02.001",
      "quantidade_medida": 5.5,
      "valor_medido": 5500
    }
  ]
}
```

Vincula a `orcamento_itens` por `codigo` quando existir.

---

## Aprovações genéricas

### `POST /api/v1/aprovacoes`

Aprova ou reprova documento sem finalizar PDF.

```json
{
  "documento_id": "uuid",
  "aprovado": false,
  "aprovador": "Engenheiro",
  "comentario": "Faltou equipe"
}
```

### `GET /api/v1/documentos/{documento_id}`

Metadados do documento (status, bucket_uri, metadata_json).

---

## Triagem (utilitário)

### `POST /api/v1/triagem/classificar`

Classifica texto sem persistir entrada completa (debug/integração).

### `GET /api/v1/triagem/{triagem_id}`

Consulta triagem persistida.

---

## Painel admin (sessão)

Não usa `X-Obrabot-API-Key`. Principais rotas HTML:

| Rota | Função |
|------|--------|
| `GET /admin/login` | Formulário de login |
| `GET /admin` | Dashboard |
| `GET /admin/obras` | CRUD obras |
| `GET /admin/entradas` | Lista entradas + resolver obra |
| `GET /admin/dia-obra` | Visão do dia + gerar RDO |
| `GET /admin/documentos/{id}` | Detalhe, complementos RDO, finalizar PDF |

---

## Códigos de erro comuns

| HTTP | Causa |
|------|-------|
| 400 | Validação (`ValidationError`, baseline não pronto) |
| 401 | API key ausente/incorreta |
| 403 | Forbidden / allowlist |
| 404 | Recurso não encontrado |
| 429 | Rate limit |
| 500 | Erro interno (ver logs worker/api) |

Erros de domínio retornam `{"detail": "mensagem em português"}`.

---

## Exemplo PowerShell (produção)

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "X-Obrabot-API-Key" = $env:OBRABOT_API_KEY
}

Invoke-RestMethod -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/rdo/gerar" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-SMOKE","data_ref":"2026-06-30"}'
```
