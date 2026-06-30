# AGENTS.md — Obrabot

Instruções para agentes de IA (Cursor, Claude Code, etc.) trabalhando neste repositório.

## O que é este projeto

**Obrabot (Construtora AgentOS)** — agente de gestão documental para construtoras. MVP 1: triagem automática de entradas de engenheiros, persistência auditável e orquestração CEO via pipeline assíncrono.

Roadmap detalhado: `dev/plan-1.md` (não implementar escopo futuro sem pedido explícito).

## Stack

| Camada | Tecnologia |
|--------|------------|
| Runtime | Python 3.11+, [uv](https://docs.astral.sh/uv/) |
| API | FastAPI + Uvicorn (`src/api/`) |
| Worker | RQ + Redis (`src/worker/`) |
| Banco | PostgreSQL + SQLAlchemy async + Alembic |
| LLM | OpenAI SDK (`AsyncOpenAI`), API OpenAI-compatible |
| Storage | S3-compatible opcional (`src/storage/`) |
| Deploy | Railway (serviços `api` + `worker`) |

## Arquitetura

Ingestão **unificada** (Sprint 2): todo canal grava uma `EntradaBruta` antes da IA e enfileira `process_entrada`; o processamento pesado roda no worker.

```
POST /tasks            ┐
POST /api/v1/openclaw  ┘→ API (FastAPI) → cria EntradaBruta → Redis (fila obrabot) → 202
                                ↓                                      ↓
                           PostgreSQL                    Worker → run_entrada_pipeline
                                                              ↓ (raw S3 ANTES da IA)
                                                   S3 + triagem + Documento/Triagem/Auditoria
```

- `/tasks`: cria `Task` + `EntradaBruta(source=api, task_id)`; worker espelha status na `Task` (poll `GET /tasks/:id`).
- OpenClaw: HMAC + idempotência atômica → `EntradaBruta(source=openclaw)` → `202 Accepted` (sem IA no request).
- Núcleo único: `src/services/entrada_service.py`. `run_ceo_pipeline` é legado (job `process_task`).

### Entry points

| Arquivo | Papel |
|---------|-------|
| `src/api/server.py` | App FastAPI (registra todos os routers) |
| `src/api/routes/tasks.py` | `/tasks` — cria Task + EntradaBruta, enfileira |
| `src/api/routes/openclaw.py` | Webhook OpenClaw/Telegram (HMAC, 202) |
| `src/api/routes/health.py` | Healthcheck `/health` |
| `src/api/routes/admin.py` | Painel admin `/admin` (server-rendered, auth por sessão) |
| `src/services/entrada_service.py` | **Núcleo de ingestão unificada** (entrada + fila + pipeline) |
| `src/services/ingestao_service.py` | `ensure_obra`, `save_triagem`, idempotência atômica |
| `src/worker/index.py` | Worker RQ: `process_entrada` (atual) + `process_task` (legado) |
| `src/agent/ceo.py` | `run_ceo_pipeline` (legado, usado por `process_task`) |
| `src/agent/triagem.py` | Classificação LLM + heurística fallback |
| `src/core/security.py` | HMAC OpenClaw (`verify_hmac_signature`) |
| `src/config/env.py` | Settings via pydantic-settings |
| `src/db/models.py` | `Task`, `Obra`, `EntradaBruta`, `IdempotencyKey`, cadeia de documentos |
| `alembic/` | Migrations (head: `005_add_entradas_brutas`) |

## Comandos

```bash
uv sync                    # deps
make dev-api               # API :8000
make dev-worker            # worker RQ
make test                  # pytest
make lint                  # ruff
make typecheck             # mypy (strict)
make db-migrate            # alembic upgrade head
docker compose up -d       # Postgres + Redis local
```

## Convenções de código

- **Imports no topo** do módulo — sem imports inline.
- **Tipagem estrita** — mypy strict em `src/`.
- **Async na API**, sync no worker RQ (`asyncio.run` para pipeline async).
- **Settings** via `get_settings()` — nunca hardcode secrets.
- **Diff mínimo** — reutilize padrões existentes; não refatore fora do escopo.
- **Testes** só quando agregam cobertura real (`tests/`).
- Responder/documentar em **português** quando interagir com o usuário.

## Invariantes de domínio (MVP)

1. Todo canal gera uma `EntradaBruta` no PostgreSQL **antes** de chamar IA; o raw vai ao bucket antes da triagem (quando S3 configurado).
2. Sem IA no caminho do request — processamento pesado vai para a fila RQ (`process_entrada`).
3. Idempotência do webhook é **atômica** (`INSERT ... ON CONFLICT`); reenvio retorna resultado em cache.
4. Triagem retorna JSON estruturado (`tipo_documento`, `obra_id`, `pendencias`, etc.).
5. PDF final e publicação em pasta final exigem validação humana (fases futuras).
6. Fonte de verdade: bucket + PostgreSQL — não a resposta da IA.
7. Nenhuma rota `/admin/*` responde sem sessão válida — o guard `require_admin_session` interrompe via `raise AdminLoginRequired` (Depends que retorna `Response` não interrompe a rota).

## Deploy Railway

- Config por serviço: `railway.api.json`, `railway.worker.json`.
- `railway.json` está no `.gitignore` (cópia local para `railway up`).
- Deploy via GitHub exige config path no dashboard **ou** `RAILPACK_START_CMD` por serviço.
- Docs: `docs/railway-deploy-plan.md`, `docs/operations.md`.

## O que evitar

- Não commitar `.env`, secrets ou `railway.json`.
- Não adicionar `openai-agents-python` no núcleo MVP.
- Não tornar o worker público no Railway.
- Não criar commits/PRs sem pedido explícito do usuário.
- OpenClaw/Telegram **já ativos** (HMAC + 202). Não expandir para novos canais (WhatsApp) nem especialistas (RDO/fotos/orçamento/medição) sem solicitação — ver `dev/plan-2.md`.

## Mapa rápido de diretórios

```
src/agent/     Lógica de agentes (CEO legado, triagem)
src/api/       HTTP FastAPI (routes/)
src/services/  Núcleo de negócio (entrada, ingestão, bucket, openai, etc.)
src/worker/    Jobs RQ (process_entrada, process_task)
src/db/        Models + sessions
src/storage/   S3
src/core/      Constantes, erros, segurança (HMAC)
src/config/    Env settings
tests/         pytest
alembic/       Migrations
docs/          Operações e deploy
dev/           Planos internos (ignorar em deploy)
```
