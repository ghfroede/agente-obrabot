# Operações — Obrabot

## Rodar localmente

```bash
docker compose up -d
cp .env.example .env
uv sync
make db-migrate
make dev-api    # terminal 1
make dev-worker # terminal 2
```

## Executar migrations

```bash
# Local
make db-migrate

# Ou diretamente
uv run alembic upgrade head

# Produção (Railway)
# Configurado em railway.api.json preDeployCommand
```

## Ver logs

```bash
# Local — stdout dos processos dev-api / dev-worker

# Railway
railway logs --service api --lines 200
railway logs --service worker --lines 200
railway logs --service OpenClaw --lines 200
```

## Redeployar

```bash
railway up -s api --detach -m "Redeploy API"
railway up -s worker --detach -m "Redeploy worker"
railway service redeploy OpenClaw

# Verificar deployment
railway deployment list --json
```

## OpenClaw no Railway

O serviço `OpenClaw` roda no mesmo projeto Railway, com domínio HTTPS próprio, proxy HTTP na porta `8080` e volume persistente montado em `/data`.

Variáveis esperadas no serviço `OpenClaw`:

- `OBRABOT_API_URL=https://<api-domain>`
- `OPENCLAW_SHARED_SECRET` referenciando `api.OPENCLAW_SHARED_SECRET`
- `TELEGRAM_BOT_TOKEN` referenciando `worker.TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY` referenciando `worker.OPENAI_API_KEY`
- `OPENCLAW_STATE_DIR=/data/.openclaw`
- `OPENCLAW_WORKSPACE_DIR=/data/workspace`
- `OPENCLAW_GATEWAY_PORT=8080`
- `SETUP_PASSWORD` e `OPENCLAW_GATEWAY_TOKEN` gerados no Railway

Não configure `DATABASE_URL`, `REDIS_URL` nem `S3_*` no OpenClaw. Ele deve chamar apenas a API pública do Obrabot com HMAC.

Setup inicial:

```bash
# Acesse pelo navegador:
https://<openclaw-domain>/setup
```

O wizard é protegido por `SETUP_PASSWORD`, disponível nas variáveis do serviço `OpenClaw` no dashboard Railway. Não copie esse segredo para arquivos do repositório.

Validação do contrato OpenClaw → Obrabot:

```bash
railway run --service api uv run python scripts/smoke_openclaw.py https://<api-domain>
```

Esse smoke usa `OPENCLAW_SHARED_SECRET` e a allowlist Telegram do serviço `api`, assina o payload com HMAC e espera `202 Accepted`. O worker deve concluir `process_entrada` logo depois.

## Escalar worker

1. Railway Dashboard → serviço `worker` → Settings → Replicas
2. Ou horizontal scaling na documentação Railway
3. Todos os replicas consomem a mesma fila Redis `obrabot`

## Alterar modelo LLM

```bash
railway variable set OPENAI_MODEL=gpt-4o --service worker
railway variable set LLM_BASE_URL=https://api.openai.com/v1 --service worker
```

Reinicie/redeploy o worker após alterar variáveis.

## Configurar secrets

```bash
# Nunca commitar .env com valores reais
railway variable set OBRABOT_API_KEY=... --service api
railway variable set OPENAI_API_KEY=sk-... --service worker
railway variable set OPENAI_API_KEY=sk-... --service api  # se necessário

# HMAC OpenClaw — OBRIGATÓRIO em produção
railway variable set OPENCLAW_SHARED_SECRET=... --service api
railway variable set OPENCLAW_REQUIRE_HMAC=true --service api

# OpenClaw deve referenciar o mesmo segredo do api, não duplicar manualmente
railway variable set OBRABOT_API_URL=https://<api-domain> --service OpenClaw

# S3 / MEGA S4
railway variable set S3_ENDPOINT_URL=... --service worker
railway variable set S3_ACCESS_KEY_ID=... --service worker
railway variable set S3_SECRET_ACCESS_KEY=... --service worker
railway variable set S3_BUCKET_NAME=bucket-construtora --service worker

# RQ worker — ajuste se LLM/S3 demorarem mais que o padrão
railway variable set RQ_JOB_TIMEOUT_SECONDS=900 --service api
railway variable set RQ_RETRY_MAX=3 --service api
railway variable set RQ_RETRY_INTERVALS_SECONDS=30,120,300 --service api
```

Referencie `DATABASE_URL` e `REDIS_URL` das variáveis dos serviços Postgres/Redis no dashboard.

Com `APP_ENV=production` ou `NODE_ENV=production`, a API não publica `/docs`, `/redoc` nem `/openapi.json`.

## Painel admin interno

Painel server-rendered no serviço `api`, em `/admin` (login em `/admin/login`). Prod: `https://api-production-8bfb.up.railway.app/admin`.

Variáveis **obrigatórias** no serviço `api` (ausência derruba a `api` — fail-closed):

- `ADMIN_PASSWORD` — senha de login (comparada com `hmac.compare_digest`)
- `SESSION_SECRET` — chave do cookie de sessão assinado

```bash
railway variables --service api --set "ADMIN_PASSWORD=..."
railway variables --service api --set "SESSION_SECRET=..."
```

Login tem rate-limit por IP (`ADMIN_LOGIN_MAX_PER_MINUTE`, padrão `5`). Para rotacionar a senha, basta atualizar a variável e redeployar:

```bash
railway variables --service api --set "ADMIN_PASSWORD=..."
```

## Cadastrar obras iniciais

Antes de usar o Telegram em operação real, cadastre pelo menos uma obra. As rotas de obras são administrativas e exigem `X-Obrabot-API-Key`; portanto, `OBRABOT_API_KEY` precisa estar definida no serviço `api`.

