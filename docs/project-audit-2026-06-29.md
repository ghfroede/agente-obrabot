# Auditoria do Projeto — 2026-06-29

## Veredito

O Obrabot esta tecnicamente estavel para continuar. A auditoria identificou que o bloqueio de produto imediato era o cadastro e a resolucao de obras.

O GHF-233 tratou esse bloqueio no codigo:

- obras reais passam a ser cadastradas antes do uso por API administrativa tipada;
- OpenClaw pode enviar mensagens sem `obra_id`, que ficam em `pending_obra`;
- entradas sem obra resolvida nao entram na fila de IA e nao geram documento oficial;
- o operador pode resolver a obra depois pelo endpoint de resolucao e entao enfileirar o processamento.

## Estado Verificado

Repositorio:

- Branch `main` sincronizada com `origin/main`.
- Ultimo commit publicado: `32c6d04` (`fix: harden API auth and jobs`).
- Gates locais executados:
  - `uv run ruff check src tests` — OK
  - `uv run mypy src` — OK
  - `uv run pytest -q` — 70 passed
  - `uv run alembic heads` — `006_add_jsonb_gin_indexes (head)`

Railway:

- `api`, `worker`, `Postgres`, `Redis` e `OpenClaw` em `SUCCESS`.
- API `/health` respondeu `200`.
- Worker processou jobs `process_entrada` recentes com sucesso.
- Deploy da `api` e do `worker` esta no commit `32c6d04`.
- OpenClaw esta ativo como servico separado.

Linear:

- `GHF-225` (`Integração Telegram/OpenClaw`) esta em progresso.
- `GHF-228`, `GHF-229` e `GHF-230` estao concluidas, cobrindo hardening, ingestao unificada e Telegram real com midia.
- `GHF-222` (`RDO com aprovação Telegram`) esta em backlog e deve ser o proximo bloco depois de resolver obras.
- Documentos antigos do Linear ainda descrevem Telegram/OpenClaw como futuro em alguns trechos; a issue `GHF-230` e o README local ja refletem o estado mais atual.

## Achados

### P0 — `OBRABOT_API_KEY` ausente no servico `api`

As rotas administrativas foram protegidas por `X-Obrabot-API-Key`. Na auditoria do Railway, a variavel `OBRABOT_API_KEY` nao apareceu no servico `api`.

Impacto:

- `GET /api/v1/obras` e `POST /api/v1/obras` ficam indisponiveis para operacao administrativa.
- A tentativa sem chave em producao retornou `500`, comportamento esperado quando a chave obrigatoria nao esta configurada.
- Sem essa rota operacional, nao ha caminho simples para cadastrar obras reais.

Correcao operacional:

```bash
railway variable set OBRABOT_API_KEY=<valor-forte> --service api
```

Depois do redeploy, usar o mesmo valor apenas como header administrativo:

```powershell
$headers = @{
  "Content-Type" = "application/json"
  "X-Obrabot-API-Key" = $env:OBRABOT_API_KEY
}

Invoke-RestMethod `
  -Method Post `
  -Uri "https://api-production-8bfb.up.railway.app/api/v1/obras" `
  -Headers $headers `
  -Body '{"id":"OBRA-001","nome":"Nome da Obra"}'
```

### P0 — Onboarding de obras

Diagnostico original:

- `src/api/routes/obras.py` criava obra com payload generico.
- Nao existia script/guia de seed para criar as obras iniciais.
- `src/services/ingestao_service.py::ensure_obra` auto-criava obra quando um `obra_id` chegava.

Estado apos GHF-233:

- `/api/v1/obras` usa schemas Pydantic tipados.
- `scripts/seed_obras.py` cadastra obras iniciais pela API administrativa.
- `/tasks` rejeita `obra_id` ausente ou desconhecido.
- OpenClaw aceita entrada sem obra, mantendo status `pending_obra`.

Correcao aplicada:

