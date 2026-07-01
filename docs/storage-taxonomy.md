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
obras/OBRA-SMOKE-obra-smoke/
```

Entradas sem obra ficam apenas no PostgreSQL com `status=pending_obra` até a resolução.

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
  03_rascunhos/
    {tipo}/{data_ref}/{revisao}/{arquivo}.html
  04_documentos_finais/
    {tipo}/{data_ref}/{revisao}/{arquivo}.pdf
    relatorio_fotografico/{periodo_inicio}/{revisao}/RELATORIO_FOTOGRAFICO_*.pdf
  05_RDO/
    rascunhos/{data_ref}/{revisao}/{arquivo}.html
    finalizados_pdf/{data_ref}/{revisao}/RDO_*_FINAL.pdf
  06_fotos/
    brutas/{data_ref}/{hash16}.jpg
  07_planejamento/
    baseline/{data_ref}/baseline_FINAL.json
```

## Tipos de documento por área

| Área | Conteúdo | Sobrescrita |
|------|----------|-------------|
| `01_entrada_bruta` | Envelope JSON da entrada | Não (nova entrada = nova chave) |
| `02_midias` | Áudio, PDF, etc. (não foto) | Por hash |
| `03_triagem` | JSON da classificação | Por triagem_id |
| `03_rascunhos` | HTML de rascunhos (RDO, relatório) | Sim, durante revisão |
| `04_documentos_finais` | PDFs finais aprovados | **Não** (`allow_overwrite=false`) |
| `05_RDO/finalizados_pdf` | PDF RDO final | **Não** |
| `06_fotos/brutas` | Binários de foto | Por hash + data_ref |
| `07_planejamento/baseline` | Snapshot JSON orçamento+cronograma | Sim na reaprovação do dia |

## Sidecar de metadata

Todo documento final deve ter metadata sidecar via `persist_sidecar_metadata`:

```text
.../RDO_OBRA-001_2026-06-30_REV00_FINAL.pdf
.../RDO_OBRA-001_2026-06-30_REV00_FINAL.metadata.json
```

Campos típicos: `documento_id`, `obra_id`, `status`, `hash_sha256`, `aprovado_por`, `schema_version`.

## Relação com o banco

| Tabela | Campos relevantes |
|--------|-------------------|
| `entradas_brutas` | `id`, `obra_id`, `data_ref`, `status`, `raw_payload` |
| `arquivos` | `entrada_id`, `bucket_key`, `hash_sha256` |
| `documentos` | `tipo`, `status`, `bucket_key`, `revisao`, `metadata_json` |
| `fotos` | `arquivo_id`, `data_foto`, `descricao`, `tags` |
| `orcamento_itens` | `codigo`, `quantidade`, `valor_unitario` |
| `cronograma_atividades` | `codigo`, datas, `metadata_json.codigo_orcamento` |
| `aprovacoes` | `documento_id`, `aprovador`, `aprovado` |
| `auditoria_eventos` | `entidade`, `acao`, `detalhes` |
| `obras.metadata_json` | `baseline` (status, bucket_uri, aprovado_em) |

## Investigação de incidentes

1. Comece por `entradas_brutas` (filtro `obra_id`, `data_ref`, `status`).
2. Siga `entrada_id` → `arquivos`, `documentos`, `triagens`, `fotos`.
3. Use `bucket_key` / `bucket_uri` do documento para localizar o objeto.
4. Consulte `auditoria_eventos` para transições (`rdo_finalizado`, `baseline.aprovado`, etc.).

## Convenção de datas

- Telegram: `data_ref` vem do timestamp da mensagem (`telegram.date`).
- Sem data na origem: UTC do processamento.
- `data_ref` é operacional; validar data real do serviço no fluxo do documento (RDO, medição).

## Funções de chave (código)

| Função | Uso |
|--------|-----|
| `build_entrada_bruta_key` | Envelope de entrada |
| `build_arquivo_key` | Mídias e fotos brutas |
| `build_triagem_key` | JSON de triagem |
| `build_rdo_key` | RDO rascunho/final |
| `build_documento_key` | Rascunhos/finais genéricos |
| `build_baseline_key` | Snapshot baseline |
| `build_metadata_key` | Sidecar `.metadata.json` |

Implementação: `src/services/bucket_service.py`.
