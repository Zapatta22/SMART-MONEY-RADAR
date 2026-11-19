# Geyser Historical Persistence and Backfill Contract

**Status:** Architecture specification plus offline RAW persistence, transport checkpoints/gaps, normalized ingestion, account-write/timeline projections, and recovery/backfill state persistence implemented. Provider transport and real historical backfill remain pending.  
**Date:** 2026-11-19  
**Scope:** PR #23, branch `feat/damm-v2-economic-reconciliation`.

## 1. Purpose and non-goals

This document defines the persistence boundary for Yellowstone/Geyser account history, bank lineage, transport continuity, and historical backfill. It is a contract for a future implementation, not evidence that ingestion or storage is operational.

The design must preserve the existing provider-neutral normalizers, `BankLineageTracker`, and `AccountUpdateTimeline`. It must not change the existing transaction/swap EventStore semantics.

Non-goals for this stage:
- no Yellowstone/Helius endpoint or gRPC client;
- no provider credentials, paid service, VPS, or continuous capture;
- no order execution, signing, or on-chain operation;
- no merge, main-branch change, or promotion of PR #23.

## 2. Architectural layers

The system has three logical layers:

1. **Immutable RAW evidence.** Preserve the received source payload and its provenance. Never silently rewrite or delete it.
2. **Provider-neutral normalized events.** Convert source messages into the existing account, slot, block-metadata, and entry-parent contracts. Record the normalizer/schema versions.
3. **Rebuildable timeline projections.** Derive account-write history, bank lineage, continuity, invalidation/orphan status, and queryable transitions. A projection is disposable and reproducible from retained evidence; it is not the primary evidence.

A correction to a normalizer must permit rebuilding projections without destroying the original input.

## 3. Storage isolation

Use a dedicated SQLite database, initially named `smr_geyser.sqlite`, separate from the existing `smr_events.sqlite` used by `SQLiteEventStore`.

Do not reuse wallet transaction checkpoints as Geyser transport or timeline checkpoints. They have different identities and semantics.

Initial durability policy:
- WAL mode with an explicitly documented synchronous/durability setting;
- checkpoint advancement only after the corresponding event transaction commits durably;
- no automatic deletion/retention pruning until volume, integrity, and recovery have been measured;
- schema migrations are versioned and transactional.

The exact SQLite pragmas, filesystem assumptions, backup procedure, and migration runner must be specified and tested during implementation before live ingestion.

## 4. Immutable RAW events and delivery history

Separate event content from each transport delivery.

### 4.1 `geyser_raw_events`

One row per unique source event content. Proposed fields:

- `event_id`: deterministic identity within the source namespace;
- `source_id`: stable logical source identity across reconnects;
- `event_kind`: account, slot, block_meta, entry_update_parent, or explicitly supported future kind;
- `schema_version`: exact upstream schema/protocol version when known;
- `payload_encoding`: `protobuf_wire` or an explicitly named normalized/decoded representation;
- `payload_bytes`: immutable bytes for the declared encoding;
- `payload_sha256`: SHA-256 of exactly those stored bytes;
- `first_received_at`: first observed receipt time.

The identity must not include `stream_id` or `stream_sequence`: these describe a delivery, not the source event content. The versioned identity contract is implemented in `src/smart_money_radar/data_sources/geyser_event_identity.py` as `derive_event_identity(event, schema_version=...)`. It hashes canonical JSON containing the identity-contract version, upstream schema version, event kind, and event-kind-specific logical key. A hash alone is an integrity check, not a substitute for the RAW store's conflict detection.

If an existing event identity is presented with different bytes, preserve the conflicting observation and record an integrity conflict. Never overwrite the original row or silently treat the conflict as a duplicate.

### 4.2 `geyser_raw_deliveries`

One row per delivery/replay, referencing the RAW event where identity can be established. Proposed fields:

- `delivery_id`;
- `event_id` (nullable only when the message cannot be safely identified);
- `source_id`;
- `stream_id`;
- `stream_sequence`;
- `received_at`;
- `delivery_kind` (live, replay, backfill, or other explicitly defined mode);
- `continuity_epoch_id` where applicable.

