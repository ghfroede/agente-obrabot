# Operações — Obrabot

## Rodar localmente

```bash
docker compose up -d
cp .env.example .env
uv sync
make db-migrate
make dev-api    # terminal 1
make dev-worker # terminal 2
```

## Executar migrations

```bash
# Local
make db-migrate

# Ou diretamente
uv run alembic upgrade head

# Produção (Railway)
# Configurado em railway.api.json preDeployCommand
```

## Ver logs

```bash
# Local — stdout dos processos dev-api / dev-worker

# Railway
railway logs --service api --lines 200
railway logs --service worker --lines 200
railway logs --service OpenClaw --lines 200
```

## Redeployar

```bash
railway up -s api --detach -m "Redeploy API"
railway up -s worker --detach -m "Redeploy worker"
railway service redeploy OpenClaw

# Verificar deployment
railway deployment list --json
```

## OpenClaw no Railway

O serviço `OpenClaw` roda no mesmo projeto Railway, com domínio HTTPS próprio, proxy HTTP na porta `8080` e volume persistente montado em `/data`.

Variáveis esperadas no serviço `OpenClaw`:

- `OBRABOT_API_URL=https://<api-domain>`
- `OPENCLAW_SHARED_SECRET` referenciando `api.OPENCLAW_SHARED_SECRET`
- `TELEGRAM_BOT_TOKEN` referenciando `worker.TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY` referenciando `worker.OPENAI_API_KEY`
- `OPENCLAW_STATE_DIR=/data/.openclaw`
- `OPENCLAW_WORKSPACE_DIR=/data/workspace`
- `OPENCLAW_GATEWAY_PORT=8080`
- `SETUP_PASSWORD` e `OPENCLAW_GATEWAY_TOKEN` gerados no Railway

Não configure `DATABASE_URL`, `REDIS_URL` nem `S3_*` no OpenClaw. Ele deve chamar apenas a API pública do Obrabot com HMAC.

Setup inicial:

```bash
# Acesse pelo navegador:
https://<openclaw-domain>/setup
```

O wizard é protegido por `SETUP_PASSWORD`, disponível nas variáveis do serviço `OpenClaw` no dashboard Railway. Não copie esse segredo para arquivos do repositório.

Validação do contrato OpenClaw → Obrabot:

```bash
railway run --service api uv run python scripts/smoke_openclaw.py https://<api-domain>
```

Esse smoke usa `OPENCLAW_SHARED_SECRET` e a allowlist Telegram do serviço `api`, assina o payload com HMAC e espera `202 Accepted`. O worker deve concluir `process_entrada` logo depois.

## Escalar worker

1. Railway Dashboard → serviço `worker` → Settings → Replicas
2. Ou horizontal scaling na documentação Railway
3. Todos os replicas consomem a mesma fila Redis `obrabot`

## Alterar modelo LLM

```bash
railway variable set OPENAI_MODEL=gpt-4o --service worker
railway variable set LLM_BASE_URL=https://api.openai.com/v1 --service worker
```

Reinicie/redeploy o worker após alterar variáveis.

## Configurar secrets

```bash
# Nunca commitar .env com valores reais
railway variable set OBRABOT_API_KEY=... --service api
railway variable set CORS_ORIGIN=https://api-production-8bfb.up.railway.app --service api
railway variable set API_MAX_BODY_BYTES=10485760 --service api
railway variable set ADMIN_LOGIN_MAX_BODY_BYTES=16384 --service api
railway variable set RATE_LIMIT_PROTECTED_PER_MINUTE=120 --service api
railway variable set RATE_LIMIT_EXPENSIVE_PER_MINUTE=20 --service api
railway variable set OPENAI_API_KEY=sk-... --service worker
railway variable set OPENAI_API_KEY=sk-... --service api  # se necessário

# HMAC OpenClaw — OBRIGATÓRIO em produção
railway variable set OPENCLAW_SHARED_SECRET=... --service api
railway variable set OPENCLAW_REQUIRE_HMAC=true --service api
railway variable set WEBHOOK_MAX_BODY_BYTES=10485760 --service api

# OpenClaw deve referenciar o mesmo segredo do api, não duplicar manualmente
railway variable set OBRABOT_API_URL=https://<api-domain> --service OpenClaw

# S3 / MEGA S4
railway variable set S3_ENDPOINT_URL=... --service worker
railway variable set S3_ACCESS_KEY_ID=... --service worker
railway variable set S3_SECRET_ACCESS_KEY=... --service worker
railway variable set S3_BUCKET_NAME=bucket-construtora --service worker

# RQ worker — ajuste se LLM/S3 demorarem mais que o padrão
railway variable set RQ_JOB_TIMEOUT_SECONDS=900 --service api
railway variable set RQ_RETRY_MAX=3 --service api
railway variable set RQ_RETRY_INTERVALS_SECONDS=30,120,300 --service api
```

