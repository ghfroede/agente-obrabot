# Obrabot — Construtora AgentOS

Agente de IA para gestão documental de obras de construção civil. O MVP operacional cobre **ingestão unificada** (API + Telegram/OpenClaw), **triagem automática**, **RDO com aprovação humana**, **relatório fotográfico**, **orçamento/cronograma com baseline validado**, **painel admin** e **persistência auditável** no PostgreSQL + bucket S3-compatible.

## Stack

| Camada | Tecnologia |
|--------|------------|
| Runtime | Python 3.12+ (ver `.python-version`), [uv](https://docs.astral.sh/uv/) |
| API | FastAPI, Uvicorn |
| Worker | RQ + Redis |
| Banco | PostgreSQL + Alembic (head: `010_medicao_periodos`) |
| LLM | OpenAI-compatible (OpenAI, etc.) |
| PDF | xhtml2pdf (pure Python, compatível com Railway) |
| Storage | S3-compatible (MEGA S4) — opcional em dev |
| Deploy | Railway (`api`, `worker`, `OpenClaw`, Postgres, Redis) |

## Início rápido

```bash
uv sync
cp .env.example .env
docker compose up -d
make db-migrate
make dev-api    # terminal 1
make dev-worker # terminal 2
```

API em `http://localhost:8000`. Healthcheck: `GET /health`.

## Arquitetura (resumo)

```
Cliente HTTP / Telegram (OpenClaw)
        ↓
   API (FastAPI) → EntradaBruta → Redis (fila obrabot) → Worker
        ↓                              ↓
   PostgreSQL                    raw S3 → mídia → triagem IA
        ↓                              ↓
   Painel /admin              Documento / Triagem / Auditoria
```

Detalhes: [docs/architecture.md](docs/architecture.md).

## API pública (`X-Obrabot-API-Key`)

| Área | Rotas principais |
|------|------------------|
| Saúde | `GET /health` |
| Tarefas | `POST /tasks`, `GET /tasks/{id}` |
| OpenClaw | `POST /api/v1/openclaw/telegram-event` (HMAC, sem API key) |
| Obras | `GET/POST /api/v1/obras` |
| Telegram | `GET/POST /api/v1/telegram-contextos` |
| Entradas | `POST /api/v1/entradas/{id}/resolver-obra` |
| RDO | `POST /api/v1/rdo/rascunho`, `/gerar`, `/aprovar-finalizar`, `/finalizar` |
| Fotos | `POST /api/v1/fotos/relatorio`, `/relatorio/aprovar-finalizar` |
| Orçamento | `GET/POST /api/v1/orcamento/...` |
| Cronograma | `GET/POST /api/v1/cronograma/...` |
| Baseline | `POST /api/v1/baseline/validar`, `/aprovar` |
| Medições | `POST /api/v1/medicoes`, `/fechar` |
| Aprovações | `POST /api/v1/aprovacoes` |
| Documentos | `GET /api/v1/documentos/{id}` |

Referência completa: [docs/api-reference.md](docs/api-reference.md).

## Painel admin

| Rota | Descrição |
|------|-----------|
| `GET /admin/login` | Login (sessão assinada) |
| `GET /admin` | Dashboard |
| `GET /admin/dia-obra` | Consolidação do dia + gerar RDO |
| `GET /admin/obras`, `/entradas`, `/documentos` | CRUD e revisão operacional |

Auth por cookie (`SESSION_SECRET` + `ADMIN_PASSWORD`). Não usa `X-Obrabot-API-Key`.

## Comandos Telegram (OpenClaw)

| Comando | Ação |
|---------|------|
| `/gerar_rdo {obra} hoje` | Rascunho RDO do dia |
| `/aprovar_rdo {documento_id}` | Aprova + PDF final |
| `/gerar_relatorio_foto {obra} {início} {fim}` | Relatório fotográfico |
| `/aprovar_relatorio_foto {documento_id}` | Aprova + PDF final |
| `/validar_baseline {obra}` | Valida orçamento + cronograma |
| `/aprovar_baseline {obra}` | Publica baseline no bucket |

Guia do engenheiro: [docs/guia-engenheiro.md](docs/guia-engenheiro.md).

## Scripts e smoke tests

| Comando | Descrição |
|---------|-----------|
| `make test` | pytest (~210 testes unitários; integração via `pytest -m integration`) |
| `make lint` | ruff |
| `make typecheck` | mypy strict |
| `make security-audit` | exporta `uv.lock` e roda `uvx pip-audit --strict` |
| `make smoke-prod-railway` | Smoke integração produção |
| `make smoke-rdo-railway` | E2E RDO (gerar + aprovar PDF) |
| `make smoke-foto-railway` | E2E relatório fotográfico |
| `make smoke-orcamento-railway` | E2E orçamento + cronograma + baseline |

No PowerShell (sem `make`):

```powershell
railway run --service api uv run python scripts/smoke_orcamento.py
```

## Variáveis de ambiente

Veja [.env.example](.env.example). Obrigatórias em **produção** (serviço `api`):

- `DATABASE_URL`, `REDIS_URL` — injetados pelo Railway
- `CORS_ORIGIN` — allowlist CSV explícita; `*` é bloqueado em produção
- `OBRABOT_API_KEY` — header `X-Obrabot-API-Key`
- `API_MAX_BODY_BYTES` — limite global para bodies JSON/HTTP gerais (default 10 MiB)
- `ADMIN_LOGIN_MAX_BODY_BYTES` — limite específico do formulário `/admin/login` (default 16 KiB)
- `OPENCLAW_SHARED_SECRET` + `OPENCLAW_REQUIRE_HMAC=true`
- `WEBHOOK_MAX_BODY_BYTES` — limite do webhook OpenClaw (default 10 MiB)
- `ADMIN_PASSWORD` + `SESSION_SECRET` — painel admin (fail-closed)
- `TELEGRAM_ALLOWED_CHAT_IDS` / `TELEGRAM_ALLOWED_USER_IDS` — allowlist
- `RATE_LIMIT_PROTECTED_PER_MINUTE` / `RATE_LIMIT_EXPENSIVE_PER_MINUTE` — quotas
  para rotas autenticadas, com limite menor em rotas caras

No **worker**: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `S3_*` (se bucket ativo).

Em produção, `/docs`, `/redoc` e `/openapi.json` ficam desabilitados.
O boot também falha se secrets obrigatórios estiverem ausentes ou com placeholders
conhecidos.

A API também aplica headers de segurança em todas as respostas HTTP:
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
`Permissions-Policy` e CSP compatível com o painel admin. HSTS é emitido apenas
em produção quando a requisição é HTTPS.

## Produção (Railway)

| Serviço | URL / notas |
|---------|-------------|
| API | `https://api-production-8bfb.up.railway.app` |
| OpenClaw | gateway Telegram com HMAC → API |
| Obra smoke | `OBRA-SMOKE` |

Operação: [docs/operations.md](docs/operations.md). Deploy: [docs/railway-deploy-plan.md](docs/railway-deploy-plan.md). Bucket: [docs/storage-taxonomy.md](docs/storage-taxonomy.md).

## Roadmap (estado atual)

| MVP | Escopo | Status |
|-----|--------|--------|
| 1 | Ingestão unificada, triagem, OpenClaw HMAC | ✅ |
| 2 | RDO com aprovação Telegram + PDF | ✅ |
| 3 | Relatório fotográfico com aprovação | ✅ |
| 4 | Orçamento + cronograma + baseline validado | ✅ |
| 5 | Medições e gestão de obra | ⏳ backlog |
| 6 | OpenAI Agents SDK multiagente | ⏳ backlog |

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [AGENTS.md](AGENTS.md) | Instruções para agentes de IA no repositório |
| [CLAUDE.md](CLAUDE.md) | Guia técnico conciso (Claude Code) |
| [docs/README.md](docs/README.md) | Índice da documentação |
| [docs/api-reference.md](docs/api-reference.md) | Referência HTTP completa |
| [docs/architecture.md](docs/architecture.md) | Arquitetura e fluxos |
| [docs/operations.md](docs/operations.md) | Runbook operacional |
| [docs/guia-engenheiro.md](docs/guia-engenheiro.md) | Uso no Telegram |
| [SECURITY.md](SECURITY.md) | Política de segurança e auditoria de dependências |
| [openclaw/skills/](openclaw/skills/) | Skills OpenClaw por domínio |

## Licença

MIT — veja [LICENSE](LICENSE).
