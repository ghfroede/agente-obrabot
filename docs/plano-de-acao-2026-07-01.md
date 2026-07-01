# Auditoria e Plano de Ação — 2026-07-01

Auditoria completa do repositório (código, arquitetura, segurança, worker, testes, CI/CD, observabilidade e documentação) com plano de ação priorizado. Substitui [project-audit-2026-06-29.md](project-audit-2026-06-29.md) como referência atual.

**Base da auditoria:** commit `f13b6aa`, branch de trabalho `claude/repo-audit-plan-msu748`. ~6.900 linhas em `src/`, 31 arquivos de teste (~163 testes), 10 migrações Alembic (head `010_medicao_periodos`).

---

## 1. Sumário executivo

O projeto tem uma **base sólida**: idempotência atômica na ingestão (`INSERT ... ON CONFLICT`), HMAC canônico com janela de replay, SQL 100% parametrizado, comparações de credenciais timing-safe, validação de secrets em produção com rejeição de placeholders, headers de segurança bem configurados, migrações encadeadas corretamente e suíte ampla de testes de serviço.

As lacunas se concentram em quatro eixos:

1. **Segurança (severidade média):** checagem same-origin do admin burlável por prefixo de host; bypass do webhook OpenClaw em configuração específica; limites de tamanho de mídia definidos mas nunca aplicados.
2. **Confiabilidade do worker:** retry do RQ pode duplicar `Documento`/`Triagem`; retries com intervalo dependem de scheduler que não está habilitado; chave de idempotência fica presa em `processing` após falha.
3. **Fundação de engenharia:** não existe CI (nenhum workflow em `.github/`); observabilidade praticamente nula (zero logging no pipeline crítico); testes 100% mockados, sem integração com banco real.
4. **Dívida técnica:** pipeline "CEO" inteiro é código morto; helpers duplicados entre 4 serviços; módulos monolíticos (`entrada_service.py`, `admin.py`).

---

## 2. Achados da auditoria

### 2.1 Segurança

#### Severidade média

| # | Achado | Evidência |
|---|--------|-----------|
| S1 | **CSRF: same-origin burlável por prefixo.** `_check_same_origin` valida `source.startswith(base)` sem delimitar o fim do host — uma Origin `https://app.com.evil.com` passa quando a base é `https://app.com`. Afeta todas as POSTs de mutação do admin. | `src/api/routes/admin.py:86` |
| S2 | **CSRF: login sem checagem same-origin.** `login_submit` não chama `_check_same_origin` (as demais POSTs chamam) — login-CSRF possível. | `src/api/routes/admin.py:125-156` |
| S3 | **Webhook OpenClaw: bypass com secret setado e `OPENCLAW_REQUIRE_HMAC=false`.** Se há secret mas HMAC não é obrigatório e a requisição chega sem header de assinatura nem `X-OpenClaw-Secret`, a condição `if require_hmac or signature` é falsa e o body é aceito **sem verificação alguma**. Só é fechado em produção porque `is_production` força `require_hmac`. Default é `false`. | `src/core/security.py:103-152`, `src/config/env.py:96` |
| S4 | **Caminho shared-secret estático sem replay/rate-limit.** Quando `X-OpenClaw-Secret` casa (fora de produção), retorna imediatamente — sem timestamp, sem dedup de `event_id`, sem rate limit. | `src/core/security.py:106-107` |
| S5 | **Limites de mídia nunca aplicados.** `max_image_bytes`/`max_audio_bytes`/`max_document_bytes` existem só na config (grep confirma zero usos). `download_file` baixa o conteúdo inteiro em memória sem cap; `persist_arquivo` grava sem validar. O limite de body do webhook cobre só o envelope JSON, não o fetch da mídia. Risco de exaustão de memória. | `src/config/env.py:108-110` vs `src/services/telegram_media_service.py:105-131`, `src/services/media_service.py:44-58` |
| S6 | **docker-compose com credenciais triviais e portas expostas.** `POSTGRES_USER/PASSWORD/DB = obrabot`; portas 5432/6379 publicadas no host; Redis sem auth. Ambiente dev, mas comitado. | `docker-compose.yml:5-9,18-19` |

