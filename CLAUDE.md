# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sister docs: [AGENTS.md](AGENTS.md) (agent instructions, domain invariants), [README.md](README.md) (quickstart), `.cursor/rules/*.mdc` (Cursor rules — same conventions encoded below). Internal roadmap in `dev/plan-0.md`, `dev/plan-1.md` (not deployed; do not implement future scope without explicit request). **Respond to the user in Portuguese.**

## Commands

```bash
uv sync                 # install deps (dev included); uv is the only package manager
docker compose up -d    # local Postgres + Redis
make db-migrate         # alembic upgrade head
make dev-api            # API on :8000 (uvicorn --reload)
make dev-worker         # RQ worker (separate terminal)
make test               # pytest -q
make lint               # ruff check src tests
make typecheck          # mypy src (strict)
```

Pre-delivery gate (run all three): `make lint && make typecheck && make test`

Single test: `uv run pytest tests/test_triagem.py -q` or `uv run pytest tests/test_mvp1.py::test_name -q`. pytest uses `asyncio_mode = auto` — async tests need no `@pytest.mark.asyncio`. Mock LLM/Redis/S3 in unit tests; never hit external services.

## Architecture

**Unified ingestion (Sprint 2).** Every channel produces an `EntradaBruta` row (`received`) *before* any AI runs, then enqueues `src.worker.jobs.process_entrada` on the `obrabot` Redis queue. The heavy pipeline (raw persist → mídia download → triagem → `Documento`/`Triagem`/`AuditoriaEvento`) runs in the worker via [entrada_service.run_entrada_pipeline](src/services/entrada_service.py) — never in the request path. The single ingestion core is [src/services/entrada_service.py](src/services/entrada_service.py) (`create_entrada_bruta` / `enqueue_entrada` / `ingest_telegram` / `run_entrada_pipeline`).

**Telegram media (Sprint 3).** When the Telegram payload carries `photo`/`voice`/`audio`/`document`, the worker fetches + persists it via [telegram_media_service](src/services/telegram_media_service.py) (`getFile`→download, client injetável p/ teste) + [media_service](src/services/media_service.py) (`Arquivo` + `Foto`/`AudioTranscricao`, `describe_image`/`transcribe_audio`). Media text enriches the triagem input; a per-media download failure degrades (records `erro`, raw já persistido). Status reply to the engineer is **opt-in** (`telegram_reply_enabled`, default off). Needs `telegram_bot_token` on the worker.

- **`/tasks`** ([src/api/routes/tasks.py](src/api/routes/tasks.py)): `POST` writes a `Task` (`queued`) **plus** an `EntradaBruta` (`source="api"`, `task_id` linked) and enqueues `process_entrada` → `202`. The worker processes the entrada and mirrors final status/result back onto the linked `Task`; clients poll `GET /tasks/:id`.
- **`/api/v1/openclaw/telegram-event`** ([src/api/routes/openclaw.py](src/api/routes/openclaw.py) → `entrada_service.ingest_telegram`): HMAC-verified, claims idempotency, writes `TelegramMessage` + `EntradaBruta` (`source="openclaw"`) and enqueues → `202 Accepted`. No synchronous triagem.
- **Other `/api/v1/*`** (`obras`/`documentos`/`fotos`/`orcamento`/`medicoes`/`triagem`): still run synchronously in-request on the async DB session. Routers wired in [src/api/server.py](src/api/server.py).
- **`/admin`** ([src/api/routes/admin.py](src/api/routes/admin.py)): painel interno server-rendered (Jinja2Templates + HTMX vendorizado em `/admin/static`) — obras (CRUD + ativar/desativar), entradas (filtro por status + payload bruto + resolver `pending_obra`), documentos+triagens (read-only) e aprovar/reprovar. Incluído **fora** do `protected_dependencies` (não usa `require_api_key`): auth por sessão via `SessionMiddleware` (cookie HttpOnly + SameSite=Lax, Secure em prod), guard `require_admin_session` que **interrompe via `raise AdminLoginRequired`** → handler redireciona `303` p/ `/admin/login`. Login = `hmac.compare_digest` contra `admin_password` (fallback `obrabot_api_key` só em dev); em prod `session_secret`/senha vazios = **fail-closed** (RuntimeError no boot). Rate-limit de login por IP (`admin_login_max_per_minute`); POSTs checam `Origin`/`Referer`. Leituras via [src/services/admin_service.py](src/services/admin_service.py); mutações reusam `obra_service.upsert_obra`/`set_status`, `entrada_service.resolve_pending_obra` e `approval_service.approve_document`. Sem migration (reusa `Obra.status`).

`run_ceo_pipeline` ([src/agent/ceo.py](src/agent/ceo.py)) remains a thin triagem+storage orchestrator used by the legacy `process_task` job; new work flows through `entrada_service`.

