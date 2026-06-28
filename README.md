# Obrabot — Construtora AgentOS

Agente de IA para gestão documental de obras de construção civil. MVP focado em **triagem automática**, **persistência auditável** e **orquestração CEO** para entradas de engenheiros (texto, futuro Telegram/OpenClaw).

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

### Exemplo

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"input":{"message":"Hoje executamos alvenaria no pav 2","obra_id":"OBRA-001","author":"Engenheiro 01"}}'

curl http://localhost:8000/tasks/<taskId>
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
- `OPENAI_API_KEY` — para triagem via LLM (sem chave, usa heurística)

Opcionais:

- `S3_*` — persistência bruta no bucket MEGA S4
- `AGENT_SYSTEM_PROMPT`, `OPENAI_MODEL`, `LLM_BASE_URL`

## Arquitetura Railway

```
[Cliente/Telegram futuro] → API (público) → Redis → Worker (privado)
                                ↓                      ↓
                           PostgreSQL              PostgreSQL
                                ↓
                           MEGA S4 (opcional)
```

Documentação detalhada: `docs/railway-deploy-plan.md`, `docs/operations.md` e [`AGENTS.md`](AGENTS.md) (instruções para agentes de IA).

## Roadmap (plano-01)

1. **MVP 1** (atual): triagem, tarefas, bucket opcional, banco
2. **MVP 2**: RDO com aprovação Telegram
3. **MVP 3**: relatório fotográfico
4. **MVP 4**: orçamento e cronograma
5. **MVP 5**: medições e gestão

## Licença

MIT — veja [LICENSE](LICENSE).