#### Severidade baixa

- Rate-limit por `request.client.host` — atrás do proxy do Railway sem tratar `X-Forwarded-For`, todos os clientes compartilham o IP do proxy (`src/api/deps.py:33`, `admin.py:136`).
- CSP com `'unsafe-inline'` em `script-src`/`style-src` — necessário para HTMX/Jinja inline hoje, mas enfraquece proteção XSS (`src/api/middleware.py:10-11`).
- Pins de dependência só de piso (`>=` sem teto) em todo o `pyproject.toml` — mitigado pelo `uv.lock`, mas sem política de atualização.
- Mime/extensão de mídia sem allowlist — `mime_type` vem do payload Telegram e é persistido sem restrição (`telegram_media_service.py:90-102`).
- Vazamento fino de `str(exc)` em `detail` de erros e em `{"erro": str(exc)[:200]}` de mídia (`src/api/server.py:129-157`, `entrada_service.py:494-496`, `deps.py:26`).
- Fallback de credenciais em dev: API key vira senha do admin e session secret quando não configurados (`admin.py:52-58`, `server.py:98-100`).
- CORS default `*` com `allow_credentials=True` (`env.py:69`, `server.py:82-88`) — proibido em produção, mas permissivo por default.
- `/health` anônimo expõe status de Postgres/Redis (`src/api/routes/health.py:16-40`).

**Pontos corretos (sem achado):** SQL parametrizado em 100% dos acessos (únicos `text()` são constantes literais); `hmac.compare_digest` na API key e na senha admin; HMAC canônico `timestamp\nevent_id\nmethod\npath\nsha256(body)` com skew de ±300s e binding do `event_id` ao payload; idempotência durável via `ON CONFLICT DO NOTHING`; `validate_production_secrets` rejeita placeholders; wildcard CORS proibido em produção; docs/OpenAPI desabilitados em produção; chaves de bucket derivadas de sha256 (sem path traversal).

### 2.2 Confiabilidade do worker

| # | Achado | Evidência |
|---|--------|-----------|
| W1 | **Retry do RQ sem idempotência de reprocessamento.** Em retry, `_process` reexecuta persistência de bucket, chamadas de IA e cria **novo `Documento`/`Triagem`/`AuditoriaEvento`** — não há checagem de "já processado" além de `entrada.status`. | `src/services/entrada_service.py:358-463` |
| W2 | **Retries com intervalo podem não disparar.** `worker.work(with_scheduler=False)` — o RQ precisa do scheduler para reexecutar jobs com `Retry(interval=[...])`; sem ele os retries agendados podem nunca rodar. | `src/worker/index.py` |
| W3 | **`fail_idempotency` nunca é chamado.** Definido e documentado, mas sem chamador — em falha, a chave fica presa em `processing` e a entrada nunca pode ser reprocessada pela mesma chave. | `src/services/ingestao_service.py:119` |
| W4 | **Shutdown abrupto.** SIGTERM/SIGINT → `sys.exit(0)` imediato, sem drain do job em andamento. | `src/worker/index.py:64-67` |
| W5 | **Conexão Redis nova a cada enqueue.** `Redis.from_url` instanciado por chamada em `enqueue_entrada`; padrão repetido em 4 pontos sem factory comum. | `entrada_service.py:78`, `worker/index.py:62`, `rate_limit_service.py:37`, `health.py:31` |

### 2.3 Código morto e dívida técnica

