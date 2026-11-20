"""Audit-only join of first-publication receipt, stored RAW and quote identity.

The archive currently lacks independently attested provider provenance.
This module cannot elevate a locally consistent hash to authenticated status.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from smart_money_radar.services.receipt_raw_link import ReceiptRawLink
from smart_money_radar.services.observed_quote_gate import ObservedQuoteEvidence, QuoteGateResult

ChainStatus = Literal["INCOMPLETE", "CONFLICTED", "LOCALLY_LINKED_UNATTESTED"]


@dataclass(frozen=True)
class EvidenceChain:
    operation_id: str
    signature: str
    slot: int | None
    pool: str
    quote_id: str | None
    source_id: str | None
    cutoff: datetime
    raw_local_sha256: str | None
    quote_raw_sha256: str | None
    status: ChainStatus
    reasons: tuple[str, ...]
    provider_authenticated: bool = False
    finalized_attested: bool = False
    executable_price_verified: bool = False


def bind_evidence_chain(
    *, receipt: ReceiptRawLink, quote: ObservedQuoteEvidence | None,
    quote_gate: QuoteGateResult | None, cutoff: datetime,
    expected_pool: str, expected_source: str | None = None,
) -> EvidenceChain:
    """Reconcile independent identities, never infer missing evidence.

    Local equality of claims is only a consistency check. Network finality
    and provider authenticity require a separate attestation, not a boolean
    supplied by a caller. This contract deliberately never authorizes replay.
    """
    if not isinstance(receipt, ReceiptRawLink):
        raise TypeError("recibo RAW inválido")
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff requer fuso")
    if not isinstance(expected_pool, str) or not expected_pool.strip():
        raise ValueError("pool obrigatório")
    point = cutoff.astimezone(timezone.utc)
    reasons = set(receipt.reasons)
    conflicts = set()
    if receipt.pool != expected_pool:
        conflicts.add("receipt_pool_mismatch")
    if receipt.available_at > point:
        conflicts.add("receipt_after_cutoff")
    if receipt.observed_at is not None and receipt.observed_at > point:
        conflicts.add("raw_after_cutoff")
    if expected_source is not None and receipt.source_id != expected_source:
        conflicts.add("receipt_source_mismatch")
    if receipt.slot is None:
        reasons.add("receipt_slot_unknown")
    if not receipt.local_payload_sha256:
        reasons.add("receipt_raw_hash_missing")
    if not receipt.signature or not receipt.operation_id:
        reasons.add("receipt_identity_missing")
    if not receipt.provider_authenticated:
        reasons.add("receipt_provider_not_authenticated")
    if not receipt.finalized_attested:
        reasons.add("receipt_finality_unknown")
    if quote is None or quote_gate is None:
        reasons.add("quote_or_gate_missing")
    else:
        if not isinstance(quote, ObservedQuoteEvidence) or not isinstance(quote_gate, QuoteGateResult):
            raise TypeError("cotação/gate inválidos")
        if quote.quote_id != quote_gate.quote_id:
            conflicts.add("quote_id_mismatch")
        if quote.pool != expected_pool or quote_gate.pool != expected_pool:
            conflicts.add("quote_pool_mismatch")
        if quote.slot != quote_gate.slot:
            conflicts.add("quote_gate_slot_mismatch")
        if receipt.slot is not None and receipt.slot != quote.slot:
            conflicts.add("transaction_quote_slot_mismatch")
        if quote.source_id != quote_gate.source_id:
            conflicts.add("quote_gate_source_mismatch")
        if expected_source is not None and quote.source_id != expected_source:
            conflicts.add("quote_source_mismatch")
        if receipt.source_id is not None and quote.source_id != receipt.source_id:
            conflicts.add("cross_source_identity_conflict")
        if (quote.available_at > point or quote.market_at > point
                or quote.observed_at > point or quote_gate.available_at > point):
            conflicts.add("quote_after_cutoff")
        if quote.available_at != quote_gate.available_at:
            conflicts.add("quote_gate_availability_mismatch")
        if not isinstance(quote.raw_payload, bytes) or (
                sha256(quote.raw_payload).hexdigest() != quote.raw_sha256):
            conflicts.add("quote_raw_hash_mismatch")
        if quote_gate.status != "CANDIDATE_PAPER_ONLY":
            reasons.add("quote_gate_not_accepted")
        if quote_gate.tick is None:
            reasons.add("quote_tick_unavailable")
        elif (quote_gate.tick.quote_id != quote.quote_id
              or quote_gate.tick.at != quote.available_at
              or quote_gate.tick.market_at != quote.market_at):
            conflicts.add("quote_tick_identity_mismatch")
        if quote_gate.economics_supported:
            # A caller cannot promote paper quotes to economically validated.
            conflicts.add("unsupported_economic_promotion")
        if not quote.provider_attested:
            reasons.add("quote_provider_not_attested")
        if not quote.depth_attested:
            reasons.add("quote_depth_not_attested")
    reasons.update(conflicts)
    if conflicts:
        status: ChainStatus = "CONFLICTED"
    elif (quote is None or quote_gate is None or receipt.slot is None
          or not receipt.local_payload_sha256 or not receipt.signature
          or not receipt.operation_id):
        status = "INCOMPLETE"
    else:
        status = "LOCALLY_LINKED_UNATTESTED"
    return EvidenceChain(
        operation_id=receipt.operation_id, signature=receipt.signature,
        slot=receipt.slot, pool=expected_pool,
        quote_id=quote.quote_id if quote is not None else None,
        source_id=receipt.source_id, cutoff=point,
        raw_local_sha256=receipt.local_payload_sha256,
        quote_raw_sha256=quote.raw_sha256 if quote is not None else None,
        status=status, reasons=tuple(sorted(reasons)),
    )
