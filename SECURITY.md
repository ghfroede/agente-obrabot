# Politica de Seguranca

## Escopo

Este documento cobre o backend Obrabot neste repositorio: API FastAPI, worker RQ,
migrations, scripts operacionais, templates administrativos e configuracao de deploy
Railway.

O servico OpenClaw roda como componente separado no Railway e deve acessar o Obrabot
somente pela API publica assinada com HMAC. Ele nao deve receber credenciais de banco
ou S3.

## Versoes Suportadas

| Versao | Suporte |
|--------|---------|
| `main` | Suporte ativo |
| branches antigas | Sem suporte de seguranca |

## Reporte

Reporte vulnerabilidades diretamente aos mantenedores do projeto por canal privado
interno. Nao abra issue publica com detalhes exploraveis, secrets, payloads reais,
logs sensiveis ou dados de clientes.

Inclua, quando possivel:

- componente afetado;
- pre-condicoes de exploracao;
- impacto esperado;
- passos minimos de reproducao;
- evidencias sem dados sensiveis;
- versao/commit observado.

## Segredos e Producao

Em producao, o boot da API deve falhar quando secrets obrigatorios estiverem
ausentes ou com placeholders conhecidos. Secrets obrigatorios no servico `api`:

- `OBRABOT_API_KEY`
- `OPENCLAW_SHARED_SECRET`
- `SESSION_SECRET`
- `ADMIN_PASSWORD`

Secrets opcionais tambem nao devem usar placeholders quando definidos:

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

Configure secrets pelo Railway. Nunca commite `.env`, `railway.json` local ou
valores reais em documentacao, testes ou comentarios.

## Auditoria de Dependencias

Execute antes de releases e apos qualquer alteracao em `pyproject.toml` ou
`uv.lock`:

```bash
make security-audit
```

Sem `make`, use:

```bash
uv run python scripts/audit_dependencies.py
```

O script exporta o `uv.lock` sem dependencias de desenvolvimento para um
requirements temporario e executa `uvx pip-audit --strict`. O comando deve retornar
codigo diferente de zero quando houver vulnerabilidade relevante.

Cadencia recomendada:

- semanal enquanto o sistema estiver em testes reais;
- obrigatoria antes de deploys de producao;
- obrigatoria apos atualizacao de bibliotecas de API, banco, storage, PDF ou LLM.

## Mitigacoes da Auditoria 2026-07-01

Confirmadas e tratadas:

- CORS em producao exige allowlist explicita e bloqueia wildcard.
- Body size limit global cobre rotas HTTP gerais, login admin e OpenClaw.
- Security headers globais incluem CSP, frame deny, nosniff, referrer policy,
  permissions policy e HSTS em producao HTTPS.
- Placeholders conhecidos em secrets derrubam o boot de producao.
- Rate limit cobre OpenClaw, login admin e rotas protegidas/caras por API key.

Controles de dominio que nao devem ser removidos:

- webhook OpenClaw com HMAC obrigatorio em producao;
- persistencia de `EntradaBruta` antes da IA;
- aprovacao humana obrigatoria antes de documentos finais;
- worker sem dominio publico;
- OpenClaw sem acesso direto a DB/S3.
