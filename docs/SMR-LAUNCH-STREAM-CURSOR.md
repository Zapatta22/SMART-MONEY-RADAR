# SMR — Cursor durável do consumidor Launch Radar CPMM

Estado: **módulo de persistência offline**, sem cliente RPC/stream conectado,
sem operações financeiras e sem compromisso de cobertura histórica da Solana.

## Contrato

`SQLiteEventStore.archive_cpmm_launches(payloads, source_id="consumer-id", first_sequence=100)`
aceita uma lista não vazia de *bytes RAW JSON-RPC* em ordem de entrega. O
consumidor atribui os números inteiros consecutivos (não são slots, assinaturas,
nem números de sequência fornecidos pela Solana). `source_id` identifica o
domínio estável da sequência; nunca reutilize a mesma origem para outro fluxo.

Uma única transação SQLite grava:

- os bytes originais e hashes SHA-256, inclusive entregas sem Initialize CPMM;
- as identidades dos pools CPMM detectados e eventuais conflitos;
- `(source_id, sequence, sha256)` de cada entrega;
- o último cursor aceito por origem.

Na repetição, a mesma sequência com o mesmo hash é idempotente; hash diferente
recusa o lote. Lacunas depois do checkpoint, saltos e sequências históricas
desconhecidas recusam o lote. Se a gravação falhar, cursor, RAW e evidências
sofrem rollback conjuntamente. O modo antigo sem parâmetros de cursor não foi
alterado.

O relatório inclui `stream_cursor` com primeiro/último número, novas entregas,
replays e `prior_coverage="UNKNOWN"`. O primeiro número observado apenas
estabelece um baseline local; **não comprova que foram capturados todos os
lançamentos anteriores ou que o provedor não omitiu eventos**.

## Restrições e próximos passos

Este módulo não busca dados na rede, não autentica RPC, não valida commitments
ou relógios do provedor e não garante que uma entrega seja uma inicialização
recente. O consumidor deve obter envelopes íntegros, declarar uma fonte estável,
reconciliar cursor pós-reconexão, fazer backfill e registrar lacunas de cobertura.
Não inferir segurança operacional de SHA-256 produzido pelo mesmo consumidor.

Próximo marco: adaptar uma fonte Solana de leitura com backfill e fail-closed
por origem, sem enviar ordens reais. Registrar testes de integração e métricas
de latência e cobertura separadamente.