Referencie `DATABASE_URL` e `REDIS_URL` das variáveis dos serviços Postgres/Redis no dashboard.

Com `APP_ENV=production` ou `NODE_ENV=production`, a API não publica `/docs`, `/redoc` nem `/openapi.json`.
O boot da API também falha se `OBRABOT_API_KEY`, `OPENCLAW_SHARED_SECRET`,
`SESSION_SECRET` ou `ADMIN_PASSWORD` estiverem ausentes ou com placeholders
conhecidos como `change-me-in-production`, `secret`, `password` ou `sk-your-*`.

Em todas as respostas, a API adiciona headers de segurança (`X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` e CSP). Em
produção, `Strict-Transport-Security` só é emitido quando a requisição chega como
HTTPS ou com `X-Forwarded-Proto: https`, que é o caso esperado atrás do proxy do
Railway.

## Painel admin interno

Painel server-rendered no serviço `api`, em `/admin` (login em `/admin/login`). Prod: `https://api-production-8bfb.up.railway.app/admin`.

Variáveis **obrigatórias** no serviço `api` (ausência derruba a `api` — fail-closed):

- `ADMIN_PASSWORD` — senha de login (comparada com `hmac.compare_digest`)
- `SESSION_SECRET` — chave do cookie de sessão assinado

```bash
railway variables --service api --set "ADMIN_PASSWORD=..."
railway variables --service api --set "SESSION_SECRET=..."
```

Login tem rate-limit por IP (`ADMIN_LOGIN_MAX_PER_MINUTE`, padrão `5`). Para rotacionar a senha, basta atualizar a variável e redeployar:

```bash
railway variables --service api --set "ADMIN_PASSWORD=..."
```

## Rate limits da API

Rate limits ficam no serviço `api` e usam Redis. As políticas atuais são:

| Escopo | Variáveis | Default |
|--------|-----------|---------|
| OpenClaw | `RATE_LIMIT_USER_PER_MINUTE`, `RATE_LIMIT_CHAT_PER_MINUTE` | `30`, `120` |
| Login admin | `ADMIN_LOGIN_MAX_PER_MINUTE` | `5` |
| Rotas protegidas leves | `RATE_LIMIT_PROTECTED_PER_MINUTE` | `120` |
| Rotas protegidas caras | `RATE_LIMIT_EXPENSIVE_PER_MINUTE` | `20` |

Rotas caras incluem `/tasks`, `/api/v1/triagem/classificar`, geração/finalização
de RDO e relatório fotográfico, importação de orçamento/cronograma, baseline e
medições. Quando o limite é excedido, a API retorna `429` e registra log com IP,
rota e fingerprint da API key, nunca a chave bruta.

## Auditoria de dependências

Antes de releases e após mudanças em `pyproject.toml` ou `uv.lock`, rode:

```bash
make security-audit
```

Sem `make`:

```bash
uv run python scripts/audit_dependencies.py
```

O comando exporta o lockfile sem dependências de desenvolvimento e executa
`uvx pip-audit --strict`. Resultado diferente de zero deve bloquear deploy até
triagem do achado.

## Cadastrar obras iniciais

Antes de usar o Telegram em operação real, cadastre pelo menos uma obra. As rotas de obras são administrativas e exigem `X-Obrabot-API-Key`; portanto, `OBRABOT_API_KEY` precisa estar definida no serviço `api`.

```bash
railway variable set OBRABOT_API_KEY=... --service api
```

Exemplo em PowerShell:

```powershell
$env:OBRABOT_API_KEY="..."
$headers = @{
  "Content-Type" = "application/json"
  "X-Obrabot-API-Key" = $env:OBRABOT_API_KEY
}

Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/obras" `
  -Headers $headers `
  -Body '{"id":"OBRA-001","nome":"Nome da Obra"}'

Invoke-RestMethod `
  -Method Get `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/obras" `
  -Headers $headers
```

Também é possível usar o script operacional:

```bash
OBRABOT_API_URL=https://api-production-8bfb.up.railway.app \
OBRABOT_API_KEY=... \
uv run python scripts/seed_obras.py OBRA-001 "Nome da Obra"
```

Enquanto houver apenas uma obra operacional, cadastre também um contexto Telegram para que o backend resolva a obra mesmo quando o OpenClaw não preencher `obra_id`.

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/telegram-contextos" `
  -Headers $headers `
  -Body '{"chat_id":-1001234567890,"obra_id":"OBRA-001","papel":"engenheiro","status":"ativo"}'
```

Para supergrupos com tópicos, preencha `thread_id`:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/telegram-contextos" `
  -Headers $headers `
  -Body '{"chat_id":-1001234567890,"thread_id":42,"obra_id":"OBRA-001","papel":"engenheiro","status":"ativo"}'
```