Repeated delivery of identical content creates another delivery record, not another content row. Conflicting or unidentifiable messages must still leave auditable delivery/conflict evidence.

### 4.3 Wire-byte provenance

The current protobuf adapter receives already-decoded protobuf objects. It therefore cannot claim to preserve the original wire bytes. A future transport boundary must capture serialized protobuf bytes before decoding to label the payload `protobuf_wire`.

If that boundary is unavailable, persist the exact deterministic representation actually captured and label it accordingly (for example, normalized protobuf-derived payload). Never describe decoded/re-serialized bytes as the original wire payload.

## 5. Normalized event and timeline projections

Proposed logical tables:

- `geyser_normalized_events`: event reference, normalized payload, source schema version, normalizer version, normalization status/error, and deterministic normalized fingerprint;
- `geyser_account_writes`: source, pubkey, slot, optional bank_id, write_version, optional txn_signature, startup flag, state bytes/hash, RAW/normalized references, and continuity epoch;
- `geyser_bank_events`: normalized slot lifecycle, block metadata, EntryUpdateParent, bank creation/death/clear evidence and references;
- `geyser_timeline_generations`: generation ID, input high-water marks, normalizer/projection versions, build status, timestamps, and diagnostics;
- `geyser_orphaned_events`: references to retained events excluded from a current projection, with reason, invalidating evidence, and generation.

The account event key includes stable source namespace, pubkey, slot, write_version, bank_id, and startup semantics. Slot events use source, slot, status, and bank_id; BlockMeta uses source, slot, and bank_id; EntryUpdateParent uses source, slot, and cleared_bank_id. Payload fields excluded from the key remain subject to RAW payload/hash conflict checks. Account updates without bank_id retain a null bank component; they are not silently joined to bank-scoped events.

Projection rebuilds must preserve:
- observed versus invalidated/orphaned state;
- the reason and evidence for invalidation;
- known bank lineage and unresolved parent relationships;
- the normalizer and projection version that produced each generation.

Never infer canonical fork selection from arrival order. Never physically delete forked, dead-bank, or orphaned evidence as part of projection rollback.

## 6. Three independent progress/checkpoint domains

### 6.1 Transport checkpoint

Key: `(source_id, stream_id)`.

Records the greatest contiguous transport sequence durably accepted for that stream, plus observed gaps and stream lifecycle. It proves only what the consumer received and committed; it does not prove that the provider emitted every expected event.

### 6.2 Continuity checkpoint

Tracks the last position for which account-history continuity is actually supported by available evidence, scoped to source and continuity epoch. It must reference the relevant stream/gap/reconnect evidence and projection generation.

It does not establish that a bank is canonical or finalized.

### 6.3 Backfill checkpoint

Tracks a backfill job's requested interval, cursor/progress, provider semantics, and coverage evidence. It does not prove complete historical coverage merely because a cursor reached its end.

These three checkpoints must never be collapsed into one cursor or substituted for wallet transaction checkpoints.

### 6.4 Gap rule

If sequence 102 arrives when 100 is expected:
- durably retain event 102 and its delivery;
- record missing sequence range 100–101;
- mark the affected continuity epoch interrupted;
- do not synthesize missing events or advance the contiguous transport checkpoint across the gap;
- resume continuity only after a documented recovery procedure proves the required interval was recovered.

The exact sequence-reset/wrap semantics must be supplied by the transport adapter. A new stream gets a new `stream_id`; `stream_sequence` is monotonic only within its defined stream scope and is never ledger ordering. Ledger ordering continues to use the existing `(slot, write_version)` semantics.

## 7. Reconnect, replay, and restart recovery

A restart/reconnect procedure must:

1. open the dedicated database and validate schema/integrity;
2. load durable transport, continuity, and backfill checkpoints independently;
3. select the last complete timeline generation;
4. create a new `stream_id` and continuity epoch as appropriate;
5. record reconnect and any provider/adapter discard-bank or gap evidence;
6. accept replay with idempotent event identity while preserving each delivery;
7. rebuild affected projections from retained normalized/RAW evidence;
8. mark continuity restored only when explicit recovery evidence satisfies the declared coverage rule.