**Raw-first invariant (all paths):** persist the raw entry to the S3 bucket *before* calling the LLM. The bucket + PostgreSQL are the source of truth — never the AI response. See `persist_raw_entry` ([src/storage/s3.py](src/storage/s3.py)) and `bucket_service.persist_entrada_bruta` (keyed by `source`).

**Dual DB engines** ([src/db/client.py](src/db/client.py)): async engine (`AsyncSessionLocal`, asyncpg) for the API; sync engine (`SyncSessionLocal`, psycopg2) for the legacy `process_task`. The worker's `process_entrada` wraps the async `run_entrada_pipeline` in `asyncio.run(...)` and opens its own `AsyncSessionLocal`. `Settings` derives both URLs from a single `DATABASE_URL` (`async_database_url` / `sync_database_url` properties rewrite the driver).

**LLM layer** ([src/services/openai_service.py](src/services/openai_service.py)): `triagem_structured` returns a Pydantic `TriagemOutput`. Without `OPENAI_API_KEY` it falls back to a heuristic (mode tagged `"heuristic"` vs `"llm"`). LLM responses must be valid JSON — parsed defensively.

**Config** ([src/config/env.py](src/config/env.py)): all settings via `get_settings()` (`@lru_cache`d pydantic-settings). Two capability flags gate optional behavior: `s3_configured` (all three S3 creds present) and presence of `openai_api_key`. Never hardcode secrets.

**OpenClaw webhook security** ([src/core/security.py](src/core/security.py)): `verify_hmac_signature` checks `X-OpenClaw-Signature` (HMAC-SHA256 over the canonical `timestamp\nevent_id\nmethod\npath\nsha256(body)`), `X-Timestamp` (±5 min window), and `X-Event-Id` — and validates `X-Event-Id == payload.event_id` so the id is part of the signed proof. **All checks no-op when `openclaw_shared_secret` is empty** — set it in production. Idempotency is **atomic**: `claim_idempotency` does `INSERT ... ON CONFLICT DO NOTHING` (status `processing`) and commits before processing; the winner runs, then `complete_idempotency`/`fail_idempotency` update status + `response_json`. Key = `event_id:content_hash:obra_id` in `idempotency_keys`; duplicates return the cached `response_json`. `verify_openclaw_secret` (static header) is legacy only.

**Domain model** ([src/db/models.py](src/db/models.py)): `Task`, `Obra` (PK is a short string id), `EntradaBruta` (unified ingestion record — `source`/`status`/`hash_sha256`/`raw_payload`/`task_id`), then the OpenClaw/document chain `TelegramMessage`→`Arquivo`→`Documento`→`Triagem`, plus `Foto`/`AudioTranscricao`/`Aprovacao`/`OrcamentoItem`/`CronogramaAtividade`/`Medicao`/`AuditoriaEvento`/`IdempotencyKey`. `Documento.status` follows the `DocumentStatus` lifecycle in [src/core/constants.py](src/core/constants.py); final publish requires human approval (`FINAL_PUBLISH_STATUSES`). Latest migration: `005_add_entradas_brutas` (apply with `make db-migrate`).

## Conventions

- `from __future__ import annotations` in core modules; imports at top — no inline imports.
- mypy strict over `src/` — type all public params/returns. ruff: line 100, target py311, rules `E,F,I,UP`.
- API = async session via `Depends(get_async_session)` / `get_db`; worker = sync session + `asyncio.run` for the async pipeline.
- Pydantic v2 schemas ([src/schemas/domain.py](src/schemas/domain.py)) kept separate from SQLAlchemy models.
- Any schema change requires an Alembic migration ([alembic/versions/](alembic/versions/)) — never alter the DB by hand.
- User-facing `HTTPException`/error messages in Portuguese; custom errors in [src/core/errors.py](src/core/errors.py) map to status codes via handlers in `server.py`.
- Minimal diffs; reuse existing patterns. Keep the CEO agent a thin orchestrator — new specialists go in `src/agent/` + a dedicated RQ job, not inline in the pipeline.

## Railway deploy

Two services, config-as-code: `railway.api.json` (uvicorn `src.api.server:app`) and `railway.worker.json` (`python -m src.worker.index`). Build: `pip install uv && uv sync --frozen --no-dev`. API pre-deploy runs `alembic upgrade head`.

Gotcha: `railway.json` is gitignored, so GitHub deploys don't see it — either set the config path per service in the dashboard, or set `RAILPACK_START_CMD` per service (see [docs/railway-deploy-plan.md](docs/railway-deploy-plan.md), [docs/operations.md](docs/operations.md)). **Never** expose the worker on a public domain or commit secrets / `railway.json`.