Ordem de resolução de obra no webhook:

1. `obra_id` vindo do payload OpenClaw.
2. Prefixo no texto/caption, como `OBRA-001: concretagem concluída`.
3. Contexto ativo por `chat_id + thread_id`.
4. Contexto ativo raiz por `chat_id`.
5. `pending_obra` quando nada resolver.

Quando uma mensagem chegar sem obra clara, o webhook retorna `status=pending_obra`, salva `EntradaBruta`/`TelegramMessage` sem gerar documento oficial e lista as obras ativas. Após confirmação humana, resolva a pendência:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/entradas/<entrada_id>/resolver-obra" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001"}'
```

Essa chamada vincula a entrada à obra e enfileira o processamento assíncrono.

## Gerar RDO do dia

Pelo painel admin:

1. Acesse `/admin/dia-obra`.
2. Selecione obra e data.
3. Revise entradas, triagens, fotos, áudios, documentos brutos e pendências do dia.
4. Clique em **Gerar RDO** para criar o rascunho e abrir o detalhe do documento.

O rascunho segue o fluxo normal de validação humana em `/admin/documentos/<documento_id>`. No detalhe do documento, use **Complementos do RDO** para preencher clima, equipe, equipamentos, observações e complementos do engenheiro; ao salvar, o backend atualiza `metadata_json`, regenera o HTML do rascunho e mantém o status em revisão antes da aprovação. Depois da aprovação, use **Finalizar RDO PDF** no próprio detalhe para gerar o PDF final, publicar em `05_RDO/finalizados_pdf/` e atualizar o status para `FINALIZADO_VALIDADO`.

Pela API:

Depois que as entradas do dia estiverem processadas, gere um rascunho de RDO a partir das evidências persistidas:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/rdo/gerar" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","data_ref":"2026-06-29"}'
```

O backend agrega `EntradaBruta`, `Triagem`, `Arquivo`, `Foto` e `AudioTranscricao` por `obra_id + data_ref`, gera o conteúdo estruturado e chama o fluxo existente de rascunho. O documento gerado guarda `source_entrada_ids`, `source_arquivo_ids` e `campos_editaveis` em `metadata_json` para revisão humana antes de aprovação/finalização.

Para aprovar e finalizar pelo fluxo conversacional do Telegram/OpenClaw, use o comando `/aprovar_rdo <documento_id>` somente depois de uma aprovação humana explícita. O OpenClaw deve chamar a API em uma única operação:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/rdo/aprovar-finalizar" `
  -Headers $headers `
  -Body '{"documento_id":"<documento_id>","aprovador":"Engenheiro Responsável","comentario":"Aprovado no Telegram"}'
```

Essa chamada cria o registro de aprovação, gera o PDF final, publica em `05_RDO/finalizados_pdf/` e retorna `status=FINALIZADO_VALIDADO`. Se a aprovação já tiver sido registrada por outro caminho, use `POST /api/v1/rdo/finalizar`.

Smoke E2E RDO:

```bash
railway run --service api uv run python scripts/smoke_rdo.py
# ou: make smoke-rdo-railway
```

## Relatório fotográfico

Pela API:

```powershell
# Gerar rascunho
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/fotos/relatorio" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","periodo_inicio":"2026-06-01","periodo_fim":"2026-06-15"}'

# Aprovar e publicar PDF
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/fotos/relatorio/aprovar-finalizar" `
  -Headers $headers `
  -Body '{"documento_id":"<uuid>","aprovador":"Engenheiro"}'
```

No Telegram: `/gerar_relatorio_foto OBRA-001 hoje hoje` e `/aprovar_relatorio_foto <documento_id>`.

Smoke E2E:

```bash
railway run --service api uv run python scripts/smoke_foto.py
```

## Orçamento, cronograma e baseline

Importar orçamento:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/orcamento/importar" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","itens":[{"codigo":"03.02.001","descricao":"Concretagem","unidade":"m3","quantidade":10,"valor_unitario":1000}]}'
```

Importar cronograma (aceita `inicio_planejado`/`fim_planejado`):

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/cronograma/importar" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","atividades":[{"codigo":"ATV-001","nome":"Estrutura","inicio_planejado":"2026-06-01","fim_planejado":"2026-06-30","codigo_orcamento":"03.02.001"}]}'
```

Validar e aprovar baseline:

```powershell
Invoke-RestMethod -Method Post -Uri ".../api/v1/baseline/validar" -Headers $headers -Body '{"obra_id":"OBRA-001"}'
Invoke-RestMethod -Method Post -Uri ".../api/v1/baseline/aprovar" -Headers $headers -Body '{"obra_id":"OBRA-001","aprovador":"Engenheiro"}'
```

