# Solana Geyser commitment/finality policy

## Purpose

This policy defines the minimum commitment evidence required before a bank-scoped account transition may be exposed as eligible historical evidence. It is provider-neutral and does not authenticate a provider.

## Commitment observations

The tracker preserves provider-reported slot lifecycle states without treating them as interchangeable:

- `PROVIDER_REPORTED_PROCESSED`: observed at processed commitment; never eligible.
- `PROVIDER_REPORTED_CONFIRMED`: observed at confirmed commitment; never eligible.
- `PROVIDER_REPORTED_FINALIZED`: provider reported `SLOT_FINALIZED`; necessary, but not by itself proof of provider authenticity or canonicality.
- `UNKNOWN`, `DEAD`, `INVALIDATED`, and `CONFLICTED`: ineligible.

A transition requires both its prestate bank and poststate bank to be provider-reported finalized. For cross-bank transitions, every explicitly linked ancestor in the bank lineage must also be finalized and usable. Missing ancestry is not inferred.

## Rollback, forks, and contradictions

- `SLOT_DEAD`, EntryUpdateParent invalidation, and explicit rollback keep affected observations ineligible.
- Conflicting blockhash or parent metadata taints the bank identity; later observations cannot rehabilitate it merely by reporting FINALIZED.
- A replacement bank is a distinct identity. No automatic fork selection or retroactive repair is performed.
- RAW observations and orphaned updates remain audit evidence; they are not promoted as active transitions.

## Trust boundary

`SLOT_FINALIZED` is a provider statement. This implementation labels it `PROVIDER_REPORTED_FINALIZED`; it does not claim cryptographic authentication, quorum verification, or independent proof of consensus finality. A future operational adapter must define provider authentication, endpoint identity, transport integrity, reconnect semantics, and rollback handling before any live evidence can be marked operationally VERIFIED.

## Validation scope

Unit tests establish deterministic fail-closed behavior for commitment progression, ancestor finality, conflicts, and timeline eligibility. They do not establish correctness of a live provider integration or production consensus.
