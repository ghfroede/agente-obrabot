# Auditoria do Projeto — 2026-06-29

## Veredito

O Obrabot esta tecnicamente estavel para continuar, mas o proximo bloqueio de produto nao e Telegram nem worker: e o cadastro e a resolucao de obras.

O backend ja processa entradas quando um `obra_id` chega no payload. Porem, nao ha ainda um fluxo operacional completo para:

- cadastrar obras reais antes do uso;
- listar/selecionar obra pelo OpenClaw quando o engenheiro nao informa `obra_id`;
- impedir que mensagens reais sejam associadas a obras placeholders como `SEM_OBRA`;
- orientar o operador a criar uma obra pelo caminho correto.

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

### P0 — Nao existe onboarding de obras

O codigo possui `POST /api/v1/obras`, mas ele aceita `dict` generico e nao existe script/guia de seed para criar as obras iniciais.

Evidencia:

- `src/api/routes/obras.py` cria obra com `payload["id"]` e `payload["nome"]`.
- `src/services/ingestao_service.py::ensure_obra` auto-cria a obra quando um `obra_id` chega.

Impacto:

- Se o OpenClaw nao souber qual `obra_id` usar, o payload nem valida, porque `OpenClawTelegramPayload.obra_id` e obrigatorio.
- Se a API `/tasks` for usada sem `obra_id`, o sistema cai em `SEM_OBRA`, o que nao serve para operacao real.
- Auto-criacao e util para idempotencia e testes, mas nao substitui cadastro operacional.

Correcao recomendada:

1. Criar schemas Pydantic para obras (`ObraCreate`, `ObraResponse`).
2. Criar script `scripts/seed_obras.py` para cadastrar obras reais via API ou diretamente via banco em ambiente controlado.
3. Documentar cadastro inicial em `docs/operations.md`.
4. Definir convencao de IDs: `OBRA-001`, `OBRA-002`, etc.

### P0 — Payload OpenClaw exige `obra_id`

O schema atual exige:

```python
class OpenClawTelegramPayload(BaseModel):
    event_id: str
    obra_id: str
    obra_nome: str | None = None
    telegram: TelegramEvent
```

Impacto:

- Mensagens naturais como "Hoje concretamos a laje" nao entram se o gateway nao preencher `obra_id`.
- A decisao de obra esta hoje deslocada para o OpenClaw, mas o backend nao oferece API/fluxo de resolucao de obra.

Correcao recomendada:

1. Manter `obra_id` obrigatorio para documentos finais e RDO.
2. Permitir entrada bruta sem obra clara em uma fase controlada, com status `pendente_obra`.
3. Criar endpoint/fluxo de resolucao:
   - listar obras ativas;
   - sugerir obra por texto, alias ou contexto;
   - responder no Telegram pedindo confirmacao quando ambigua.
4. So processar documento oficial depois que a obra estiver resolvida.

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

## Como Resolver o Problema das Obras Agora

Curto prazo:

1. Configurar `OBRABOT_API_KEY` no servico `api`.
2. Cadastrar pelo menos uma obra real via `POST /api/v1/obras`.
3. Configurar o OpenClaw/CEO para usar esse `obra_id` unico por enquanto.
4. Rodar teste real no Telegram mencionando explicitamente o ID da obra.

Exemplo de mensagem:

```text
OBRA-001: hoje executamos alvenaria no pavimento 2.
```

Medio prazo:

1. Implementar cadastro de obras com schema tipado e aliases.
2. Implementar resolucao de obra quando a mensagem vier sem `obra_id`.
3. Implementar estado `pendente_obra` para entradas que precisam de confirmacao humana.
4. So iniciar Sprint 4/RDO depois que texto e midia estiverem associados a uma obra real.

## Ordem Recomendada de Desenvolvimento

1. `P0` Configurar `OBRABOT_API_KEY` em producao.
2. `P0` Criar fluxo de cadastro/seed de obras.
3. `P0` Adaptar OpenClaw para usar obra unica inicial ou perguntar a obra quando faltar.
4. `P0` Rodar e registrar smoke real Telegram com obra real.
5. `P1` Implementar agregador de RDO diario.
6. `P1` Implementar aprovacao/reprovacao por Telegram.
7. `P1` Finalizar RDO com PDF + metadata + hash.