Listar dados importados: `GET /api/v1/orcamento/{obra_id}`, `GET /api/v1/cronograma/{obra_id}`.

Registrar e fechar medição:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/medicoes" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","periodo_ref":"2026-06","itens":[{"codigo_orcamento":"03.02.001","quantidade":5,"valor":5000}]}'

Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/medicoes/fechar" `
  -Headers $headers `
  -Body '{"obra_id":"OBRA-001","periodo_ref":"2026-06","aprovador":"Engenheiro"}'
```

Medições exigem orçamento previamente importado. O fechamento é bloqueado quando houver item sem orçamento, quantidade negativa ou período já fechado.

Smoke E2E:

```bash
railway run --service api uv run python scripts/smoke_orcamento.py
```

No PowerShell (sem `make`):

```powershell
railway run --service api uv run python scripts/smoke_orcamento.py
```

## Smoke tests (resumo)

| Script | Valida |
|--------|--------|
| `scripts/smoke_prod.py` | Health + OpenClaw + worker |
| `scripts/smoke_openclaw.py` | Webhook HMAC |
| `scripts/smoke_rdo.py` | RDO gerar + aprovar PDF |
| `scripts/smoke_foto.py` | Relatório fotográfico E2E |
| `scripts/smoke_orcamento.py` | Orçamento + cronograma + baseline |

Todos usam `OBRABOT_API_KEY`; OpenClaw smoke usa `OPENCLAW_SHARED_SECRET` via `railway run --service api`.

## Estrutura de dados e bucket

O pipeline mantém rastreabilidade explícita entre `EntradaBruta`, `Arquivo`, `Documento` e `Triagem` por `entrada_id`. A migration `008_operational_links` adiciona esses vínculos, além de `data_ref` e `metadata_json` em `entradas_brutas`. A migration `009_telegram_contextos` adiciona o mapeamento canônico de Telegram para obra. A migration `010_medicao_periodos` adiciona períodos formais de medição e vínculo opcional dos lançamentos a esses períodos.

Após deploy do backend que contém essa migration, aplique:

```bash
railway run --service api uv run alembic upgrade head
```

A organização do MEGA S4/S3 está documentada em `docs/storage-taxonomy.md`. O guia de uso para o engenheiro está em `docs/guia-engenheiro.md`.

## Diagnosticar erros comuns

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| `/health` 503 postgres | `DATABASE_URL` incorreta ou migration pendente | Verificar referência + `alembic upgrade head` |
| `/health` 503 redis | `REDIS_URL` incorreta | Referenciar Redis service |
| Rotas HTTP retornam `401` | `X-Obrabot-API-Key` ausente/incorreto | Enviar header com `OBRABOT_API_KEY`; `/health` e OpenClaw não usam esse header |
| Rotas HTTP retornam `500` com `OBRABOT_API_KEY` | Variável ausente na `api` | Definir `OBRABOT_API_KEY` no serviço `api` |
| Rotas HTTP retornam `413` | Body maior que `API_MAX_BODY_BYTES`, `ADMIN_LOGIN_MAX_BODY_BYTES` ou `WEBHOOK_MAX_BODY_BYTES` | Reduzir payload ou ajustar o limite no serviço `api` |
| Rotas HTTP retornam `429` | Rate limit excedido | Ver logs da API; ajustar quota se for uso legítimo |
| Task / `EntradaBruta` stuck em `queued`/`received` | Worker offline | Logs worker, verificar Redis |
| OpenClaw responde `202` mas nada acontece | Worker offline / fila parada | Ver `EntradaBruta.status` no banco + logs worker |
| Task `failed` ou `EntradaBruta.status=failed` | LLM timeout ou S3 error | Ver `error` em `GET /tasks/:id` / logs worker |
| OpenClaw `401` | HMAC/timestamp/`X-Event-Id` inválido ou uso de `X-OpenClaw-Secret` em produção | Conferir assinatura canônica e relógio (±5 min) |
| OpenClaw `/setup` retorna `401` | Wizard protegido | Usar `SETUP_PASSWORD` do serviço `OpenClaw` no Railway |
| OpenClaw `configured: false` nos logs | Setup inicial ainda não concluído | Acessar `/setup` e finalizar pareamento/configuração |
| Crash loop API | Porta errada | Usar `$PORT`, host `0.0.0.0` |
| Worker SIGTERM | Deploy rolling | Normal; RQ re-enfileira job não ack |

## Graceful shutdown

O worker registra handlers para SIGTERM/SIGINT (Railway envia SIGTERM em deploys). Jobs em processamento devem completar ou falhar com status `failed` no banco.

## Backup

- Postgres: backups gerenciados pelo Railway (ver docs PostgreSQL Railway)
- Bucket MEGA S4: política de versionamento REV00/REV01 no app (plano-01)
