# Geyser account timeline — contrato inicial

## Escopo

`AccountUpdateTimeline` mantém, em memória, uma linha do tempo provider-neutral de `NormalizedAccountUpdate`. Não abre conexão, não persiste em SQLite/RAW, não consulta RPC e não classifica swaps.

## Duas ordens distintas

- **Ordem de ledger:** `slot` e `write_version`. É a chave de ordenação das escritas de uma conta.
- **Ordem de transporte:** `stream_id` e `stream_sequence`. Serve para detectar replay, reutilização de sequência, reconexão e lacunas na entrega.

A sequência do stream nunca desempata uma colisão de identidade de ledger. Para a mesma pubkey, slot e write_version, payloads diferentes geram conflito e não sobrescrevem o estado anterior.

## Regras de timeline

1. A primeira atualização observada de cada pubkey é baseline: não existe pre-state conhecido antes dela.
2. Updates são ordenados por `(slot, write_version)`, independentemente da ordem em que chegaram ao método `add`.
3. Reentrega idêntica é deduplicada por fingerprint. Colisão de identidade com conteúdo diferente é registrada como conflito.
4. Uma lacuna de `stream_sequence` ou troca de `stream_id` cria uma fronteira de continuidade. A primeira atualização subsequente de cada conta conhecida vira novo baseline; ela não gera par pre/post.
5. Depois desse baseline, escritas seguintes no mesmo epoch podem gerar transição se houver predecessor observado.
6. Update sem `txn_signature` permanece na timeline, mas não pode ser associado a uma transação específica.
7. `rollback_from_slot` só deve ser chamado após sinal autoritativo de rollback/fork do provider. Updates removidos são mantidos em `orphaned_updates`; a primeira escrita posterior vira baseline.

## Pareamento pre/post

`transition_for(signature)` retorna somente contas com update associado à assinatura e predecessor observado imediatamente anterior na mesma continuidade. Não retorna:
- primeiro estado conhecido da conta;
- primeiro estado depois de lacuna, reconexão ou rollback;
- update sem assinatura;
- escrita com colisão de identidade.

O par é evidência de estados observados na sequência de account writes; não prova sozinho que o stream capturou todos os dados, nem promove o commitment.

## Limitações intencionais

- Ainda não há adapter protobuf Yellowstone oficial; o normalizador recebe envelope canônico.
- A timeline é em memória e não sobrevive a reinício.
- Não armazena commitment, blockhash, parent slot ou identidade de fork. Rollback é sinal externo explícito, não inferência local.
- `write_version` é preservado como metadado de ordenação de account writes; não é substituto de índice de instrução/transação nem de ordem de execução interna.
- Uma transição não deve ser usada para reconciliação econômica até o adapter/provider comprovar a semântica do stream e o compromisso da transação em nível superior.
- Nenhum dado de fixture sintética é considerado prova mainnet.

## Testes

A suíte `tests/test_geyser_account_timeline.py` cobre ordenação ledger versus entrega, replay, colisões, lacuna de sequência, reconexão, assinatura ausente, rollback explícito e independência entre contas.


## Bank identity and fork-lineage extension

The Yellowstone bank lifecycle is normalized separately in
`geyser_bank_lineage.py`:

- Account updates preserve optional `bank_id` and `is_startup`. Startup
  account updates must not claim a bank ID.
- Bank identity is `(source_id, slot, bank_id)`; `source_id` is a stable
  provider/node namespace across reconnects, while `stream_id` identifies a
  transport connection only.
- `SLOT_CREATED_BANK` requires a bank ID. `SLOT_DEAD` with a bank ID marks
  that exact bank dead; without a bank ID it marks known and subsequently
  observed banks for that source/slot dead. FIRST_SHRED_RECEIVED and COMPLETED
  may be unassigned to a bank.
- `EntryUpdateParent` invalidates exactly the `cleared_bank_id` and preserves
  `parent_block_id` as opaque bytes. A subsequent CREATED_BANK event is linked
  as its replacement only when the relationship is unambiguous.
- Slot parent number alone does not identify a parent fork. A parent edge is
  established only by an exact `(parent_slot, parent_blockhash)` match from
  block metadata. Missing or ambiguous matches remain unresolved.
- The opaque `parent_block_id` is never compared with a textual blockhash.
- `is_ancestor` returns unknown (`None`) when parent lineage is incomplete;
  it does not guess.
- The existing linear AccountUpdateTimeline refuses to emit pre/post
  transitions for bank-scoped updates and returns no single current state for
  a fork-scoped account history. Bank-aware pre/post pairing is deferred until
  lineage is integrated and validated.

## Remaining limitations

No Yellowstone protobuf adapter or live stream exists yet. The canonical event
normalizers accept mappings already decoded by a future adapter. The tracker
is in-memory, provider-scoped, and does not declare a bank canonical merely
because it is processed or finalized; higher-level commitment policy and
fork-resolution policy remain separate. No RAW/SQLite persistence, RPC, or
Helius integration is part of this change.

- O campo `source` de `NormalizedAccountUpdate` deve receber o mesmo namespace estável usado como `source_id` nos eventos de slot/block/parent. O identificador não deve mudar em cada reconexão; `stream_id` pode mudar.
- A chave `ordering_key` agora contém somente `(slot, write_version)`; `stream_sequence` não desempata nem altera a ordem do ledger. Quando bancos diferentes compartilham o mesmo slot, a ordem linear é deliberadamente insuficiente.
- `is_ancestor` só retorna `False` quando a cadeia observada chega à raiz conhecida (slot 0); cadeia incompleta retorna `None`.
