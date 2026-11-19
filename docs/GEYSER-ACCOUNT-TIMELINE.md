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

- O método legado `rollback_from_slot` rejeita histórico que contenha `bank_id`: remover tudo a partir de um slot poderia apagar simultaneamente bancos concorrentes. Para dados fork-scoped, a invalidação deve passar pelo `BankLineageTracker` com identidade exata do banco.
- A timeline não expõe `current_state` quando há histórico fork-scoped ou quando o último evento ainda é startup; um snapshot de startup não é promovido a estado corrente de banco.


## Yellowstone protobuf boundary adapter

The boundary adapter in `geyser_proto_adapter.py` accepts decoded messages
from the Yellowstone Geyser protobuf client and maps only four event families
to the provider-neutral contracts:

- `SubscribeUpdateAccount`: Base58-encodes 32-byte pubkey/owner and an optional
  64-byte transaction signature; preserves account data as raw bytes, slot,
  write_version, optional bank_id and is_startup.
- `SubscribeUpdateSlot`: maps the numeric SlotStatus enum and preserves the
  optional parent, bank_id and dead_error fields.
- `SubscribeUpdateBlockMeta`: preserves blockhash, parent slot/hash and bank ID.
- `SubscribeUpdateEntryUpdateParent`: preserves parent_block_id as opaque bytes.

The protocol contract is pinned to rpcpool/yellowstone-grpc tag
`v16.1.5+solana.4.3.2`; the exact upstream `geyser.proto` Git blob SHA and
serialized fixture hashes are recorded in
`tests/fixtures/yellowstone/v16.1.5+solana.4.3.2/manifest.json`. Tests parse
versioned, serialized protobuf wire fixtures with a descriptor subset matching
the pinned field numbers, enum values and wire types. The production adapter
does not depend on the fixture descriptor.

The caller supplies a stable provider/node `source_id`, a per-connection
`stream_id`, and a monotonically assigned `stream_sequence`. This adapter
does not create that sequence, infer commitment, reorder messages, reconnect,
or replay. Unknown/unhandled oneof members are ignored; malformed required
binary keys/signatures fail closed.

This is a message-boundary adapter only. No Yellowstone endpoint/client,
continuous capture, RAW/SQLite persistence, backfill, or financial execution
is enabled. Bank-aware pre/post pairing is integrated in the section below and is
validated against competing banks and explicit invalidation signals.


## Bank-aware account timeline integration

`AccountUpdateTimeline` now owns a provider-neutral `BankLineageTracker`
by default (or accepts an injected tracker) and exposes event-ingestion methods
for normalized slot lifecycle, block metadata and EntryUpdateParent messages.

For bank-scoped account writes, `transition_for(signature)` now follows these
rules:

1. Both pre- and post-state writes must have an observed, non-startup bank
   identity from the same stable source namespace.
2. A pair within the exact same bank is eligible only while that bank and all
   known ancestors remain usable.
3. A pair across banks is eligible only when the pre-state bank is a verified
   ancestor of the post-state bank through exact parent slot + parent blockhash
   matches. Shared slot, parent slot alone, stream order and sibling forks do
   not establish ancestry.
4. Among verified ancestors, the latest earlier ledger write is selected. If
   multiple candidates share the same latest ledger key, the method returns
   no transition rather than depending on insertion order.
5. A dead or EntryUpdateParent-cleared bank, or any known invalidated ancestor,
   cannot contribute to a transition. Historical account updates remain in
   the timeline for audit; they are not physically deleted.
6. Missing lineage remains unresolved. If block metadata arrives after account
   writes, a later call to `transition_for` may resolve the pair without
   rewriting the account timeline.
7. Reconnect/sequence gaps retain the existing continuity-epoch baseline rule.
   Replay remains idempotent.

The legacy slot-only rollback remains prohibited for bank-scoped histories.
Exact fork invalidation is driven by the bank tracker and leaves old account
updates available for audit. No commitment is inferred and no branch is
declared canonical merely because a bank was observed or finalized.

Tests in `test_geyser_bank_aware_timeline.py` cover same-bank and verified
cross-bank transitions, sibling forks, unresolved parents, cleared/dead banks,
invalidated ancestors, metadata arriving late, reconnect baselines and replay.


### Out-of-order writes and continuity baselines

For bank-scoped updates, the first write ever observed for an account is not
permanently treated as an unchangeable baseline: if an earlier ledger write
arrives later in the same continuity epoch and is proven to be on the target
bank's ancestor chain, the pair can be reconstructed after ledger sorting.
This supports out-of-order delivery without using stream sequence as ledger
order.

A reconnect or stream gap is different. The first subsequent write for each
known account is marked as a continuity baseline. A late-arriving ancestor
write cannot bypass that boundary or restore a pre-state across a missing
stream segment. Pairing may resume only from the new baseline to a later
contiguous write in the same epoch.

Exact invalidation is tested at both the cleared bank and a descendant whose
known parent chain passes through that bank. Such descendants are not usable
for pre/post reconstruction after the ancestor is cleared or marked dead.


## Persistent RAW-to-Timeline projection integrity (projection v2)

The SQLite projection in `geyser_account_timeline_projection.py` is a
rebuildable derived view. Before decoding a selected normalized RAW event, it
recomputes SHA-256 over the exact stored `payload_bytes` and requires equality
with the immutable `payload_sha256` column. A mismatch aborts the transaction;
the prior projection generation and recovery checkpoints remain unchanged.

A delivery is not eligible for timeline replay if its exact
`(source_id, stream_id, stream_sequence)` has any row in
`geyser_transport_anomalies`. This is historical taint: the exclusion applies
whether the anomaly is OPEN or administratively RESOLVED. RESOLVED closes the
operational interruption only; it does not rehabilitate the historical
sequence or its deliveries.

A logical RAW event identity with any row in `geyser_raw_conflicts` is also
excluded from the derived timeline. The original RAW bytes, conflicting
payload, and delivery records remain preserved for audit; projection exclusion
does not delete or rewrite them.

Eligible deliveries are selected deterministically by source, stream, sequence,
and delivery ID. Sequence ordering is applied only within the same stream.
Different streams are never compared numerically; a stream change remains a
continuity boundary in the account timeline. This allows a full rebuild to
place a late-arriving sequence 2 between previously received sequences 1 and 3
for the same stream, while retaining conservative continuity across gaps,
reconnects, and stream changes.

The persistent projection version is now 2. These rules affect only derived
projection eligibility and replay; they do not assign missing sequences,
change RAW identity, infer a canonical fork, promote provider commitment, or
authorize financial execution. Regression coverage lives in
`tests/test_geyser_account_timeline_projection.py`.