A delayed event must not cross a gap/reconnect continuity boundary to fabricate a pre-state. Preserve the current in-memory timeline's baseline and bank-lineage safety rules.

## 8. Backfill jobs and coverage

Backfill is a distinct process from live capture. Proposed table: `geyser_backfill_jobs`.

Fields include:
- `job_id`, `source_id`, requested start/end boundaries;
- provider and adapter version, schema version, and query semantics;
- cursor start/current/end where supported;
- status: `PENDING`, `RUNNING`, `PARTIAL`, `COMPLETED`, or `FAILED`;
- counts requested/received/normalized/rejected;
- known gaps, retry history, start/end timestamps;
- coverage classification and evidence.

Coverage values:
- `COMPLETE`: the provider/query contract and returned evidence prove the requested interval is covered;
- `PARTIAL`: some, but not all, requested coverage is proven;
- `UNKNOWN`: there is insufficient evidence to determine coverage.

An empty response is not proof that no account updates occurred. A current-state query such as `getAccountInfo` does not reconstruct historical account writes. Provider retention limits, pagination, ordering, and historical availability must be declared per adapter; do not claim complete coverage beyond those guarantees.

Backfill and live ingestion may overlap. Their events must converge through the same identity/conflict rules while preserving delivery provenance and distinguishing their delivery modes.

## 9. Atomic ingestion and integrity

For each accepted delivery, a single database transaction must:
1. insert or verify immutable RAW content (or record why it cannot be identified);
2. insert the delivery record;
3. persist normalized output and normalization diagnostics when available;
4. record identity/hash conflicts and sequence gaps;
5. update only the appropriate durable transport checkpoint after all required writes succeed.

Any failure before commit rolls back the entire unit. A checkpoint must never advance beyond durable evidence. Projection generation can be updated separately only with explicit generation status and reproducible input high-water marks; incomplete generations must not replace the last complete generation.

## 10. Recovery, rebuild, and backup invariants

- Rebuilding a projection from the same immutable inputs and the same normalizer/projection versions must be deterministic.
- A failed rebuild leaves the last complete generation queryable.
- A backup/restore test must demonstrate that RAW evidence, delivery provenance, gaps, conflicts, and checkpoint state survive together.
- Database corruption or an incomplete restore must fail closed; do not resume ingestion from an unverified checkpoint.
- Retention/archival policy is deferred until measured data volume and tested restore procedures exist.

## 11. Implementation sequence and acceptance criteria

1. **Contracts and schema:** migrations, constraints, identities, indexes, versioning, and schema validation tests.
2. **RAW and deliveries:** byte/hash integrity, idempotent replay, duplicate delivery history, and conflict preservation.
3. **Transport checkpoints:** monotonicity, gap detection, reconnect, sequence reset, and atomic rollback tests.
4. **Normalized event persistence:** adapter versioning, invalid payload handling, and deterministic re-normalization.
5. **Timeline generations:** bank-aware rebuild, orphan retention, forks, and continuity boundaries.
6. **Backfill jobs:** partial/complete/unknown coverage, overlap with live ingestion, pagination and provider limits.
7. **Restart and restore:** crash injection, backup/restore, replay after restart, and no false checkpoint advancement.

Required tests include duplicate content across streams, same identity with different bytes, out-of-order delivery, gap and reconnect, sequence reset, failure at every transactional write boundary, late metadata, bank invalidation, sibling forks, backfill/live overlap, incomplete provider coverage, failed projection rebuild, and restart from a corrupted or partial checkpoint.

## 12. Compatibility with the existing SMR architecture

- Keep `SQLiteEventStore` and its transaction/swap tables and wallet checkpoints unchanged.
- Keep `NormalizedAccountUpdate`, `geyser_proto_adapter.py`, `BankLineageTracker`, and `AccountUpdateTimeline` provider-neutral.
- Do not use `stream_sequence` as ledger order or `write_version` as instruction order.
- Do not infer BUY/SELL, canonicality, or permission to trade from persisted account transitions.
- The storage adapter must not silently change the semantics of existing swap reconciliation or wallet monitoring.

