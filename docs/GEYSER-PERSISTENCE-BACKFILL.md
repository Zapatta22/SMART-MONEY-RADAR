# Geyser Historical Persistence and Backfill Contract

**Status:** Architecture specification approved for documentation; implementation not started.  
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

Implemented deterministic event identity for normalized Geyser events:
- `src/smart_money_radar/data_sources/geyser_event_identity.py` defines `IDENTITY_VERSION = "geyser-event-id:v1"`, `EventIdentity`, and `derive_event_identity(event, schema_version=...)`;
- canonical SHA-256 identity includes identity-contract version, explicit upstream schema version, event kind, and the logical key for Account, Slot, BlockMeta, or EntryUpdateParent;
- transport `stream_id` and `stream_sequence` are excluded, so reconnect/replay does not change the logical event identity;
- payload fields intentionally excluded from the logical key remain protected by immutable RAW content comparison. Reusing an identity with changed bytes is a conflict, not a second event or silent duplicate;
- this helper accepts provider-neutral normalized event objects. It does not decode protobuf, capture wire bytes, persist events, or automatically invoke itself from the transport adapter; the future ingestion coordinator must call it and pass its `event_id` to RAW storage;
- `protobuf_wire` provenance remains valid only when bytes were captured before protobuf decoding. The current adapter receives decoded objects.

Validation for deterministic identity is pending CI at this point in the document. The exact commit/run and test count will be added after the workflow completes.

Still not implemented:
- automatic invocation of the identity helper by a transport/ingestion coordinator and normalized-event persistence;
- continuity checkpoints/epochs, account-write persistence, timeline generations, backfill jobs, or restart orchestration;
- live Yellowstone/Helius client, wire-byte capture boundary, provider connection, credentials, continuous capture, or financial/on-chain execution.

No provider connection or financial execution is authorized by this document.