```bash
railway variable set OBRABOT_API_KEY=... --service api
```

Exemplo em PowerShell:

```powershell
$env:OBRABOT_API_KEY="..."
$headers = @{
  "Content-Type" = "application/json"
  "X-Obrabot-API-Key" = $env:OBRABOT_API_KEY
}

Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/obras" `
  -Headers $headers `
  -Body '{"id":"OBRA-001","nome":"Nome da Obra"}'

Invoke-RestMethod `
  -Method Get `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/obras" `
  -Headers $headers
```

Também é possível usar o script operacional:

```bash
OBRABOT_API_URL=https://api-production-8bfb.up.railway.app \
OBRABOT_API_KEY=... \
uv run python scripts/seed_obras.py OBRA-001 "Nome da Obra"
```

Enquanto houver apenas uma obra operacional, cadastre também um contexto Telegram para que o backend resolva a obra mesmo quando o OpenClaw não preencher `obra_id`.

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/telegram-contextos" `
  -Headers $headers `
  -Body '{"chat_id":-1001234567890,"obra_id":"OBRA-001","papel":"engenheiro","status":"ativo"}'
```

Para supergrupos com tópicos, preencha `thread_id`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/telegram-contextos" `
  -Headers $headers `
  -Body '{"chat_id":-1001234567890,"thread_id":42,"obra_id":"OBRA-001","papel":"engenheiro","status":"ativo"}'
```

Ordem de resolução de obra no webhook:

1. `obra_id` vindo do payload OpenClaw.
2. Prefixo no texto/caption, como `OBRA-001: concretagem concluída`.
3. Contexto ativo por `chat_id + thread_id`.
4. Contexto ativo raiz por `chat_id`.
5. `pending_obra` quando nada resolver.

Quando uma mensagem chegar sem obra clara, o webhook retorna `status=pending_obra`, salva `EntradaBruta`/`TelegramMessage` sem gerar documento oficial e lista as obras ativas. Após confirmação humana, resolva a pendência:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/entradas/<entrada_id>/resolver-obra" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001"}'
```

Essa chamada vincula a entrada à obra e enfileira o processamento assíncrono.

## Gerar RDO do dia

Depois que as entradas do dia estiverem processadas, gere um rascunho de RDO a partir das evidências persistidas:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/rdo/gerar" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","data_ref":"2026-06-29"}'
```

O backend agrega `EntradaBruta`, `Triagem`, `Arquivo`, `Foto` e `AudioTranscricao` por `obra_id + data_ref`, gera o conteúdo estruturado e chama o fluxo existente de rascunho. O documento gerado guarda `source_entrada_ids`, `source_arquivo_ids` e `campos_editaveis` em `metadata_json` para revisão humana antes de aprovação/finalização.

## Estrutura de dados e bucket

O pipeline mantém rastreabilidade explícita entre `EntradaBruta`, `Arquivo`, `Documento` e `Triagem` por `entrada_id`. A migration `008_link_entries_and_operational_metadata` adiciona esses vínculos, além de `data_ref` e `metadata_json` em `entradas_brutas`. A migration `009_add_telegram_contextos` adiciona o mapeamento canônico de Telegram para obra.

Após deploy do backend que contém essa migration, aplique:

```bash
railway run --service api uv run alembic upgrade head
```

A organização do MEGA S4/S3 está documentada em `docs/storage-taxonomy.md`. O guia de uso para o engenheiro está em `docs/guia-engenheiro.md`.

## Diagnosticar erros comuns

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| `/health` 503 postgres | `DATABASE_URL` incorreta ou migration pendente | Verificar referência + `alembic upgrade head` |
| `/health` 503 redis | `REDIS_URL` incorreta | Referenciar Redis service |
| Rotas HTTP retornam `401` | `X-Obrabot-API-Key` ausente/incorreto | Enviar header com `OBRABOT_API_KEY`; `/health` e OpenClaw não usam esse header |
| Rotas HTTP retornam `500` com `OBRABOT_API_KEY` | Variável ausente na `api` | Definir `OBRABOT_API_KEY` no serviço `api` |
| Task / `EntradaBruta` stuck em `queued`/`received` | Worker offline | Logs worker, verificar Redis |
| OpenClaw responde `202` mas nada acontece | Worker offline / fila parada | Ver `EntradaBruta.status` no banco + logs worker |
| Task `failed` ou `EntradaBruta.status=failed` | LLM timeout ou S3 error | Ver `error` em `GET /tasks/:id` / logs worker |
| OpenClaw `401` | HMAC/timestamp/`X-Event-Id` inválido ou uso de `X-OpenClaw-Secret` em produção | Conferir assinatura canônica e relógio (±5 min) |
| OpenClaw `/setup` retorna `401` | Wizard protegido | Usar `SETUP_PASSWORD` do serviço `OpenClaw` no Railway |
| OpenClaw `configured: false` nos logs | Setup inicial ainda não concluído | Acessar `/setup` e finalizar pareamento/configuração |
| Crash loop API | Porta errada | Usar `$PORT`, host `0.0.0.0` |
| Worker SIGTERM | Deploy rolling | Normal; RQ re-enfileira job não ack |

## Graceful shutdown

O worker registra handlers para SIGTERM/SIGINT (Railway envia SIGTERM em deploys). Jobs em processamento devem completar ou falhar com status `failed` no banco.

## Backup

- Postgres: backups gerenciados pelo Railway (ver docs PostgreSQL Railway)
- Bucket MEGA S4: política de versionamento REV00/REV01 no app (plano-01)