## 13. Current implementation status

The initial offline RAW persistence slice is now implemented in PR #23:
- `src/smart_money_radar/storage/geyser_raw_store.py` defines `SQLiteGeyserRawStore`, `RawEventInput`, `RawDeliveryInput`, and `RawIngestResult`;
- schema migration v1 creates a dedicated RAW event table, delivery table, conflict table, migration ledger, and lookup indexes;
- file-backed stores use WAL and `synchronous=FULL`; in-memory stores support deterministic offline tests;
- event content is stored separately from each delivery. Replays of identical content add delivery rows without duplicating RAW content;
- reuse of an event_id with incompatible source/kind/schema/encoding/bytes preserves the original RAW row, records the incoming bytes and hashes as a conflict, and records the attempted delivery;
- each ingest transaction atomically stores the RAW row (when new) and its delivery. A forced delivery insert failure is tested to roll back the new RAW row;
- SHA-256 is computed over the exact supplied payload bytes. `protobuf_wire` may be declared only when the caller actually captured wire bytes; this store does not manufacture or infer that provenance.

Validation:
- CI #1645, run `44462300540`, push: SUCCESS; 522/522 tests and `python -m compileall -q src tests` passed on `92ba36d494e23932d11ec4b7c25ffd9afebe2916`.
- CI #1646, run `44462306301`, pull_request: SUCCESS; 522/522 tests and compileall passed on the same commit.

The offline transport checkpoint/gap slice is also implemented in PR #23:
- schema migration v2 adds `geyser_transport_checkpoints`, `geyser_transport_gaps`, and `geyser_transport_anomalies`;
- `register_stream(source_id, stream_id, initial_sequence)` records an adapter-declared first expected sequence before ingestion;
- if no explicit registration exists, the first observed sequence becomes a baseline marked `first_observed_unverified`; this does not prove that earlier sequences were delivered;
- `contiguous_sequence` advances only through sequences with durable delivery rows. A later sequence creates explicit missing ranges, is retained, and does not move the contiguous checkpoint across the gap;
- out-of-order arrivals can close a gap only after every sequence from the baseline through the observed high-water mark is present. Superseded and resolved gap records remain auditable;
- replay of the same event at the same sequence is idempotent for continuity. A different event reusing a sequence, an unidentifiable RAW identity conflict, or a sequence before the declared baseline creates an open transport anomaly and interrupts the checkpoint;
- anomalies require an explicit resolution note; resolving an anomaly does not clear the interrupted flag while any gap or other open anomaly remains;
- RAW event, delivery, gap/anomaly evidence, and transport checkpoint update share the same SQLite transaction. A forced gap-write failure test proves that RAW, delivery, and checkpoint changes all roll back together;
- transport checkpoints are scoped by `(source_id, stream_id)`; reconnects must use a new stream_id. This store does not infer sequence-reset semantics.

Validation of the transport slice:
- CI #1660, run `44508678117`, push: SUCCESS; 530/530 tests and `python -m compileall -q src tests` passed on `b470a5eb02025512569d83d667d82ddc55a33ec5`.
- CI #1661, run `44508689458`, pull_request: SUCCESS; 530/530 tests and compileall passed on the same commit.
- Added a schema-upgrade test that starts from an existing v1 database and verifies the v2 migration preserves integrity.
- CI #1664, run `44508979168`, push: SUCCESS; 531/531 tests and compileall passed on `5d66bd1b50559ed9f4ede06461c2b4cf0ac9cf9b`.
- CI #1665, run `44508987457`, pull_request: SUCCESS; 531/531 tests and compileall passed on the same commit.
- Earlier runs #1654–#1659 exposed a test assertion mismatch in the expected error message for late baseline registration; corrected before the successful HEAD above.

