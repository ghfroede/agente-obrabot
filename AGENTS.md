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
| LLM | httpx + API OpenAI-compatible |
| Storage | S3-compatible opcional (`src/storage/`) |
| Deploy | Railway (serviços `api` + `worker`) |

## Arquitetura

```
POST /tasks → API (FastAPI) → Redis (fila obrabot) → Worker → run_ceo_pipeline
                ↓                                        ↓
           PostgreSQL                              PostgreSQL + S3 (opcional)
```

### Entry points

| Arquivo | Papel |
|---------|-------|
| `src/api/server.py` | App FastAPI |
| `src/api/routes/tasks.py` | Criação/consulta de tarefas |
| `src/api/routes/health.py` | Healthcheck `/health` |
| `src/worker/index.py` | Worker RQ + `process_task` |
| `src/agent/ceo.py` | Pipeline CEO (triagem → storage → delegação) |
| `src/agent/triagem.py` | Classificação LLM + heurística fallback |
| `src/config/env.py` | Settings via pydantic-settings |
| `src/db/models.py` | `Task`, `Obra` |
| `alembic/` | Migrations |

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

1. Toda entrada deve poder ser persistida no bucket antes do processamento de IA (quando S3 configurado).
2. Toda tarefa gera registro no PostgreSQL (`tasks`).
3. Triagem retorna JSON estruturado (`tipo_documento`, `obra_id`, `pendencias`, etc.).
4. PDF final e publicação em pasta final exigem validação humana (fases futuras).
5. Fonte de verdade: bucket + PostgreSQL — não a resposta da IA.

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
- Não expandir escopo para Telegram/OpenClaw/RDO sem solicitação.

## Mapa rápido de diretórios

```
src/agent/     Lógica de agentes (CEO, triagem)
src/api/       HTTP FastAPI
src/worker/    Jobs RQ
src/db/        Models + sessions
src/storage/   S3
src/config/    Env settings
tests/         pytest
alembic/       Migrations
docs/          Operações e deploy
dev/           Planos internos (ignorar em deploy)
```
