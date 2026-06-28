# Plano de deploy Railway — Obrabot

## Resumo do agente

**Obrabot (Construtora AgentOS)** é um agente de gestão documental para construtoras. Recebe entradas de engenheiros (texto e mídia — foto/áudio/documento — via API e Telegram/OpenClaw), grava uma `EntradaBruta` e enfileira o processamento, classifica automaticamente (triagem), persiste evidências no bucket S3-compatible e orquestra delegação a agentes especialistas (RDO, fotos, orçamento, etc.).

## Requisitos assumidos

- Usuários finais: 3 engenheiros de obra (organização interna de confiança)
- Entrada: texto via API HTTP e Telegram/OpenClaw (HMAC); mídia (foto/áudio/documento) baixada no worker
- Saída MVP: classificação estruturada + metadados + delegação ao especialista
- Tarefas podem levar segundos a minutos (LLM + storage)
- Validação humana obrigatória para documentos finais (fases futuras)
- Fonte de verdade: bucket + PostgreSQL + auditoria (não a IA)

## Stack escolhida

**Python + FastAPI** (em vez de Node.js padrão do prompt):

| Critério | Decisão |
|----------|---------|
| Domínio | OCR, PDF, parsers Excel, transcrição — ecossistema Python maduro |
| Plano-01 | Recomenda explicitamente Python FastAPI |
| Worker | RQ (Redis Queue) — simples e robusto para MVP |
| ORM/Migrations | SQLAlchemy + Alembic |
| LLM | httpx + API OpenAI-compatible |
| Gerenciador | [uv](https://docs.astral.sh/uv/) + `uv.lock` |

## Arquitetura Railway

```
┌─────────────┐     ┌─────────┐     ┌──────────────┐
│  api        │────▶│  redis  │────▶│  worker      │
│  (público)  │     │ (fila)  │     │  (privado)   │
└──────┬──────┘     └─────────┘     └──────┬───────┘
       │                                      │
       └──────────────┬───────────────────────┘
                      ▼
               ┌─────────────┐
               │  postgres   │
               └─────────────┘
```

### Serviços

| Serviço | Tipo | Público | Start command |
|---------|------|---------|---------------|
| `api` | App (repo) | Sim | `.venv/bin/python -m uvicorn src.api.server:app --host 0.0.0.0 --port $PORT` |
| `worker` | App (repo) | Não | `.venv/bin/python -m src.worker.index` |
| `postgres` | Template Railway | Não | — |
| `redis` | Template Railway | Não | — |

## Templates Railway usados

| Template | Motivo |
|----------|--------|
| `postgres` | Estado persistente: tarefas, obras, futuras tabelas do plano |
| `redis` | Fila RQ entre API e worker; retries e coordenação |

**Não** usamos template de app genérico — o código do agente foi criado do zero neste repositório.

## Por que Postgres e Redis

- **Postgres**: tarefas assíncronas precisam de status/resultado consultável; roadmap inclui obras, documentos, medições, RAG (pgvector futuro)
- **Redis**: padrão oficial Railway para agent workers ([AI Agent Workers guide](https://docs.railway.com/guides/ai-agent-workers)); tarefas LLM não cabem em HTTP síncrono

## Config as Code

Dois arquivos separados (mesmo repo, serviços diferentes):

- `railway.api.json` — build, pre-deploy migration, healthcheck `/health`
- `railway.worker.json` — worker always-on, restart ALWAYS

Configure cada serviço no dashboard Railway para apontar ao arquivo correto (Settings → Config-as-code), **ou** defina `RAILPACK_START_CMD` por serviço (necessário para deploy via GitHub se o config path não estiver configurado):

```bash
railway variable set RAILPACK_START_CMD=".venv/bin/python -m uvicorn src.api.server:app --host 0.0.0.0 --port \$PORT" --service api
railway variable set RAILPACK_START_CMD=".venv/bin/python -m src.worker.index" --service worker
```

`railway.json` fica no `.gitignore` (cópia local para `railway up`); deploys pelo GitHub não o enxergam. Sem config path ou `RAILPACK_START_CMD`, o Railpack falha com *No start command detected* porque o FastAPI está em `src/api/server.py`.

## Build / Start

```bash
# Build (ambos serviços)
pip install uv && uv sync --frozen --no-dev

# API — pre-deploy
.venv/bin/alembic upgrade head

# API — start
.venv/bin/python -m uvicorn src.api.server:app --host 0.0.0.0 --port $PORT

# Worker — start
.venv/bin/python -m src.worker.index
```

## Variáveis de ambiente

| Variável | Serviço | Obrigatória |
|----------|---------|-------------|
| `DATABASE_URL` | api, worker | Sim (referência Postgres) |
| `REDIS_URL` | api, worker | Sim (referência Redis) |
| `OPENAI_API_KEY` | worker | Recomendada (heurística sem chave) |
| `OPENCLAW_SHARED_SECRET` | api | **Sim em produção** (segredo usado para HMAC do webhook) |
| `OPENCLAW_REQUIRE_HMAC` | api | **Sim em produção** (`true`; `X-OpenClaw-Secret` é legado apenas para dev sem HMAC obrigatório) |
| `TELEGRAM_BOT_TOKEN` | worker | Recomendada (download de mídia foto/áudio/documento via getFile) |
| `TELEGRAM_REPLY_ENABLED` | worker | Não (default `false`; `true` ativa resposta de status ao engenheiro) |
| `TELEGRAM_API_BASE` | worker | Não (default `https://api.telegram.org`) |
| `OPENAI_MODEL` | worker | Não (default: gpt-4o-mini) |
| `LLM_BASE_URL` | worker | Não |
| `AGENT_NAME` | worker | Não |
| `AGENT_SYSTEM_PROMPT` | worker | Não |
| `S3_ENDPOINT_URL` | worker | Não (MEGA S4) |
| `S3_ACCESS_KEY_ID` | worker | Não |
| `S3_SECRET_ACCESS_KEY` | worker | Não |
| `S3_BUCKET_NAME` | worker | Não |
| `PORT` | api | Sim (Railway injeta) |
| `RAILPACK_START_CMD` | api, worker | Sim (deploy GitHub sem config path) |

## Comandos de deploy

```bash
# Verificar CLI
railway --version
railway whoami

# Setup agent (Cursor)
railway setup agent -y

# Novo projeto
railway init --name obrabot

# Adicionar databases (template oficial)
railway add --database postgres --json
railway add --database redis --json

# Serviços app
railway add --service api --json
railway add --service worker --json

# Deploy por serviço
railway up -s api --detach -m "Deploy API"
railway up -s worker --detach -m "Deploy worker"

# Validar
railway status --json
curl https://<api-domain>/health
```

## Checklist de validação pós-deploy

- [ ] `railway status` mostra serviços healthy
- [ ] Logs API sem crash loop
- [ ] Logs worker sem crash loop
- [ ] `GET /health` retorna 200 com postgres e redis ok
- [ ] `POST /tasks` retorna `202` + taskId
- [ ] `GET /tasks/:id` evolui queued → processing → completed
- [ ] `POST /api/v1/openclaw/telegram-event` (com HMAC válido) retorna `202`
- [ ] `OPENCLAW_SHARED_SECRET` definido no serviço `api`
- [ ] Migrations executadas (pre-deploy API)
- [ ] Worker sem domínio público
- [ ] API com domínio HTTPS Railway
- [ ] Secrets não aparecem nos logs

## Limitações conhecidas

- OpenClaw/Telegram **ativo** para texto e mídia (foto/áudio/documento; download no worker — Sprint 3). Resposta de status ao engenheiro é opt-in (`TELEGRAM_REPLY_ENABLED`)
- HMAC é obrigatório em produção; `X-OpenClaw-Secret` é aceito apenas como legado em desenvolvimento sem HMAC obrigatório
- Triagem heurística quando `OPENAI_API_KEY` ausente
- S3 opcional — sem credenciais, entrada bruta vai ao bucket local (`.local-bucket`)
- PDF/RDO/aprovação humana: Sprint 4+
- pgvector/RAG: futuro

## Referências Railway consultadas

- [AI Agent Workers](https://docs.railway.com/guides/ai-agent-workers)
- [Config as Code Reference](https://docs.railway.com/config-as-code/reference)
- [Start Command](https://docs.railway.com/deployments/start-command)