Implemented deterministic event identity and offline normalized ingestion:
- `src/smart_money_radar/data_sources/geyser_event_identity.py` defines the versioned event identity contract.
- `src/smart_money_radar/data_sources/geyser_ingestion.py` exposes `ingest_normalized_event(store, event, schema_version=...)` for Account, Slot, BlockMeta, and EntryUpdateParent.
- The coordinator derives the deterministic `event_id`, serializes provider-neutral normalized content as canonical UTF-8 JSON (`payload_encoding=normalized_json`), and persists it through the immutable RAW store.
- Transport `stream_id` and `stream_sequence` are persisted only as a separate delivery; they are excluded from the canonical payload and logical identity.
- Account bytes are represented losslessly as Base64 in normalized JSON; opaque EntryUpdateParent bytes are represented as hex. This is a normalized representation, not protobuf wire capture.
- Reconnect replay with the same logical event creates another delivery but does not duplicate the RAW event. Changed content under the same logical event ID becomes an immutable RAW conflict.
- The coordinator is offline and does not create a gRPC client, connect to a provider, or claim to capture original protobuf wire bytes.

Validation for the normalized-ingestion coordinator:
- CI #1686, run `44515088642`, pull_request event, code HEAD `0beb6c26f2ac6833cb7ebff5861d208c2a1c307b`: SUCCESS; **544/544 tests OK** in 4.035 s; `python -m compileall -q src tests` passed.

Validation for deterministic identity:
- CI #1674, run `44510167848`, pull_request event, HEAD `bde85727630b4f37994852c67594a9c70887d1a3`: SUCCESS; **539/539 tests OK** in 3.843 s; `python -m compileall -q src tests` passed.

Still not implemented:
- dedicated normalized-event projections/tables, account-write index, persistent timeline generations, historical backfill, and restart recovery;
- dedicated continuity epochs, account-write projections/index, timeline generations, backfill jobs, or restart orchestration;
- live Yellowstone/Helius client, original protobuf wire-byte capture boundary, provider connection, credentials, continuous capture, or financial/on-chain execution.

No provider connection or financial execution is authorized by this document.


## Implementação offline da projeção persistente de account writes — 19/11/2026

### Implementação
- Criado `src/smart_money_radar/storage/geyser_account_write_projection.py`.
- Criado `tests/test_geyser_account_write_projection.py`.
- Classe: `SQLiteGeyserAccountWriteProjection`; API principal: `rebuild()`, `get_checkpoint()` e `list_writes()`.
- A projeção compartilha o arquivo dedicado `smr_geyser.sqlite`; não reutiliza `smr_events.sqlite`.
- Materializa somente eventos `event_kind=account` com `payload_encoding=normalized_json`. Outros tipos e encodings são contabilizados como ignorados, não reinterpretados.
- Preserva `event_id`, source, pubkey, slot, write_version, bank_id, is_startup, txn_signature, lamports, owner, executable, rent_epoch, schema_version e os dados binários em Base64. Calcula também tamanho e SHA-256 dos bytes decodificados.
- A tabela `geyser_account_writes` é uma projeção derivada; o RAW continua sendo a fonte autoritativa.
- Checkpoint separado em `geyser_projection_checkpoints`, com nome/versão da projeção, geração, contagem de eventos fonte, contagem projetada/ignoradas, maior event_id observado e horário da reconstrução.
- Reconstrução integral e atômica: lê o conjunto RAW de account/normalized_json, valida e materializa, substitui a projeção e atualiza checkpoint dentro da mesma transação SQLite. Registro malformado aborta a transação e mantém a projeção/checkpoint anteriores.
- Reconstrução integral foi escolhida deliberadamente nesta versão: um cursor incremental baseado em event_id poderia perder eventos RAW que chegassem tardiamente ou por backfill com chave lexical anterior ao cursor. O campo source_max_event_id é diagnóstico, não cursor incremental.

### Testes e CI
- Seis testes novos cobrem materialização e preservação dos bytes, reconstrução idempotente/versionada, chegada tardia, contagem de eventos ignorados, rollback em RAW normalizado malformado e separação do checkpoint de transporte.
- CI #1693 — run `44516277804`, push, commit `b62e8660b4bc32c9d921e5fcf09bdfdb428fbb67`: completed/success; **550/550 testes OK** em 4,216 s; `python -m compileall -q src tests` aprovado.

