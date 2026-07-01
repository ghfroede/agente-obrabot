# CLAUDE.md

Guidance for Claude Code working in this repository. Sister docs: [AGENTS.md](AGENTS.md), [README.md](README.md), [docs/](docs/). **Respond to the user in Portuguese.**

## Commands

```bash
uv sync
docker compose up -d
make db-migrate
make dev-api            # :8000
make dev-worker         # separate terminal
make test               # pytest -q (134+ tests)
make lint && make typecheck && make test   # pre-delivery gate
```

Single test: `uv run pytest tests/test_orcamento_service.py -q`. pytest `asyncio_mode = auto`.

## Architecture

**Unified ingestion.** Every channel writes `EntradaBruta` (`received`) before AI, enqueues `process_entrada` on Redis queue `obrabot`. Pipeline in [entrada_service.py](src/services/entrada_service.py): raw persist → media download → triagem → `Documento`/`Triagem`/`AuditoriaEvento`.

- **`/tasks`**: `Task` + `EntradaBruta(source=api)` → `202`; worker mirrors status on `Task`.
- **OpenClaw webhook**: HMAC + idempotency → `EntradaBruta(source=openclaw)` → `202`.
- **Other `/api/v1/*`**: synchronous on async DB session (RDO, fotos, orçamento, medições, obras).

**Document flows (all require human approval for final PDF):**

| Flow | Generate | Approve+finalize |
|------|----------|------------------|
| RDO | `POST /api/v1/rdo/gerar` | `POST /api/v1/rdo/aprovar-finalizar` |
| Relatório fotográfico | `POST /api/v1/fotos/relatorio` | `POST /api/v1/fotos/relatorio/aprovar-finalizar` |
| Baseline | import orçamento + cronograma | `POST /api/v1/baseline/aprovar` |

Services: [rdo_service.py](src/services/rdo_service.py), [foto_service.py](src/services/foto_service.py), [orcamento_service.py](src/services/orcamento_service.py), [rdo_aggregator_service.py](src/services/rdo_aggregator_service.py).

**Admin panel** [admin.py](src/api/routes/admin.py): session auth (`SESSION_SECRET` + `ADMIN_PASSWORD`), Jinja2 + HTMX. Not behind `require_api_key`. Dia-obra view aggregates evidence and generates RDO drafts.

**Security** [security.py](src/core/security.py): HMAC canonical string `timestamp\nevent_id\nmethod\npath\nsha256(body)`. Idempotency via `idempotency_keys` table. Production: `OPENCLAW_REQUIRE_HMAC=true`, Telegram allowlist, Redis rate limits.

**Config** [env.py](src/config/env.py): `get_settings()` cached. Flags: `s3_configured`, `is_production`.

**Domain model** [models.py](src/db/models.py): `EntradaBruta`, `Obra`, `Documento`, `Triagem`, `Foto`, `OrcamentoItem`, `CronogramaAtividade`, `Medicao`, `Aprovacao`, `AuditoriaEvento`. `DocumentStatus` in [constants.py](src/core/constants.py). Migration head: `009_add_telegram_contextos`.

## Conventions

- Imports at top; `from __future__ import annotations` in core modules.
- mypy strict on `src/`; ruff line 100, py311.
- API async session via `Depends(get_db)`; worker uses `asyncio.run` + `AsyncSessionLocal`.
- Pydantic v2 schemas in [domain.py](src/schemas/domain.py) separate from SQLAlchemy models.
- Schema changes → Alembic migration only.
- Error messages to users in Portuguese; [errors.py](src/core/errors.py) mapped in server handlers.
- Minimal diffs; match existing patterns.

## Railway

Two services from repo: `railway.api.json` (uvicorn + `alembic upgrade head` pre-deploy), `railway.worker.json`. OpenClaw is separate template service. `railway.json` gitignored — set config path in dashboard or `RAILPACK_START_CMD`. Never expose worker publicly.

Smoke in production:

```bash
railway run --service api uv run python scripts/smoke_prod.py
railway run --service api uv run python scripts/smoke_rdo.py
railway run --service api uv run python scripts/smoke_foto.py
railway run --service api uv run python scripts/smoke_orcamento.py
```

## Docs map

| File | Purpose |
|------|---------|
| [docs/api-reference.md](docs/api-reference.md) | Full HTTP reference |
| [docs/architecture.md](docs/architecture.md) | Flows and components |
| [docs/operations.md](docs/operations.md) | Runbook |
| [docs/storage-taxonomy.md](docs/storage-taxonomy.md) | S3 key layout |
| [docs/guia-engenheiro.md](docs/guia-engenheiro.md) | Telegram user guide |
