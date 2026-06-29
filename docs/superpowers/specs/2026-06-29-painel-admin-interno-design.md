# Painel Admin Interno do Obrabot — Design (v1)

- **Data:** 2026-06-29
- **Status:** aprovado para planejamento (revisado pós-review adversarial multi-lente)
- **Autor:** brainstorming colaborativo (Claude Code)
- **Escopo:** painel administrativo interno para operar o Obrabot sem chamadas REST manuais, scripts ou `/docs`.

## 1. Objetivo

Entregar um painel interno, protegido, server-rendered, que permita ao operador:

1. Cadastrar e gerenciar obras (CRUD + ativar/desativar).
2. Listar entradas (`EntradaBruta`) com filtro por status e inspecionar o payload bruto.
3. Resolver pendências de obra (`pending_obra`) selecionando uma obra cadastrada.
4. Visualizar documentos gerados e suas triagens estruturadas (read-only).
5. Aprovar/reprovar documentos que aguardam aprovação humana.

O painel é a base operacional para testar RDO, aprovação humana e relatório fotográfico sem depender de terminal.

## 2. Decisões de arquitetura

### 2.1 Stack: server-rendered (Jinja + HTMX), sem SPA

O repositório já usa Jinja2 (`src/templates/rdo.html`, `relatorio_fotografico.html`) via `jinja2.Environment` + `FileSystemLoader(settings.templates_dir)` (ver `src/services/rdo_service.py:20-25`). O FastAPI já é a fonte de verdade e expõe os serviços de domínio necessários.

Reaproveitar esse stack elimina, para um painel **interno de MVP**: um segundo serviço no Railway, build/bundler, CORS, e uma segunda camada de auth no front. A interatividade pontual (resolver `pending_obra`, aprovar documento, toggle de obra) é coberta por **HTMX**, sem JavaScript de build. HTMX justifica-se sobre POST+redirect puro por evitar reload de página inteira em toggle/aprovação (operação frequente do operador).

Alternativas descartadas:
- **SQLAdmin (auto-CRUD):** rápido para listar/editar models, mas as telas custom (resolver-obra, aprovação) ficam fora do padrão e dão pouco controle de UX.
- **SPA React/Vite separado:** UI mais rica e escalável, porém adiciona 2º serviço, build, CORS e auth via token no front — infra desproporcional para um painel interno de MVP. Reavaliar só se o painel virar produto externo.

### 2.2 Mecanismo de renderização Jinja (explícito)

O painel usa **`fastapi.templating.Jinja2Templates`** (autoescape habilitado por padrão para `.html`), instanciado **uma vez** em nível de módulo em `src/api/routes/admin.py`:

```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory=get_settings().templates_dir)  # "src/templates"
```

- Templates do painel ficam em `src/templates/admin/` (`base.html` + páginas + parciais).
- Rotas de página retornam `templates.TemplateResponse("admin/<page>.html", {"request": request, ...})` — o `request` é obrigatório no contexto (HTMX/`url_for`).
- **Autoescape é obrigatório.** `Jinja2Templates` já liga autoescape para `.html`; nenhuma chamada `|safe` sobre dados de entrada. `raw_payload` (JSONB) e `author` são controlados por terceiros via ingestão Telegram/OpenClaw (`EntradaBruta.raw_payload`/`author`, `src/db/models.py:318-321`) — renderizar `raw_payload` como `json.dumps(payload, indent=2, ensure_ascii=False)` dentro de `<pre>` com autoescape **ligado** (string escapada, nunca `|safe`). Isso fecha o sink de stored-XSS na sessão do operador.

### 2.3 Montagem e isolamento

- Router novo `src/api/routes/admin.py`, montado em `/admin`, incluído em `create_app()` (`src/api/server.py`).
- **Fora** do bloco `protected_dependencies = [Depends(require_api_key)]` (`src/api/server.py:58-66`), porque `require_api_key` valida o header `X-Obrabot-API-Key` — inadequado para navegação/forms de browser.
- Todas as rotas `/admin/*` (exceto `login`) ficam atrás da dependência `require_admin_session` (§3). Nenhuma rota pública nova é criada.
- **Estáticos:** `htmx.min.js` é **vendorizado** (não CDN) em `src/static/admin/htmx.min.js`, servido por um mount `StaticFiles` em `/admin/static` adicionado em `create_app()`. Decisão: prod no Railway não tem CDN garantido nem StaticFiles hoje (ver memória do projeto), então o painel não pode depender de CDN externo para sua interatividade. Versão do HTMX é pinada no arquivo vendorizado.

