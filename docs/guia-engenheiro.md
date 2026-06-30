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

Se o sistema responder pedindo a obra, responda com o ID cadastrado, por exemplo:

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

Envie a foto com legenda. A legenda deve explicar o que aparece e onde foi registrado.

Exemplo:

```text
OBRA-001: fachada norte, execução de reboco no 3º pavimento.
```

Boas práticas:

- fotografe com iluminação suficiente;
- inclua referência visual de local quando possível;
- evite enviar várias situações diferentes na mesma foto;
- não envie imagem sem legenda quando o local não for óbvio.

## Áudios

Áudios são aceitos e serão transcritos. Prefira áudios curtos, com obra e assunto no começo.

Exemplo:

```text
OBRA-001, registro do dia: concretagem concluída no bloco A, mas a bomba atrasou duas horas.
```

## Documentos

Documentos recebidos pelo Telegram são armazenados como arquivo bruto. OCR/importação estruturada ainda é fase futura, então descreva no texto o que o documento representa.

Exemplo:

```text
OBRA-001: estou enviando a nota de entrega do aço recebido hoje.
```

## RDO pelo Telegram

Depois que as entradas do dia forem enviadas e processadas, peça o rascunho do RDO:

```text
/gerar_rdo OBRA-001 hoje
```

O sistema deve responder com o `documento_id` do rascunho. Revise o documento antes de aprovar. Quando estiver correto, aprove de forma explícita:

```text
/aprovar_rdo <documento_id>
```

Esse comando registra a aprovação humana e finaliza o PDF no bucket. Para reprovar, informe o motivo:

```text
/reprovar_rdo <documento_id> faltou registrar a equipe de elétrica
```

## O que evitar

- Enviar informação de obra sem indicar a obra quando houver mais de uma obra ativa.
- Misturar assuntos de obras diferentes na mesma mensagem.
- Pedir geração de documento final sem aprovação humana.
- Enviar dados pessoais ou financeiros fora do escopo da obra.

## Estados possíveis

| Estado | Significado |
|--------|-------------|
| `pending_obra` | A obra precisa ser confirmada antes do processamento oficial |
| `queued` | Entrada aceita e enfileirada |
| `processing` | Worker está processando |
| `completed` | Triagem concluída e documento/registro criado |
| `failed` | Falha técnica; operação deve verificar logs/API |

## Regra de aprovação

RDO, relatório fotográfico e documentos finais só devem ser publicados depois de aprovação humana. Antes disso, o sistema trabalha com entrada bruta, triagem e rascunhos.