1. Criados schemas Pydantic para obras (`ObraCreate`, `ObraResponse`).
2. Criado `scripts/seed_obras.py`.
3. Documentado cadastro inicial em `docs/operations.md`.
4. Definida convencao operacional de IDs como `OBRA-001`, `OBRA-002`.

### P0 — Resolucao de obra no OpenClaw

Diagnostico original:

- Mensagens naturais como "Hoje concretamos a laje" nao entravam se o gateway nao preenchesse `obra_id`.
- A decisao de obra estava deslocada para o OpenClaw, sem API/fluxo de resolucao no backend.

Estado apos GHF-233:

- `obra_id` e opcional no payload OpenClaw.
- Entrada sem obra ou com obra desconhecida fica `pending_obra`.
- O backend retorna a lista de obras ativas e uma mensagem de orientacao.
- `/api/v1/entradas/{entrada_id}/resolver-obra` vincula uma obra cadastrada e enfileira a entrada.

Regra mantida:

Documento final, RDO e triagem oficial so podem acontecer depois que a obra estiver resolvida.

### P1 — RDO ainda nao tem agregador diario

O servico `rdo_service` ja cria rascunho e bloqueia finalizacao sem aprovacao humana, mas recebe `conteudo` pronto.

Falta:

- buscar entradas, fotos, audios e triagens por `obra_id` + data;
- montar conteudo estruturado de RDO;
- criar comando/fluxo OpenClaw para gerar rascunho do dia;
- aprovar/reprovar pelo Telegram.

### P1 — Documentos do Linear estao parcialmente antigos

Alguns documentos do Linear ainda citam Telegram como futuro ou S3/OpenAI como pendentes, enquanto issues mais recentes indicam que:

- OpenAI em producao foi configurado;
- MEGA S4 foi configurado;
- Telegram real com midia foi validado;
- OpenClaw esta rodando.

Recomendacao:

- Usar issues recentes como fonte de verdade operacional.
- Atualizar/criar documento Linear de estado atual apos resolver o cadastro de obras.

## Como Usar o Fluxo de Obras Agora

Operacao inicial:

1. Configurar `OBRABOT_API_KEY` no servico `api`.
2. Cadastrar pelo menos uma obra real via `POST /api/v1/obras` ou `scripts/seed_obras.py`.
3. Configurar o OpenClaw/CEO para usar esse `obra_id` unico quando ele conseguir identificar a obra.
4. Quando a mensagem chegar sem obra, resolver pelo endpoint `/api/v1/entradas/{entrada_id}/resolver-obra`.
5. Rodar teste real no Telegram mencionando explicitamente o ID da obra e outro teste sem ID.

Exemplo de mensagem:

```text
OBRA-001: hoje executamos alvenaria no pavimento 2.
```

Proximas evolucoes:

1. Adicionar aliases/apelidos de obra para sugestao automatica.
2. Automatizar pergunta de confirmacao pelo Telegram quando houver ambiguidade.
3. Iniciar Sprint 4/RDO depois que texto e midia estiverem associados a uma obra real.

## Ordem Recomendada de Desenvolvimento

1. `P0` Configurar `OBRABOT_API_KEY` em producao.
2. `P0` Cadastrar obra real inicial.
3. `P0` Rodar e registrar smoke real Telegram com obra real.
4. `P0` Rodar e registrar smoke real Telegram sem obra para validar `pending_obra`.
5. `P1` Implementar agregador de RDO diario.
6. `P1` Implementar aprovacao/reprovacao por Telegram.
7. `P1` Finalizar RDO com PDF + metadata + hash.

## Atualização GHF-233

Implementacao entregue para resolver esta auditoria:

- `/api/v1/obras` com schemas Pydantic tipados.
- `scripts/seed_obras.py` para cadastro inicial via API administrativa.
- Webhook OpenClaw aceitando `obra_id` opcional.
- Entrada sem obra ou com obra desconhecida fica `pending_obra`, sem fila/IA/documento oficial.
- `/api/v1/entradas/{entrada_id}/resolver-obra` para vincular uma obra cadastrada e enfileirar o processamento.
