# Painel Admin Interno — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) — implement task-by-task. Steps use checkbox (`- [ ]`).

**Goal:** Painel admin interno server-rendered (Jinja+HTMX) sobre o FastAPI existente, protegido por sessão, para operar obras/entradas/documentos/aprovações sem terminal.

**Architecture:** Router `/admin` fora do `require_api_key`, atrás de guard de sessão por cookie (SessionMiddleware). Leitura via `admin_service` novo; mutação 100% por serviços existentes (+1 setter fino). Templates Jinja2Templates com autoescape; HTMX vendorizado.

**Tech Stack:** FastAPI, Starlette SessionMiddleware, Jinja2Templates, HTMX (vendorizado), itsdangerous, SQLAlchemy async, pytest + httpx.ASGITransport.

## Global Constraints

- `from __future__ import annotations` em módulos core; imports no topo (sem inline).
- mypy strict sobre `src/`; ruff line 100, py311, regras `E,F,I,UP`.
- API = sessão async via `Depends(get_db)`.
- Mensagens de erro user-facing em PT.
- Sem migration (decisão do spec §2.4).
- Gate de pré-entrega: `make lint && make typecheck && make test`.
- Spec fonte: `docs/superpowers/specs/2026-06-29-painel-admin-interno-design.md`.

---

### Task 1: Config, dependência e erro de auth

**Files:** Modify `src/config/env.py`, `pyproject.toml`, `src/core/errors.py`.
**Produces:** `Settings.admin_password`, `Settings.session_secret`; `AdminLoginRequired(ObrabotError)`.

- [ ] `admin_password: str = ""` e `session_secret: str = ""` em `Settings`.
- [ ] `itsdangerous>=2.0` em `[project.dependencies]`; `uv sync`.
- [ ] `class AdminLoginRequired(ObrabotError)` em `errors.py`.

### Task 2: `obra_service.set_status`

**Files:** Modify `src/services/obra_service.py`; Test `tests/test_admin_obras.py`.
**Produces:** `async def set_status(session, obra_id: str, status: str) -> Obra` (só flush, `NotFoundError` se ausente).

- [ ] Test: muda `Obra.status`; `NotFoundError` p/ id inexistente.
- [ ] Implementar (`session.get` + set + flush).

### Task 3: `admin_service` (leituras)

**Files:** Create `src/services/admin_service.py`; Test `tests/test_admin_service.py`.
**Produces:** `dashboard_counts`, `list_entradas`, `get_entrada`, `list_documentos`, `get_documento_com_triagem`; const `AGUARDANDO_APROVACAO = (DocumentStatus.RASCUNHO_GERADO, DocumentStatus.EM_REVISAO)`.

- [ ] Tests com AsyncSession mockada (estilo `tests/test_obras.py`).
- [ ] Queries: GROUP BY counts; filtros status; join Triagem; paginação limit=50/max200/offset=0.

### Task 4: Wiring do app + auth

**Files:** Modify `src/api/server.py`; Create `src/api/routes/admin.py` (guard+login), `src/static/admin/htmx.min.js`; Test `tests/test_admin_auth.py`.
**Produces:** `require_admin_session` (raise), `templates`, `GET/POST /admin/login`, `POST /admin/logout`.

- [ ] `create_app`: resolver session_secret efetiva; vazia + prod → `raise` PT (fail-closed).
- [ ] `add_middleware(SessionMiddleware, secret_key, https_only=is_production, same_site="lax")`.
- [ ] `mount("/admin/static", StaticFiles("src/static/admin"))`.
- [ ] `require_admin_session`: `if not request.session.get("admin"): raise AdminLoginRequired()`.
- [ ] `@app.exception_handler(AdminLoginRequired)` → `RedirectResponse("/admin/login",303)`.
- [ ] `POST /admin/login`: config vazia (500) **antes** de `compare_digest`; sucesso → session+303; falha → 200+erro. Rate-limit IP.
- [ ] `POST /admin/logout`: clear+303. `include_router(admin_router)` fora de protected.
- [ ] Vendorizar `htmx.min.js` pinado.
- [ ] Tests: guard GET+POST sem sessão; login ok/erro/config-vazia; smoke `GET /admin/login`.

### Task 5: Rotas páginas/mutações

**Files:** Modify `src/api/routes/admin.py`; Test `tests/test_admin_routes.py`.

- [ ] `GET /admin` dashboard.
- [ ] Obras: list; `nova`/`editar` (`upsert_obra`+commit; id read-only no editar); `POST /{id}/status` (`set_status`+commit, swap `_obra_row`).
- [ ] Entradas: `?status=`∈{received,processing,completed,failed,pending_obra}; `{entrada_id:uuid}` detalhe; `resolver-obra` (`resolve_pending_obra`, sem commit, traduz dict; mocka enqueue).
- [ ] Documentos: `?status=` MAIÚSCULO validado vs `DocumentStatus`; detalhe; `aprovar` (`approve_document`, sem commit, swap `_aprovacao_panel`).
- [ ] Convenção: mutação→200+parcial; GET filtro→página cheia ou parcial se `HX-Request`. POST checa Origin/Referer same-origin.

### Task 6: Templates

**Files:** Create `src/templates/admin/{base,login,dashboard,obras,obra_form,entradas,entrada_detail,documentos,documento_detail}.html` + parciais `_obra_row.html`,`_entrada_resolver.html`,`_aprovacao_panel.html`.

- [ ] `base.html` navbar + `<script src="/admin/static/htmx.min.js">`.
- [ ] `entrada_detail.html`: `raw_payload` via `json.dumps(indent=2)` em `<pre>` (escapado, nunca `|safe`).

### Task 7: Gate + XSS + fechamento

- [ ] Test XSS: `<script>` em author/raw_payload sai escapado.
- [ ] `make lint && make typecheck && make test` verde.
- [ ] Commit + PR + deploy Railway.

---

## Self-Review (spec → task)

- §2.2 render/autoescape → T4+T6+T7. §2.3 static → T4. §3 auth → T1+T4. §4.1 admin_service → T3. §4.2/4.3 mutações+commit → T2+T5. §4.4 assinaturas → T5. §5 rotas+filtros → T5+T6. §7 mudanças → T1–T6. §8 testes → T2,T3,T4,T5,T7. §10 aceite → T7. ✅