### 2.4 Sem mudança de schema

`Obra.status` já é `String(32)` com default `"ativa"` (`src/db/models.py:71`). Ativar/desativar é update desse campo — **nenhuma migration Alembic no v1 inteiro**. Listagem de `EntradaBruta`/`Documento` não existe como serviço, mas as rotas admin consultam o DB diretamente (apropriado para server-rendering).

## 3. Autenticação (sessão por cookie)

Browser não envia header customizado em navegação/forms; portanto, em vez do `require_api_key`, usamos sessão por cookie assinado.

### 3.1 Settings novas

Adicionar a `Settings` (`src/config/env.py`):
- `admin_password: str = ""` — senha de login do painel, **separada** da `obrabot_api_key` (a API key é credencial de máquina; reusá-la como senha humana amplia o blast radius). Fallback explícito: se `admin_password` vazia **e não-produção**, usa `obrabot_api_key` (conveniência de dev). Em produção, `admin_password` vazia = falha fechada (login responde 500, mesma postura do `require_api_key`).
- `session_secret: str = ""` — chave de assinatura do cookie de sessão. Resolvida em `create_app()` (não como default, por causa do `@lru_cache`): efetiva = `session_secret or (obrabot_api_key se não-produção)`. **Se a chave efetiva for vazia em produção, `create_app()` levanta erro PT na inicialização** (fail-closed) — `itsdangerous.TimestampSigner("")` assinaria cookies com chave previsível, permitindo forjar `{"admin": true}`.

### 3.2 Middleware

