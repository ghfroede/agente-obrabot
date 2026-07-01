# AGENTS.md — Obrabot

Instruções para agentes de IA (Cursor, Claude Code, OpenClaw, etc.) trabalhando neste repositório.

## O que é este projeto

**Obrabot (Construtora AgentOS)** — agente de gestão documental para construtoras. Recebe entradas de engenheiros (texto, foto, áudio, documento), classifica automaticamente, persiste evidências auditáveis e gera documentos operacionais (RDO, relatório fotográfico) com **aprovação humana obrigatória** antes da publicação final no bucket.

**Estado atual (MVP operacional):** ingestão unificada, Telegram/OpenClaw com HMAC, painel admin, RDO E2E, relatório fotográfico E2E, orçamento/cronograma com baseline validado. Medições têm API básica; gestão avançada está no backlog.

Roadmap interno: `dev/plan-2.md` (não implementar escopo futuro sem pedido explícito).

## Stack

| Camada | Tecnologia |
|--------|------------|
| Runtime | Python 3.12+, [uv](https://docs.astral.sh/uv/) |
| API | FastAPI + Uvicorn (`src/api/`) |
| Worker | RQ + Redis (`src/worker/`) |
| Banco | PostgreSQL + SQLAlchemy 2.0 async + Alembic |
| LLM | OpenAI SDK (`AsyncOpenAI`), API OpenAI-compatible |
| PDF | xhtml2pdf via `src/services/pdf_service.py` |
| Storage | S3-compatible (`src/services/bucket_service.py`) |
| Templates | Jinja2 (`src/templates/`) |
| Deploy | Railway (serviços `api`, `worker`, `OpenClaw`) |

## Arquitetura

Ingestão **unificada**: todo canal grava uma `EntradaBruta` antes da IA e enfileira `process_entrada`.

```
POST /tasks            ┐
POST /api/v1/openclaw  ┘→ API → EntradaBruta → Redis (fila obrabot) → 202
                                ↓                        ↓
                           PostgreSQL          Worker → run_entrada_pipeline
                                                          ↓
                                              S3 + mídia + triagem + Documento
```

### Caminhos síncronos vs assíncronos

| Tipo | Rotas | Onde roda |
|------|-------|-----------|
| Assíncrono | `/tasks`, `/api/v1/openclaw/telegram-event` | Worker RQ |
| Síncrono | `/api/v1/rdo/*`, `/fotos/*`, `/orcamento/*`, `/medicoes`, `/obras`, etc. | Request FastAPI |

### Entry points

| Arquivo | Papel |
|---------|-------|
| `src/api/server.py` | App FastAPI, middleware, routers |
| `src/services/entrada_service.py` | **Núcleo de ingestão** (`run_entrada_pipeline`) |
| `src/services/rdo_service.py` | RDO: rascunho, aprovar-finalizar, PDF |
| `src/services/foto_service.py` | Relatório fotográfico + PDF |
| `src/services/orcamento_service.py` | Orçamento, cronograma, baseline |
| `src/services/rdo_aggregator_service.py` | Agrega evidências do dia para RDO |
| `src/services/media_service.py` | Foto/áudio → `Arquivo` + domínio |
| `src/api/routes/admin.py` | Painel `/admin` (sessão, Jinja2) |
| `src/worker/index.py` | Worker RQ: `process_entrada` |
| `src/db/models.py` | Modelos SQLAlchemy |
| `alembic/` | Migrations (head: `009_add_telegram_contextos`) |

## Comandos

```bash
uv sync
make dev-api          # API :8000
make dev-worker       # worker RQ
make test             # pytest
make lint             # ruff
make typecheck        # mypy strict
make db-migrate       # alembic upgrade head
docker compose up -d  # Postgres + Redis local
```

Smoke E2E em produção (via Railway):

```bash
make smoke-prod-railway
make smoke-rdo-railway
make smoke-foto-railway
make smoke-orcamento-railway
```

## Convenções de código

- **Imports no topo** — sem imports inline.
- **Tipagem estrita** — mypy strict em `src/`.
- **Async na API**, sync no worker RQ (`asyncio.run` para pipeline async).
- **Settings** via `get_settings()` — nunca hardcode secrets.
- **Diff mínimo** — reutilize padrões existentes.
- **Switch exhaustivo** em unions/enums TypeScript (regra Cursor); em Python, `match` com `case _:` + `assert_never` quando aplicável.
- Responder ao usuário em **português**.

## Invariantes de domínio

1. Toda entrada gera `EntradaBruta` no PostgreSQL **antes** da IA; raw no bucket antes da triagem (quando S3 configurado).
2. Sem IA no caminho do request de ingestão — processamento pesado na fila RQ.
3. Idempotência OpenClaw é **atômica** (`INSERT ... ON CONFLICT`).
4. **PDF final e publicação em pasta final exigem aprovação humana** (`approve_and_finalize_*` ou fluxo admin).
5. Fonte de verdade: bucket + PostgreSQL — não a resposta da IA.
6. Painel `/admin/*` exige sessão válida (`AdminLoginRequired` → redirect login).
7. Produção é **fail-closed**: HMAC obrigatório, allowlist Telegram, rate limit Redis, secrets admin ausentes derrubam boot.

## Fluxos documentais implementados

### RDO

1. Entradas do dia processadas → `POST /api/v1/rdo/gerar`
2. Revisão humana (admin ou Telegram)
3. `POST /api/v1/rdo/aprovar-finalizar` → PDF em `05_RDO/finalizados_pdf/`

### Relatório fotográfico

1. Fotos classificadas em `fotos` (via worker + visão)
2. `POST /api/v1/fotos/relatorio` → rascunho HTML
3. `POST /api/v1/fotos/relatorio/aprovar-finalizar` → PDF em `04_documentos_finais/relatorio_fotografico/`

### Baseline (orçamento + cronograma)

1. `POST /api/v1/orcamento/importar` + `POST /api/v1/cronograma/importar`
2. `POST /api/v1/baseline/validar` → relatório de prontidão
3. `POST /api/v1/baseline/aprovar` → JSON em `07_planejamento/baseline/` + metadata em `obra.metadata_json`

O agregador RDO inclui contexto `baseline` quando validado.

## Deploy Railway

- Config: `railway.api.json`, `railway.worker.json`
- `railway.json` no `.gitignore` (cópia local)
- Docs: `docs/railway-deploy-plan.md`, `docs/operations.md`
- **Nunca** expor o worker publicamente

## Graphify

Antes de explorar código desconhecido, consulte o grafo:

```bash
graphify query "termo relevante"
graphify update .   # após mudanças de código
```

Após mudanças em README/AGENTS.md/docs: rode `graphify extract` + `graphify cluster-only` (ver `.cursor/rules/graphify.mdc`).

## O que evitar

- Não commitar `.env`, secrets ou `railway.json`
- Não criar commits/PRs sem pedido explícito do usuário
- Não bypassar gate de aprovação humana para documentos finais
- Não acessar bucket/DB diretamente no OpenClaw — use a API

## Mapa de diretórios

```
src/api/routes/    Rotas HTTP
src/services/      Lógica de negócio
src/worker/        Jobs RQ
src/db/            Models + sessions
src/templates/     Jinja2 (RDO, relatório fotográfico)
src/core/          Constantes, erros, segurança (HMAC)
src/config/        Env settings
openclaw/          Skills e agentes OpenClaw
tests/             pytest
scripts/           Smoke tests e utilitários
docs/              Documentação operacional
alembic/           Migrations
```

Documentação detalhada: [docs/README.md](docs/README.md).