| # | Achado | Evidência |
|---|--------|-----------|
| D1 | **Pipeline "CEO" inteiro é código morto.** `process_task` chama `run_ceo_pipeline`, mas nunca é enfileirado — o único `queue.enqueue` do código enfileira `process_entrada`. Em cascata: `src/agent/ceo.py`, `persist_raw_entry` em `src/storage/s3.py`, e o engine **sync** de `src/db/client.py` só servem a esse caminho. A `Task` criada em `POST /tasks` só avança via `_mark_task` do pipeline de `EntradaBruta`. | `src/worker/index.py:19`, `src/agent/ceo.py:10`, `entrada_service.py:85-89` |
| D2 | **Helpers duplicados (copy-paste):** `_get_obra` em 4 serviços (`orcamento_service.py:18`, `rdo_service.py:42`, `foto_service.py:32`, `medicao_service.py:47`); `_get_documento` em 3 (`rdo_service.py:50`, `foto_service.py:40`, `approval_service.py:16`); `_jinja_env` e `_require_approval` idênticos em `rdo_service.py` e `foto_service.py`. | — |
| D3 | **`entrada_service.py` como hub de acoplamento** (648 linhas): importa 8 serviços + Redis/RQ; `_process` tem ~105 linhas fazendo bucket + mídia + IA + persistência; `_build_reply` embute comandos de UX Telegram (`/gerar_rdo`, `/aprovar_rdo`…) na camada de domínio. | `entrada_service.py:19-28,358-463,608-640` |
| D4 | **`admin.py` monolítico** (593 linhas, ~17 endpoints): auth de sessão + renderização HTMX + orquestração de 6+ serviços num único router. | `src/api/routes/admin.py` |
| D5 | **Dependências definidas e não usadas:** `DbSession`/`ApiKeyDep` em `src/api/deps.py:42-43` sem uso; `tasks.py` e `health.py` importam `get_async_session` direto enquanto o resto usa `get_db` — dois caminhos para a mesma coisa. | — |
| D6 | **Propriedade de transação dividida:** serviços que recebem `AsyncSession` commitam internamente (`orcamento_service.py:244`, `rdo_service.py:201`, etc.) enquanto rotas também commitam (`tasks.py:80`, `admin.py:220`) — sem padrão único; `_finalize_approved_rdo` precisou do parâmetro `commit: bool` para contornar. | `rdo_service.py:302` |
| D7 | **`sync_database_url` frágil:** deriva da URL async com dupla substituição de string dependente de prefixos exatos. | `src/config/env.py:157-161` |

### 2.4 Observabilidade

| # | Achado | Evidência |
|---|--------|-----------|
| O1 | **Zero logging no pipeline crítico.** Nenhum logger em `src/worker/`, `src/agent/` e `entrada_service.py`. Só 3 módulos em todo `src/` instanciam logger (`security.py`, `rate_limit_service.py`, `pdf_service.py`). | grep confirmado |
| O2 | **Sem configuração central de logging** — nenhum `dictConfig`/`basicConfig`; nível efetivo default (WARNING), sem formato estruturado/JSON. | — |
| O3 | **Handlers de exceção não logam e falta handler genérico.** Os handlers tipados retornam `detail` sem logar; `Exception` não prevista vira 500 sem registro. | `src/api/server.py:129-157` |
| O4 | **Falhas persistidas sem stack trace.** Worker grava `str(exc)[:500]` em `Task.error`/`EntradaBruta` — diagnóstico limitado. | `worker/index.py:15-16`, `entrada_service.py:347` |
| O5 | **Sem métricas nem error tracking** (Prometheus/OTel/Sentry ausentes). `/health` não checa S3 e reinstancia conexão Redis por chamada. | `health.py:31` |
| O6 | **Swallow silencioso:** `_send_reply` faz `except Exception: return` sem log. | `entrada_service.py:647` |

### 2.5 Testes e CI/CD

