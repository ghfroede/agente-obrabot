# Guia do Engenheiro — Obrabot no Telegram

Este guia orienta o envio de informações de campo para o Obrabot pelo grupo de Telegram integrado ao OpenClaw.

## Regra principal

Envie informações objetivas, uma ocorrência por mensagem quando possível. O Obrabot registra a entrada bruta, salva mídias no bucket e processa a triagem em segundo plano.

Se a obra não estiver clara, o sistema não gera documento oficial. A entrada fica como `pending_obra` até alguém confirmar a obra correta.

## Como informar a obra

Quando souber o código da obra, comece a mensagem com ele:

```text
OBRA-001: hoje executamos alvenaria no pavimento 2.
```

Também funciona enviar o código junto da foto, áudio ou documento:

```text
OBRA-001: foto da concretagem da laje do bloco B.
```

Se o sistema responder pedindo a obra, responda com o ID cadastrado:

```text
OBRA-001
```

## Texto de campo

Inclua, quando souber:

- serviço executado;
- local ou pavimento;
- equipe envolvida;
- materiais recebidos ou usados;
- impedimentos e pendências;
- riscos de prazo, qualidade ou segurança.

Exemplo:

```text
OBRA-001: hoje executamos alvenaria no pavimento 2, eixo B-C. Equipe com 4 pedreiros e 2 serventes. Recebemos 2 pallets de bloco. Ficou pendente argamassa para amanhã.
```

## Fotos

Envie a foto com legenda explicando o que aparece e onde foi registrado.

```text
OBRA-001: fachada norte, execução de reboco no 3º pavimento.
```

Boas práticas:

- iluminação suficiente;
- referência visual de local quando possível;
- evite várias situações diferentes na mesma foto;
- não envie imagem sem legenda quando o local não for óbvio.

As fotos são classificadas automaticamente (descrição por IA) e entram no relatório fotográfico do período.

## Áudios

Áudios são transcritos. Prefira áudios curtos, com obra e assunto no começo.

```text
OBRA-001, registro do dia: concretagem concluída no bloco A, mas a bomba atrasou duas horas.
```

## Documentos

Documentos recebidos pelo Telegram são armazenados como arquivo bruto. Descreva no texto o que o documento representa.

```text
OBRA-001: estou enviando a nota de entrega do aço recebido hoje.
```

## RDO (Relatório Diário de Obra)

Depois que as entradas do dia forem enviadas e processadas:

```text
/gerar_rdo OBRA-001 hoje
```

O sistema responde com o `documento_id` do rascunho. Revise antes de aprovar:

```text
/aprovar_rdo <documento_id>
```

Para reprovar:

```text
/reprovar_rdo <documento_id> faltou registrar a equipe de elétrica
```

O PDF final só é publicado após aprovação explícita.

## Relatório fotográfico

Para consolidar fotos de um período:

```text
/gerar_relatorio_foto OBRA-001 2026-06-01 2026-06-15
```

Para o dia atual:

```text
/gerar_relatorio_foto OBRA-001 hoje hoje
```

Após revisar o rascunho:

```text
/aprovar_relatorio_foto <documento_id>
```

## Orçamento e cronograma (baseline)

Importação de orçamento e cronograma é feita pela equipe de planejamento (planilha validada → API). No Telegram você pode acompanhar:

```text
/validar_baseline OBRA-001
```

Quando estiver correto e com aprovação explícita:

```text
/aprovar_baseline OBRA-001
```

O baseline aprovado passa a aparecer no contexto do RDO do dia.

## O que evitar

- Enviar informação sem indicar a obra quando houver mais de uma obra ativa.
- Misturar assuntos de obras diferentes na mesma mensagem.
- Pedir documento final sem aprovação humana.
- Enviar dados pessoais ou financeiros fora do escopo da obra.

## Estados possíveis

| Estado | Significado |
|--------|-------------|
| `pending_obra` | Obra precisa ser confirmada |
| `queued` | Entrada aceita e enfileirada |
| `processing` | Worker processando |
| `completed` | Triagem concluída |
| `failed` | Falha técnica — acionar operação |

## Regra de aprovação

RDO, relatório fotográfico e documentos finais só são publicados no bucket depois de **aprovação humana explícita**. Antes disso, o sistema trabalha com entrada bruta, triagem e rascunhos.

Mais detalhes: [operations.md](operations.md), [api-reference.md](api-reference.md).
