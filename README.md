# Obrabot — Construtora AgentOS

Agente de IA para gestão documental de obras de construção civil. MVP focado em **triagem automática**, **persistência auditável** e **orquestração CEO** para entradas de engenheiros (texto via API e **Telegram via OpenClaw** — integração ativa/experimental, autenticada por HMAC).

## Stack

| Camada | Tecnologia |
|--------|------------|
| Runtime | Python 3.12, [uv](https://docs.astral.sh/uv/) |
| API | FastAPI, Uvicorn |
| Worker | RQ + Redis |
| Banco | PostgreSQL + Alembic |
| LLM | OpenAI-compatible (OpenAI, etc.) |
| Storage | S3-compatible (MEGA S4) — opcional |

## Início rápido

```bash
# 1. Dependências (uv)
uv sync
cp .env.example .env

# 2. Infra local
docker compose up -d

# 3. Migrations
make db-migrate

# 4. API (terminal 1)
make dev-api

# 5. Worker (terminal 2)
make dev-worker
```

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Healthcheck (app, Postgres, Redis) |
| POST | `/tasks` | Cria tarefa de triagem |
| GET | `/tasks/:id` | Consulta status/resultado |
| POST | `/api/v1/openclaw/telegram-event` | Ingestão Telegram via OpenClaw (HMAC + idempotência) |
| GET/POST | `/api/v1/obras` | Lista/cadastra obras reais |
| POST | `/api/v1/entradas/:id/resolver-obra` | Resolve entrada Telegram pendente de obra |
| GET | `/admin` | Painel admin interno (login em `/admin/login`, auth por sessão) |

### Exemplo

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -H "X-Obrabot-API-Key: $OBRABOT_API_KEY" \
  -d '{"input":{"message":"Hoje executamos alvenaria no pav 2","obra_id":"OBRA-001","author":"Engenheiro 01"}}'

curl -H "X-Obrabot-API-Key: $OBRABOT_API_KEY" http://localhost:8000/tasks/<taskId>
```

## Scripts

| Comando | Descrição |
|---------|-----------|
| `uv sync` | Instala dependências (dev incluído) |
| `make dev-api` | API com reload |
| `make dev-worker` | Worker RQ |
| `make test` | pytest |
| `make lint` | ruff |
| `make typecheck` | mypy |
| `make db-migrate` | Alembic upgrade head |
| `make start-api` | Produção (usa `$PORT`) |
| `make start-worker` | Worker produção |

## Variáveis de ambiente

Veja `.env.example`. Obrigatórias em produção:

- `DATABASE_URL` — PostgreSQL (Railway injeta automaticamente)
- `REDIS_URL` — Redis (Railway injeta automaticamente)
- `OBRABOT_API_KEY` — exigida no header `X-Obrabot-API-Key` para rotas HTTP públicas, exceto `/health` e OpenClaw
- `OPENCLAW_SHARED_SECRET` + `OPENCLAW_REQUIRE_HMAC=true` — assinatura HMAC do webhook OpenClaw
- `OPENAI_API_KEY` — para triagem via LLM (sem chave, usa heurística)
- `ADMIN_PASSWORD` + `SESSION_SECRET` — exigidas pelo serviço `api` para o painel `/admin` (ausência derruba a `api` em produção — fail-closed)

Em produção, `/docs`, `/redoc` e `/openapi.json` ficam desabilitados.

Opcionais:

- `S3_*` — persistência bruta no bucket MEGA S4
- `AGENT_SYSTEM_PROMPT`, `OPENAI_MODEL`, `LLM_BASE_URL`

## Arquitetura Railway

```
Cliente HTTP / Telegram (OpenClaw) → API (público) → EntradaBruta → Redis → Worker (privado)
                                          ↓                                       ↓
                                     PostgreSQL                          raw S3 → triagem IA
                                          ↓                                       ↓
                                     MEGA S4 (opcional)            Documento/Triagem/Auditoria
```

Ingestão unificada: todo canal grava uma `EntradaBruta` e responde rápido (`202`); o worker faz storage + triagem fora do request. Detalhes em [AGENTS.md](AGENTS.md) e `dev/plan-2.md`.

Entradas Telegram sem obra clara ficam com `status=pending_obra` e não geram documento oficial até que uma obra cadastrada seja confirmada.

Documentação detalhada: `docs/railway-deploy-plan.md`, `docs/operations.md`, `docs/storage-taxonomy.md`, `docs/guia-engenheiro.md` e [`AGENTS.md`](AGENTS.md) (instruções para agentes de IA).

## Roadmap

Estabilização e evolução em `dev/plan-2.md`:

- ✅ **Sprint 1** — main estável: HMAC com `event_id`, idempotência atômica, ordem S3-antes-da-IA, testes
- ✅ **Sprint 2** — ingestão unificada (`EntradaBruta`); `/tasks` e OpenClaw no mesmo fluxo (202 + fila RQ)
- ✅ **Sprint 3** — Telegram real: texto, foto e áudio (worker baixa mídia → `Arquivo`/`Foto`/`AudioTranscricao` + visão/transcrição; resposta de status opt-in)
- ⏳ **Sprint 4** — RDO operacional com aprovação humana
- ⏳ **Sprint 5** — relatório fotográfico
- ⏳ **Sprint 6** — orçamento, cronograma e medição

## Licença

MIT — veja [LICENSE](LICENSE).