| # | Achado | Evidência |
|---|--------|-----------|
| T1 | **CI inexistente.** Não há `.github/` — ruff, mypy, pytest e `pip-audit` rodam apenas manualmente via Makefile. Sem Dependabot/Renovate, sem gate de cobertura (`pytest-cov` não está nas dev-deps), sem pre-commit. | — |
| T2 | **Testes 100% mockados.** Rotas testadas com `app.dependency_overrides[get_db]` + `AsyncMock`; nenhum teste toca Postgres real; **migrações Alembic sem teste** de upgrade; não há `conftest.py` (fixtures repetidos por arquivo). | ex.: `tests/test_admin_routes.py:33-36` |
| T3 | **Serviços sem teste unitário:** `audit_service`, `bucket_service`, `openai_service`, `pdf_service` (geração de PDF nunca exercitada), `rdo_service` (só indireto via `test_approval_gate.py`). | — |
| T4 | **Rotas de domínio sem teste HTTP:** `documentos.py`, `fotos.py`, `orcamento.py`, `medicoes.py`, `entradas.py`, `triagem.py`, `telegram_contextos.py` — testadas só no nível de serviço, nunca via cliente HTTP com os exception handlers reais. | — |
| T5 | **Worker quase sem cobertura:** `process_entrada` e o loop `main()` (RQ Worker, sinais) sem teste; caminho de erro de `process_task` não exercitado. | `src/worker/index.py:37-45,55-71` |

**Pontos corretos:** fluxos de aprovação bem cobertos (`test_approval_gate.py`, 451 linhas); admin bem coberto (4 arquivos); bons smoke tests E2E manuais em `scripts/` (compensam parcialmente a falta de integração — mas exigem execução manual).

### 2.6 Documentação

- `docs/project-audit-2026-06-29.md` desatualizado: reporta 70 testes (hoje ~163) e aponta P0/P1 já resolvidos (ex.: agregador diário de RDO, já implementado em `rdo_aggregator_service.py`).
- `README.md:9` diz "Python 3.12" enquanto `pyproject.toml` declara `requires-python = ">=3.11"` e mypy `python_version = "3.11"` — alvo de versão inconsistente.
- `README.md:96` afirma "134+ testes" (real ≈163); rota `GET /api/v1/rdo/rascunho` existe e não está listada na tabela de endpoints.
- Inconsistência menor nas migrações: id de revisão nem sempre bate com o nome do arquivo (ex.: `008_link_entries_and_operational_metadata.py` → `revision = "008_operational_links"`).

---

## 3. Plano de ação priorizado

Esforço: **P** (≤ meio dia), **M** (1–2 dias), **G** (3+ dias). Cada fase tem critério de conclusão. Recomendação: um PR por item (ou por par de itens pequenos correlatos), seguindo a convenção de diffs mínimos do repositório.

### P0 — Segurança e confiabilidade (fazer primeiro)

| Item | Ação | Arquivos | Esforço |
|------|------|----------|---------|
| P0.1 (S1, S2) | Corrigir `_check_same_origin`: comparar scheme+host+porta exatos (parsear com `urllib.parse.urlsplit` em vez de `startswith`); aplicar a checagem também em `login_submit`. Adicionar testes de bypass por prefixo. | `src/api/routes/admin.py`, `tests/test_admin_auth.py` | P |
| P0.2 (S3, S4) | Fechar o bypass do webhook: quando `openclaw_shared_secret` está configurado, **sempre** exigir uma das verificações (HMAC ou shared-secret) — nunca aceitar requisição sem credencial. Avaliar mudar default de `OPENCLAW_REQUIRE_HMAC` para `true`. Aplicar dedup de `event_id` também no ramo shared-secret. | `src/core/security.py`, `src/config/env.py`, `tests/test_security_openclaw.py` | P |
| P0.3 (S5) | Aplicar `max_image_bytes`/`max_audio_bytes`/`max_document_bytes`: validar `Content-Length`/tamanho no `download_file` (streaming com cap) e em `persist_arquivo` antes de gravar. Registrar mídia rejeitada por tamanho no resultado da entrada. | `src/services/telegram_media_service.py`, `src/services/media_service.py`, testes novos | M |
| P0.4 (W1) | Idempotência de reprocessamento no worker: no início de `_process`, se a `EntradaBruta` já tem `Documento`/`Triagem` associados (ou `status` avançado), pular as etapas já concluídas em vez de recriar. Tornar cada etapa do pipeline retomável. | `src/services/entrada_service.py`, `tests/test_entrada_service.py` | M |
| P0.5 (W2) | Habilitar `with_scheduler=True` no worker (ou validar empiricamente que os retries com intervalo disparam sem ele e documentar). | `src/worker/index.py` | P |
| P0.6 (W3) | Chamar `fail_idempotency` no caminho de falha de `run_entrada_pipeline`, marcando a chave como `failed` para permitir novo processamento. | `src/services/entrada_service.py`, `tests/test_idempotency*.py` | P |