### Limites preservados
- Projeção offline; nenhum cliente gRPC, stream Yellowstone/Helius, captura wire, backfill real ou serviço foi conectado.
- Não cria ainda timeline persistente, estado canônico de forks, transições pre/post, checkpoint incremental de projeção ou rotina de rebuild após reinício.
- Reconstrução integral carrega os registros elegíveis em memória e mantém transação de escrita durante a operação; desempenho deverá ser medido antes de escolher estratégia incremental segura.
- A projeção não converte estado de conta em swap, BUY/SELL, sinal ou autorização de execução.


## Timeline persistente e reconstruível de contas/bancos — 19/11/2026

### Implementação
- Criado `src/smart_money_radar/storage/geyser_account_timeline_projection.py`.
- Criado `tests/test_geyser_account_timeline_projection.py`.
- A API `SQLiteGeyserAccountTimelineProjection` oferece `rebuild()`, `get_checkpoint()`, `list_account_writes()`, `list_banks()`, `list_gaps()` e `list_conflicts()`.
- A projeção é armazenada no mesmo arquivo dedicado `smr_geyser.sqlite`; não toca no banco `smr_events.sqlite`.
- O rebuild lê o RAW imutável e usa a primeira entrega com sequência de transporte conhecida de cada evento lógico; ordena a reprodução por `delivery_id`. Eventos sem payload `normalized_json`, sem entrega sequenciada ou sem entrega são contabilizados como ignorados. Payload normalizado malformado aborta o rebuild.
- As timelines são reconstruídas separadamente por `source_id`; fontes distintas não são tratadas como reconexões uma da outra.
- Persiste escritas ativas com `event_id`, chave de conta/ledger, `continuity_epoch`, baseline, baseline após quebra de continuidade e status de observação do banco.
- Persiste nós de banco com parent slot, blockhash/parent blockhash, vínculo exato de banco pai quando comprovado, statuses, dead, invalidated, cleared_by_parent_update, parent_block_id opaco em hex e relação replaces_bank.
- Persiste gaps e conflitos de timeline/linhagem; APIs de leitura expõem esses registros.
- Bancos invalidados e escritas associadas não são apagados: ficam no histórico derivado com estado `invalidated`. A projeção não promove automaticamente um fork a canônico.
- Checkpoint versionado e geração própria. Rebuild integral, com substituição de escritas, nós, gaps, conflitos e checkpoint na mesma transação SQLite. Falha mantém geração anterior.
- `AccountUpdateTimeline.timeline_records()` fornece snapshot de leitura dos registros ativos com metadados de continuidade, sem expor mutabilidade interna.

### Testes e CI
- Nove testes específicos cobrem: persistência de timeline/linhagem; vínculo exato por blockhash; preservação de parent_block_id opaco e invalidação; escrita associada a banco invalidado; repetibilidade/checkpoint; inclusão de RAW tardio; rollback em payload corrompido; persistência de gap e quebra de predecessor; isolamento entre fontes.
- CI #1706 — run `44517573857`, commit `6bf265be4f9f7cd48ba1044ad19272c8b1a4095b`: SUCCESS; **559/559 testes OK** em 4,247 s; `python -m compileall -q src tests` aprovado.

### Limites
- Reconstrução offline a partir de eventos já normalizados; não é captura protobuf wire, stream Geyser, nem backfill real.
- Ordem de entrega é usada apenas para reproduzir a lógica de continuidade; não declara canonicalidade de fork.
- A projeção ainda não materializa uma tabela de transições econômicas pre/post, nem executa rollback canônico automático. Não existe inferência de BUY/SELL ou autorização de trade.
- Rebuild integral mantém os registros elegíveis em memória; desempenho precisa ser medido com volume real.
- Eventos RAW sem uma entrega com sequência conhecida são ignorados na timeline e contabilizados no checkpoint; RAW permanece preservado.

