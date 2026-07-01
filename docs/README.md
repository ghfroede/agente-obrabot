# Índice da documentação — Obrabot

Documentação operacional e técnica do repositório **agente-obrabot**.

## Comece aqui

| Documento | Público | Conteúdo |
|-----------|---------|----------|
| [../README.md](../README.md) | Todos | Visão geral, quickstart, roadmap |
| [../AGENTS.md](../AGENTS.md) | Agentes de IA | Convenções, invariantes, mapa do código |
| [../CLAUDE.md](../CLAUDE.md) | Claude Code | Referência técnica concisa |

## Operação e deploy

| Documento | Conteúdo |
|-----------|----------|
| [operations.md](operations.md) | Runbook: local, Railway, secrets, smoke, troubleshooting |
| [railway-deploy-plan.md](railway-deploy-plan.md) | Arquitetura Railway, serviços, variáveis |
| [guia-engenheiro.md](guia-engenheiro.md) | Como usar o bot no Telegram |
| [../SECURITY.md](../SECURITY.md) | Política de segurança, reporte e auditoria de dependências |

## Técnico

| Documento | Conteúdo |
|-----------|----------|
| [architecture.md](architecture.md) | Componentes, fluxos, estados |
| [api-reference.md](api-reference.md) | Referência HTTP completa |
| [storage-taxonomy.md](storage-taxonomy.md) | Layout de chaves no bucket S3 |

## OpenClaw

| Local | Conteúdo |
|-------|----------|
| [../openclaw/skills/](../openclaw/skills/) | Skills por domínio (rdo, fotos, orçamento, etc.) |
| [../openclaw/agents/](../openclaw/agents/) | Instruções por subagente |

## Histórico e design

| Documento | Conteúdo |
|-----------|----------|
| [plano-de-acao-2026-07-01.md](plano-de-acao-2026-07-01.md) | Auditoria completa + plano de ação priorizado (referência atual) |
| [project-audit-2026-06-29.md](project-audit-2026-06-29.md) | Auditoria pontual (superada pela de 2026-07-01) |
| [superpowers/specs/2026-06-29-painel-admin-interno-design.md](superpowers/specs/2026-06-29-painel-admin-interno-design.md) | Design do painel admin |

## Manutenção da documentação

Após alterar código:

```bash
graphify update .
```

Após alterar README, AGENTS.md ou arquivos em `docs/`:

```bash
graphify extract .
graphify cluster-only .
```

Mantenha este índice atualizado quando criar novos documentos em `docs/`.
