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
```

## Redeployar

```bash
railway up -s api --detach -m "Redeploy API"
railway up -s worker --detach -m "Redeploy worker"

# Verificar deployment
railway deployment list --json
```

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
railway variable set OPENAI_API_KEY=sk-... --service worker
railway variable set OPENAI_API_KEY=sk-... --service api  # se necessário

# S3 / MEGA S4
railway variable set S3_ENDPOINT_URL=... --service worker
railway variable set S3_ACCESS_KEY_ID=... --service worker
railway variable set S3_SECRET_ACCESS_KEY=... --service worker
railway variable set S3_BUCKET_NAME=bucket-construtora --service worker
```

Referencie `DATABASE_URL` e `REDIS_URL` das variáveis dos serviços Postgres/Redis no dashboard.

## Diagnosticar erros comuns

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| `/health` 503 postgres | `DATABASE_URL` incorreta ou migration pendente | Verificar referência + `alembic upgrade head` |
| `/health` 503 redis | `REDIS_URL` incorreta | Referenciar Redis service |
| Task stuck em `queued` | Worker offline | Logs worker, verificar Redis |
| Task `failed` | LLM timeout ou S3 error | Ver `error` em GET /tasks/:id |
| Crash loop API | Porta errada | Usar `$PORT`, host `0.0.0.0` |
| Worker SIGTERM | Deploy rolling | Normal; RQ re-enfileira job não ack |

## Graceful shutdown

O worker registra handlers para SIGTERM/SIGINT (Railway envia SIGTERM em deploys). Jobs em processamento devem completar ou falhar com status `failed` no banco.

## Backup

- Postgres: backups gerenciados pelo Railway (ver docs PostgreSQL Railway)
- Bucket MEGA S4: política de versionamento REV00/REV01 no app (plano-01)