### Próxima etapa
Definir e implementar recuperação/backfill e checkpoints de projeção mais granulares, com cobertura auditável e reconciliação de eventos sem sequência. Não conectar provider nem declarar fork canônico por heurística.


## Offline recovery and backfill state store — 19/11/2026

### Implemented

- Added `src/smart_money_radar/storage/geyser_recovery_store.py` with `SQLiteGeyserRecoveryStore`, sharing the dedicated `smr_geyser.sqlite` database and keeping `smr_events.sqlite` untouched.
- Recovery metadata has its own versioned migration table, independent from the RAW store schema migration.
- `geyser_backfill_jobs` persists source, inclusive slot range, provider/adapter/schema versions, query semantics, opaque start/current/end cursors, lifecycle status, coverage status, counters, retry count, last error, evidence, and timestamps.
- `geyser_backfill_attempts` records every attempt, its starting/ending cursor, status, timestamps, and error. Retries resume from the last durably recorded cursor and receive a new monotonically increasing attempt number.
- Lifecycle API: `create_backfill_job()`, `start_backfill_job()`, `update_backfill_progress()`, `finish_backfill_job()`, `recover_interrupted_jobs()`, `get_backfill_job()`, `list_backfill_jobs()`, and `list_backfill_attempts()`.
- On restart, `recover_interrupted_jobs()` changes abandoned RUNNING jobs with received data to PARTIAL/PARTIAL, and jobs with no received data to FAILED/UNKNOWN. It preserves the cursor and records the attempt as INTERRUPTED; it does not fabricate coverage or mark a job complete.
- Progress counters cannot regress. Only RUNNING jobs accept progress or finalization. PARTIAL/FAILED jobs can be retried; COMPLETED jobs cannot be restarted.
- COMPLETED requires coverage COMPLETE and structured evidence asserting a confirmed provider contract, full requested range, exhausted pagination, checked retention limits, and exact match with the job's recorded query semantics. The store records adapter-supplied evidence; it cannot independently prove provider claims.
- `geyser_projection_checkpoints` stores projection name/version and source-scoped generation, last delivery/event, source/projected counts, skipped unsequenced count, input coverage, and continuity-interrupted flag. Generation and delivery high-water marks cannot regress. COMPLETE is rejected when continuity is interrupted or any unsequenced event was skipped.
- Projection checkpoints are written after a successful projection generation. If a process stops between the projection commit and this separate checkpoint write, the checkpoint lags safely; it must never be advanced before the projection commit. The existing timeline rebuild remains a full rebuild and is not yet automatically wired to this metadata API.

### Explicit limits

- This is an offline persistence/control layer, not a provider adapter, scheduler, pagination client, or live backfill executor.
- Slot ranges and provider query semantics are recorded; no provider-specific completeness guarantee is assumed.
- Cursor values are opaque strings; the store does not interpret provider cursor ordering.
- A caller-supplied evidence object is auditable provenance, not independent proof that a provider returned every historical update.
- Transport continuity, projection input coverage, and provider backfill coverage remain separate concepts. No single cursor substitutes for the others.
- RAW events and deliveries remain immutable and authoritative. This module does not rewrite RAW payloads, infer missing events, select canonical forks, generate BUY/SELL, or execute trades.
- No Yellowstone/Helius endpoint, credential, client, service, VPS, or paid backfill was connected.

### Tests

- Added `tests/test_geyser_recovery_store.py` for job lifecycle, complete-coverage evidence, query-contract mismatch, monotonic counters, restart recovery, cursor-preserving retry, source-scoped projection checkpoints, coverage fail-closed rules, generation monotonicity, and invalid state/range rejection.
- CI #1733 — run `44519550364`, commit `f90fd43bbbd03c7c03bfbf7b23ca5907e5d60066`: SUCCESS; **569/569 tests OK** in 4.343 s; `python -m compileall -q src tests` passed.
- Earlier runs #1727 and #1731 exposed two test expectation/attempt-audit defects; both were corrected before #1733. The successful run includes the corrected recovery behavior.