**Concluído quando:** testes de bypass (same-origin com host-prefixo, webhook sem headers com secret setado) falham antes e passam depois; retry forçado de uma entrada não duplica `Documento`/`Triagem`; chave de idempotência transita para `failed` em falha; `make lint && make typecheck && make test` verde.

### P1 — Fundação de engenharia

| Item | Ação | Arquivos | Esforço |
|------|------|----------|---------|
| P1.1 (T1) | CI no GitHub Actions: workflow com `uv sync` + `ruff check` + `mypy src` + `pytest -q` + `make security-audit` em push/PR. Adicionar `dependabot.yml` (pip + actions, semanal). | `.github/workflows/ci.yml`, `.github/dependabot.yml` | P |
| P1.2 (O1–O4, O6) | Logging estruturado: configuração central (`logging.dictConfig`, JSON em produção, legível em dev) inicializada em `create_app` e no `main()` do worker; logs nos pontos-chave do pipeline (`entrada_service`, `worker/index.py`) com `entrada_id`/`obra_id`; logar exceções nos handlers de `server.py` e adicionar handler genérico de `Exception` (500 opaco ao cliente, stack trace no log); logar o swallow de `_send_reply`. | `src/core/logging.py` (novo), `src/api/server.py`, `src/worker/index.py`, `src/services/entrada_service.py` | M |
| P1.3 (T2) | Testes de integração com Postgres real: `tests/conftest.py` com fixture de engine async apontando para o Postgres do `docker-compose` (ou testcontainers), rodando `alembic upgrade head` no setup — isso também vira o teste das migrações. Migrar 2–3 fluxos críticos (ingestão idempotente, aprovação de RDO) para integração; manter o resto mockado. Marcar com `pytest.mark.integration` para o CI poder rodar com serviço Postgres. | `tests/conftest.py` (novo), `tests/integration/` (novo), `.github/workflows/ci.yml` | G |
| P1.4 (T3) | Cobertura: adicionar `pytest-cov` às dev-deps e relatório no CI (sem gate rígido inicialmente); testes unitários para `pdf_service`, `bucket_service` e `openai_service` (parsing/fallback da triagem). | `pyproject.toml`, `tests/` | M |

**Concluído quando:** PR aberto dispara CI com lint+types+testes+audit; falha de pipeline aparece em log estruturado com stack trace; `pytest -m integration` sobe schema via Alembic e passa; relatório de cobertura publicado no CI.

### P2 — Qualidade e dívida técnica