Em `create_app()` (`src/api/server.py`, junto do `CORSMiddleware` em `:48`):

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=<chave efetiva resolvida>,
    https_only=settings.is_production,   # Secure só em prod
    same_site="lax",                      # literal minúsculo, SEMPRE (não só prod)
)
```

Ordem relativa ao CORS é indiferente, mas o middleware precisa envolver todas as rotas `/admin/*` (senão `request.session` levanta `AssertionError`). `same_site` é o literal `"lax"` minúsculo (Starlette tipa `Literal["lax","strict","none"]` — `"Lax"` quebra mypy strict).

### 3.3 Login / logout

- `GET /admin/login` → renderiza form (campo senha). Sem guard.
- `POST /admin/login`:
  1. **Primeiro** checa config: `if not <senha efetiva>: raise 500` (mensagem PT "ADMIN_PASSWORD/OBRABOT_API_KEY obrigatória"). Esta ordem é obrigatória — `compare_digest(x, "")` retornaria `False` e mascararia o 500 como 401.
  2. `hmac.compare_digest(senha_submetida, senha_efetiva)`. Sucesso → `request.session["admin"] = True` + redirect 303 para `/admin`. Falha → re-renderiza o form com erro PT, **HTTP 200** (re-render de form server-rendered; evita confundir HTMX/browser).
  3. **Rate-limit:** `POST /admin/login` passa por limitação por IP (reusar `rate_limit_service`, já usado em `src/core/security.py`) para conter brute-force do segredo compartilhado (v1 não tem MFA).
- `POST /admin/logout` → `request.session.clear()` + redirect 303 para `/admin/login`.

### 3.4 Guard (RAISE, nunca return)

`require_admin_session(request)` lê `request.session.get("admin")`. **Ausente → levanta** uma exceção custom `AdminLoginRequired` (em `src/core/errors.py`). Um `@app.exception_handler(AdminLoginRequired)` em `server.py` (espelhando os handlers existentes em `:68-90`) retorna `RedirectResponse("/admin/login", status_code=303)`.

> Correção crítica: um `Depends()` que **retorna** um `Response` (incluindo `RedirectResponse`) **não** interrompe a rota no FastAPI — o valor é só injetado e o handler roda mesmo assim, deixando `/admin/*` desprotegida. O padrão correto, já usado por `require_api_key` (`src/api/deps.py:26-30`) e pelo guard HMAC (`src/core/security.py`), é **`raise`**. Esta dependência aplica-se a todas as rotas `/admin/*` exceto `login`.

### 3.5 CSRF

Sessão `SameSite=Lax` (em todos os ambientes) bloqueia POST cross-site em browsers modernos. Defesa-em-profundidade barata para v1: **nenhuma rota `/admin/*` muta estado em GET** (todas as mutações são POST-only) e os handlers POST verificam `Origin`/`Referer` same-origin (HTMX sempre envia `Origin`). Tokens CSRF por formulário ficam para a fase 2 (§9).

## 4. Camadas e reuso

Princípio: o router admin **não** contém lógica de domínio. Leitura via um serviço fino novo; mutação via serviços existentes. O router é responsável por: validar input, chamar o serviço, **commitar quando o serviço só faz flush** (ver §4.3), e renderizar o template/parcial.

### 4.1 `admin_service.py` (novo — somente leitura)

- `dashboard_counts(session)` → contadores: entradas por status (`GROUP BY EntradaBruta.status`), documentos aguardando aprovação (ver predicado abaixo), `pending_obra` em aberto.
- `list_entradas(session, *, status=None, limit=50, offset=0)` → página de `EntradaBruta`.
- `get_entrada(session, entrada_id)` → entrada + `raw_payload`/origem/autor/obra/data.
- `list_documentos(session, *, status=None, limit=50, offset=0)` → página de `Documento`.
- `get_documento_com_triagem(session, documento_id)` → `Documento` + `Triagem` associada (confiança, tipo, campos extraídos, pendências, ação sugerida).

**Predicado "aguardando aprovação":** `DocumentStatus` (`src/core/constants.py:6-19`) não tem estado `AGUARDANDO_APROVACAO`. Define-se explicitamente: **aguardando aprovação = `status in {RASCUNHO_GERADO, EM_REVISAO}`** (constante compartilhada usada tanto no `dashboard_counts` quanto no filtro de documentos). Ajustar se o time preferir outro conjunto, mas o predicado precisa ser nomeado.

**Paginação:** `limit` default 50, máximo 200; `offset` default 0. As rotas GET aceitam `?limit=&?offset=` via `Query(default=..., le=200, ge=0)`. Template renderiza prev/next simples.

### 4.2 Mutações — reuso (+1 adição)

100% das regras de domínio são reusadas; a **única** adição de mutação é um setter fino.

| Ação | Serviço | Commit? |
|------|---------|---------|
| Criar/editar obra | `obra_service.upsert_obra` (existe; só **flush**) | **rota commita** |
| Ativar/desativar obra | `obra_service.set_status` (**novo** setter fino sobre `Obra.status`) | **rota commita** |
| Resolver `pending_obra` | `entrada_service.resolve_pending_obra` (existe; **commita internamente**) | rota **não** commita |
| Aprovar/reprovar documento | `approval_service.approve_document` (existe; **commita internamente**) | rota **não** commita |

### 4.3 Responsabilidade de commit (explícita)

- `obra_service.upsert_obra` só faz `flush` (`src/services/obra_service.py:19-40`); o novo `set_status` idem. As rotas de **criar/editar/toggle de obra** devem `await session.commit()` após chamar o serviço (espelha o que a rota `/api/v1/obras` já faz).
- `entrada_service.resolve_pending_obra` e `approval_service.approve_document` **commitam internamente** — as rotas correspondentes **não** devem commitar de novo (evita double-commit).

### 4.4 Assinaturas a respeitar

- `entrada_service.resolve_pending_obra(session, *, entrada_id: uuid.UUID, obra_id: str)` — keyword-only; `entrada_id` é `uuid.UUID`. O path param admin `{entrada_id}` deve ser tipado `uuid.UUID` (igual a `src/api/routes/entradas.py:18`). Retorna **dict de status** (`{"status": "not_found"|"obra_not_found"|"queued"|...}`), não levanta — a rota traduz cada caso (`not_found`/`obra_not_found` → erro PT no fragmento; `queued` → fragmento de sucesso). No sucesso chama `enqueue_entrada` (Redis) — o teste mocka isso (§8).
- `approval_service.approve_document(session, *, documento_id: str, aprovado: bool, aprovador: str, comentario: str | None = None)` — keyword-only; `documento_id` é `str` (convertido a UUID internamente). Form admin envia `aprovado` (bool), `aprovador` (string; default "engenheiro" em `ApprovalRequest`) e `comentario` opcional. **Não** há gate: seta `status` para `APROVADO`/`REPROVADO` incondicionalmente e grava uma `Aprovacao`.
- `obra_service.upsert_obra` usa `payload.id` como PK (`ObraCreate.id`, pattern `^[A-Z0-9][A-Z0-9_-]*$`, `src/schemas/obras.py:17`); `slug` é regenerado de `nome`. No **editar**, o `id` é renderizado read-only/hidden — trocar `id` criaria uma obra nova (não suportado no v1).

## 5. Páginas e rotas

Templates em `src/templates/admin/` (`base.html` com `<script src="/admin/static/htmx.min.js">` + navbar; uma página por área + parciais por mutação).

**Convenção de resposta (única, explícita):**
- **Mutações** (`POST`) retornam **200 + parcial HTML** que o HTMX faz swap (a *rota* renderiza o parcial a partir do dict do serviço — os serviços retornam dict, não HTML). Parciais: `admin/_obra_row.html`, `admin/_entrada_resolver.html`, `admin/_aprovacao_panel.html`.
- **Redirect de página inteira** (303 / `HX-Redirect`) só em `login`/`logout`.
- **Páginas GET** (incl. filtros `?status=`) retornam **página completa** em navegação direta; se o header `HX-Request` estiver presente, retornam só o parcial da tabela de resultados.

| Rota | Método | Função |
|------|--------|--------|
| `/admin/login` | GET/POST | Form de login (sem guard). |
| `/admin/logout` | POST | Encerra sessão. |
| `/admin` | GET | Dashboard com contadores (§4.1). |
| `/admin/obras` | GET | Lista de obras. |
| `/admin/obras/nova` | GET/POST | Criar obra (`upsert_obra` + commit). |
| `/admin/obras/{id}/editar` | GET/POST | Editar obra (`upsert_obra` + commit; `id` read-only). |
| `/admin/obras/{id}/status` | POST | Toggle ativar/desativar (`set_status` + commit; swap `_obra_row`). |
| `/admin/entradas` | GET | Lista filtrável por `?status=` ∈ {`received`,`processing`,`completed`,`failed`,`pending_obra`}. |
| `/admin/entradas/{entrada_id}` | GET | Detalhe: payload bruto (escapado em `<pre>`), origem, autor, obra, data, resultado. |
| `/admin/entradas/{entrada_id}/resolver-obra` | POST | `<select>` de obras → `resolve_pending_obra` (sem commit na rota; swap `_entrada_resolver`). |
| `/admin/documentos` | GET | Lista filtrável por `?status=` ∈ valores de `DocumentStatus` (MAIÚSCULOS). |
| `/admin/documentos/{documento_id}` | GET | Detalhe: documento + triagem estruturada. |
| `/admin/documentos/{documento_id}/aprovar` | POST | Aprovar/reprovar (`approve_document`, sem commit na rota; swap `_aprovacao_panel`). |

**Filtro de entradas:** o conjunto válido é `{received, processing, completed, failed, pending_obra}` — `queued` **não** é status de `EntradaBruta` (é `TaskStatus`/chave de resposta de `ingest_telegram`); um `?status=queued` retornaria sempre vazio, então não é oferecido. A tela `pending_obra` é destacada no dashboard e acessível via `?status=pending_obra`.

**Filtro de documentos:** valores aceitos são os membros MAIÚSCULOS de `DocumentStatus` (StrEnum, `src/core/constants.py:6-19`: `RECEBIDO`, `TRIADO`, `PROCESSADO`, `RASCUNHO_GERADO`, `EM_REVISAO`, `APROVADO`, `REPROVADO`, `CORRIGIDO`, `FINALIZADO_VALIDADO`, `PUBLICADO_BUCKET`, `CANCELADO`, `SUBSTITUIDO`, `ERRO_PROCESSAMENTO`). O `<select>` do filtro é populado de `list(DocumentStatus)`; valores inválidos são ignorados com mensagem PT (sem case-folding implícito).

## 6. Erros e segurança

- Mensagens de usuário/erro em PT, consistentes com `src/core/errors.py`.
- Cookie de sessão `HttpOnly` (default do middleware); `Secure` em produção (`https_only`); `SameSite=Lax` em todos os ambientes.
- Nenhuma rota `/admin/*` acessível sem `require_admin_session` (exceto `GET/POST /admin/login`) — guard via `raise` (§3.4).
- Nenhuma mutação em GET; handlers POST checam `Origin`/`Referer` same-origin.
- Chave de assinatura de sessão nunca vazia em produção (fail-closed em `create_app`).
- Autoescape Jinja ligado; `raw_payload`/`author` renderizados escapados (§2.2).
- O painel não acessa o banco fora dos serviços/sessão async já usados pela API (`Depends(get_db)`).

## 7. Mudanças de código necessárias

1. `src/config/env.py`: novas settings `admin_password: str = ""` e `session_secret: str = ""`.
2. `pyproject.toml` + `uv.lock`: adicionar `itsdangerous` (requisito do `SessionMiddleware`; `starlette` é transitivo via `fastapi`, ok). `python-multipart` e `jinja2` já presentes.
3. `src/services/obra_service.py`: novo `set_status(session, obra_id, status)` (setter fino, só flush).
4. `src/services/admin_service.py`: novo (leituras §4.1).
5. `src/api/routes/admin.py`: novo router `/admin` + `Jinja2Templates` + parciais.
6. `src/api/server.py`: `app.add_middleware(SessionMiddleware, ...)`, `app.mount("/admin/static", StaticFiles(...))`, `include_router(admin_router)` (fora de `protected_dependencies`), handler de `AdminLoginRequired`.
7. `src/core/errors.py`: exceção `AdminLoginRequired`.
8. `src/templates/admin/`: `base.html` + páginas + parciais. `src/static/admin/htmx.min.js` vendorizado.

## 8. Testes (pytest, estilo do repo)

O repo **não** tem `tests/conftest.py` nem fixture de DB real; os testes existentes usam `httpx.ASGITransport(app=create_app())` com env monkeypatchado e **services mockados** (ver `tests/test_obras.py`, `tests/test_api_auth.py`). Os testes do painel seguem esse estilo: rotas via `ASGITransport`, `admin_service`/`obra_service`/`entrada_service`/`approval_service` mockados (monkeypatch), assertando args de chamada + fragmento renderizado. `enqueue_entrada` (Redis) é mockado no teste de resolver-obra.

1. **Guard (parametrizado):** sem sessão, `GET /admin/obras` **e** `POST /admin/obras/{id}/status` → 303 redirect para `/admin/login` (cobre o critério "nenhuma rota `/admin/*` sem sessão", não só `GET /admin`).
2. **Login:** senha correta → sessão setada + redirect 303; senha errada → 200 + form com erro PT; senha efetiva vazia em prod → 500. Ordem: checagem de config antes do `compare_digest`.
3. **Smoke middleware:** `GET /admin/login` renderiza (exercita `SessionMiddleware`; pega registro ausente).
4. **Obras:** criar via form chama `upsert_obra` + `commit`; toggle chama `set_status` + `commit` e o parcial reflete o novo status.
5. **Resolver obra:** `POST .../resolver-obra` com obra válida → `resolve_pending_obra` chamado, `enqueue_entrada` mockado, fragmento de sucesso; `result["status"]` em `{not_found, obra_not_found}` → erro PT no fragmento. Rota **não** commita.
6. **Aprovação:** `POST .../aprovar` com `aprovado=true` → `Documento.status=APROVADO` + `Aprovacao` gravada; `aprovado=false` → `REPROVADO`. (Sem "gate"; status setado incondicionalmente por `approve_document`.) Rota **não** commita.
7. **XSS:** detalhe de entrada com `raw_payload`/`author` contendo `<script>` é HTML-escapado na resposta (autoescape).
8. **Filtros:** `/admin/entradas?status=pending_obra` e `/admin/documentos?status=EM_REVISAO` retornam só o subconjunto correto; `?status=queued` (entradas) e status inválido (documentos) tratados sem erro 500.

Gate de pré-entrega (obrigatório): `make lint && make typecheck && make test`.

## 9. Fora do escopo (fase 2)

- Visualizador de auditoria (`AuditoriaEvento`).
- Multi-operador, usuários e papéis, auditoria por operador.
- Aliases/apelidos de obra para resolução automática de `pending_obra`.
- Tokens CSRF por formulário (endurecimento além de SameSite+Origin).
- Página de medições/orçamento no painel.
- Finalização de RDO / gate de publicação (`rdo_service.finalize_rdo`) — fora do escopo do painel v1.

## 10. Critérios de aceite (v1)

- Operador faz login no painel com a senha (`admin_password`, ou `obrabot_api_key` em dev) e **nenhuma** rota `/admin/*` (GET ou POST) abre sem sessão.
- Operador cadastra, edita e ativa/desativa obra (writes persistidos via commit).
- Operador lista entradas filtrando por status real e inspeciona o payload bruto (escapado).
- Operador resolve uma entrada `pending_obra` selecionando uma obra cadastrada.
- Operador visualiza documento + triagem estruturada.
- Operador aprova/reprova um documento (status → `APROVADO`/`REPROVADO`).
- Chave de sessão nunca vazia em produção; login com config vazia falha fechado (500).
- `make lint && make typecheck && make test` passam.
- Nenhuma migration nova; nenhuma rota pública nova sem autenticação.
