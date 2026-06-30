# Taxonomia de Storage — MEGA S4/S3

O bucket é fonte documental junto com o PostgreSQL. O banco guarda entidades, relações, status e auditoria; o bucket guarda envelopes brutos, mídias, triagens serializadas, rascunhos e documentos finais.

## Prefixo por obra

Toda informação resolvida para uma obra usa:

```text
obras/{obra_id}-{slug}/
```

Exemplo:

```text
obras/OBRA-001-residencial-aurora/
```

Entradas sem obra ficam apenas no PostgreSQL com `status=pending_obra` até a resolução. Após confirmar a obra, o worker persiste a entrada no prefixo da obra correta.

## Estrutura principal

```text
obras/{obra_id}-{slug}/
  01_entrada_bruta/
    {source}/YYYY/MM/DD/entrada_{entrada_id}/envelope.json
  02_midias/
    audio/YYYY/MM/{hash16}.ogg
    documento/YYYY/MM/{hash16}.pdf
  03_triagem/
    classificacoes/YYYY/MM/DD/triagem_{triagem_id}.json
    transcricoes_audio/{audio_id}.json
  03_rascunhos/
    {tipo}/{data_ref}/{revisao}/{arquivo}
  04_documentos_finais/
    {tipo}/{data_ref}/{revisao}/{arquivo}
  05_RDO/
    rascunhos/{data_ref}/{revisao}/{arquivo}.html
    finalizados_pdf/{data_ref}/{revisao}/{arquivo}.pdf
  06_fotos/
    brutas/{data_ref}/{hash16}.jpg
```

## Regras de gravação

- `01_entrada_bruta` deve ser gravado antes da IA.
- `02_midias` recebe binários que não são fotos; fotos ficam em `06_fotos/brutas` para facilitar relatório fotográfico.
- `03_triagem` guarda o JSON da classificação e artefatos derivados de IA.
- `03_rascunhos` e `05_RDO/rascunhos` podem ser sobrescritos conforme a revisão.
- `04_documentos_finais` e `05_RDO/finalizados_pdf` não devem sobrescrever objetos existentes.
- Todo documento final deve ter metadata sidecar gerada por `persist_sidecar_metadata`.

## Relação com o banco

As tabelas principais mantêm chaves de rastreabilidade:

| Tabela | Campos relevantes |
|--------|-------------------|
| `entradas_brutas` | `id`, `obra_id`, `data_ref`, `storage_key`, `metadata_json`, `status` |
| `arquivos` | `entrada_id`, `obra_id`, `bucket_key`, `hash_sha256` |
| `documentos` | `entrada_id`, `obra_id`, `bucket_key`, `status`, `hash_sha256` |
| `triagens` | `entrada_id`, `documento_id`, `obra_id`, `campos_extraidos` |
| `auditoria_eventos` | `obra_id`, `entidade`, `entidade_id`, `acao`, `detalhes` |

Para investigar uma informação:

1. Comece por `entradas_brutas`.
2. Siga `entrada_id` para `arquivos`, `documentos` e `triagens`.
3. Use `bucket_key` para localizar o objeto no MEGA S4.
4. Consulte `auditoria_eventos` para entender ações administrativas e transições.

## Convenção de datas

Quando a entrada vier do Telegram, a data de referência vem do timestamp da mensagem. Se a origem não informar data, o sistema usa a data UTC do processamento para montar a chave do bucket.

`data_ref` é operacional, não necessariamente a data real de execução do serviço. A data real do RDO ou medição deve ser validada no fluxo específico de cada documento.