| Item | Ação | Arquivos | Esforço |
|------|------|----------|---------|
| P2.1 (D1) | Decidir e executar sobre o pipeline CEO: **remover** `process_task`, `src/agent/ceo.py`, `persist_raw_entry` e o engine sync de `db/client.py` (recomendado — o caminho vivo é `process_entrada`), ou reativar conscientemente com enqueue real. Se remover, revisar o ciclo de vida de `Task` em `POST /tasks`. | `src/worker/index.py`, `src/agent/`, `src/storage/s3.py`, `src/db/client.py` | M |
| P2.2 (D2) | Extrair helpers duplicados para módulo comum (`src/services/_shared.py` ou `src/services/common.py`): `get_obra`, `get_documento`, `require_approval`, `jinja_env`. | 5 serviços + módulo novo | P |
| P2.3 (W5) | Factory única de conexão Redis (com reuso de pool) em `src/core/` ou `src/services/`, substituindo os 4 `Redis.from_url` espalhados. | `entrada_service.py`, `worker/index.py`, `rate_limit_service.py`, `health.py` | P |
| P2.4 (D3, D4) | Refatorar módulos monolíticos: quebrar `_process` em etapas nomeadas (persistir bruto → mídia → triagem → documento); mover `_build_reply` para um módulo de apresentação Telegram; dividir `admin.py` em auth + views (sem mudar comportamento). | `entrada_service.py`, `admin.py` | G |
| P2.5 (T4, T5) | Testes HTTP para rotas de domínio (RDO gerar/aprovar-finalizar, baseline, medições) exercitando os exception handlers reais; teste do caminho de erro do worker. | `tests/` | M |
| P2.6 | Rate-limit ciente de proxy: extrair IP de `X-Forwarded-For` (primeiro hop confiável) atrás do Railway. | `src/api/deps.py`, `admin.py` | P |
| P2.7 (D5, D6) | Padronizar: todas as rotas usam `get_db` de `deps.py` (remover `DbSession`/`ApiKeyDep` mortos ou passar a usá-los); definir convenção de commit (rota comita, serviço só faz flush) e aplicar gradualmente nos serviços tocados por outros itens. | `src/api/deps.py`, rotas/serviços | M |

**Concluído quando:** grep por `run_ceo_pipeline`/`persist_raw_entry` vazio (ou pipeline reativado com teste); um único ponto de criação de conexão Redis; nenhum helper `_get_obra` duplicado; suíte verde.

### P3 — Higiene

| Item | Ação | Arquivos | Esforço |
|------|------|----------|---------|
| P3.1 | Atualizar README: versão de Python única e consistente com `pyproject.toml` (alinhar `requires-python`, mypy e `.python-version`), contagem de testes, incluir `GET /api/v1/rdo/rascunho`. | `README.md`, `pyproject.toml` | P |
| P3.2 | Adicionar nota "superado por plano-de-acao-2026-07-01.md" no topo da auditoria antiga. | `docs/project-audit-2026-06-29.md` | P |
| P3.3 | Política de dependências: manter `>=` + `uv.lock` como fonte de verdade, com Dependabot (P1.1) cuidando das atualizações; documentar em `SECURITY.md`. Avaliar trocar `psycopg2-binary` por `psycopg2` no deploy (ou remover junto com o engine sync em P2.1). | `SECURITY.md`, `pyproject.toml` | P |
| P3.4 | Hardening do compose dev: senha não trivial via `.env`, bind das portas em `127.0.0.1`, `requirepass` no Redis. | `docker-compose.yml`, `.env.example` | P |
| P3.5 | Endurecer mensagens de erro ao cliente: `detail` genérico em 500 de config; manter detalhe apenas no log (depende de P1.2). | `src/api/deps.py`, `admin.py`, `entrada_service.py` | P |

---

## 4. Sequência sugerida

1. **Semana 1:** P0 completo + P1.1 (CI) — o CI primeiro garante que todo o resto entra com gate automático.
2. **Semana 2:** P1.2 (logging) e P1.4 (cobertura); iniciar P1.3 (integração).
3. **Semanas 3–4:** P2 (começando por P2.1 código morto e P2.2 dedup, que reduzem a superfície antes dos refactors maiores P2.4).
4. **Contínuo:** P3 pode ser intercalado a qualquer momento (itens de baixo risco).

## 5. O que **não** fazer agora

- Migrar de RQ para outra fila, trocar xhtml2pdf ou reescrever o admin em SPA — a arquitetura atual atende o MVP; o custo/benefício não justifica antes de fechar P0/P1.
- Gate rígido de cobertura no CI no primeiro momento — primeiro medir, depois definir piso.
- Refatoração ampla de transações (D6) num PR único — aplicar a convenção incrementalmente nos arquivos já tocados por outros itens.
