"""Read-only integration snapshot for two independent SMR radars.

This presentation adapter reuses existing classification and risk contracts.
It never mutates a radar, invents source provenance, requests RPC or places orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from smart_money_radar.services.opportunity_classifier import OpportunityClassification
from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk,
)

RadarName = Literal["launch", "smart_money"]
Coverage = Literal["COMPLETE", "PARTIAL", "UNKNOWN", "GAP"]


@dataclass(frozen=True)
class RadarObservation:
    """Immutable scope-bound transport evidence, not independent RPC attestation."""

    radar: RadarName
    source_id: str
    pool: str
    signature: str | None
    slot: int | None
    available_at: datetime | None
    raw_payload: bytes | None
    raw_sha256: str | None
    coverage: Coverage = "UNKNOWN"
    source_authenticated: bool = False


@dataclass(frozen=True)
class RadarIntegrationSnapshot:
    radar: RadarName
    source_id: str
    pool: str
    signature: str | None
    slot: int | None
    available_at: datetime | None
    raw_sha256: str | None
    coverage: Coverage
    evidence_status: Literal["UNKNOWN", "CONFLICTED", "LOCALLY_CONSISTENT"]
    verdict: str
    reasons: tuple[str, ...]
    paper_modes: tuple[tuple[str, str], ...]
    operational_authorized: bool = False


def compose_radar_snapshot(
    observation: RadarObservation,
    *,
    classification: OpportunityClassification | None = None,
    risk_limits: EntryRiskLimits | None = None,
    risk_snapshot: EntryRiskSnapshot | None = None,
    emergency_halt: bool = False,
) -> RadarIntegrationSnapshot:
    """Bind existing evidence, intelligence and risk without granting permissions.

    Each radar produces its own snapshot. The caller must never convert local
    hash equality, caller-declared auth, or COMPLETE coverage into trading proof.
    """
    if not isinstance(observation, RadarObservation):
        raise TypeError("radar observation contract required")
    if observation.radar not in ("launch", "smart_money"):
        raise ValueError("unknown radar")
    if any(not isinstance(x, str) or not x.strip()
           for x in (observation.source_id, observation.pool)):
        raise ValueError("source and pool required")
    if type(emergency_halt) is not bool:
        raise ValueError("emergency flag must be bool")
    if observation.coverage not in ("COMPLETE", "PARTIAL", "UNKNOWN", "GAP"):
        raise ValueError("invalid coverage")
    if observation.slot is not None and (
        type(observation.slot) is not int or observation.slot < 0
    ):
        raise ValueError("invalid slot")
    if observation.signature is not None and (
        not isinstance(observation.signature, str) or not observation.signature.strip()
    ):
        raise ValueError("invalid signature")
    if observation.available_at is not None and (
        not isinstance(observation.available_at, datetime)
        or observation.available_at.utcoffset() is None
    ):
        raise ValueError("timezone-aware publication time required")
    if observation.raw_sha256 is not None and (
        not isinstance(observation.raw_sha256, str)
        or len(observation.raw_sha256) != 64
        or any(c not in "0123456789abcdef" for c in observation.raw_sha256)
    ):
        raise ValueError("invalid SHA-256")
    if type(observation.source_authenticated) is not bool:
        raise ValueError("invalid authentication claim")

    reasons: set[str] = set()
    if observation.raw_payload is not None:
        if not isinstance(observation.raw_payload, bytes):
            raise ValueError("RAW must be bytes")
        if not observation.raw_sha256:
            reasons.add("raw_sha256_missing")
        elif sha256(observation.raw_payload).hexdigest() != observation.raw_sha256:
            reasons.add("raw_sha256_conflict")
    else:
        reasons.add("raw_missing")
    if observation.available_at is None:
        reasons.add("publication_time_missing")
    if observation.slot is None:
        reasons.add("slot_missing")
    if observation.signature is None:
        reasons.add("signature_missing")
    if observation.coverage != "COMPLETE":
        reasons.add("historical_coverage_unproven")
    # Even locally consistent bytes do not authenticate the provider.
    if not observation.source_authenticated:
        reasons.add("source_not_authenticated")

    if classification is not None:
        if not isinstance(classification, OpportunityClassification):
            raise TypeError("existing classification contract required")
        if observation.radar != "smart_money":
            raise ValueError("launch classification must use an explicit launch contract")
        if classification.pool != observation.pool or classification.source_id != observation.source_id:
            raise ValueError("classification source/pool mismatch")
        if (observation.available_at is None
                or classification.as_of < observation.available_at):
            raise ValueError("classification precedes data availability")
        if classification.operational_authorized:
            raise ValueError("unsafe operational permission")
        reasons.update(classification.reasons)
        verdict = classification.verdict
    else:
        verdict = "UNKNOWN"
        reasons.add("classification_missing")

    if (risk_limits is None) != (risk_snapshot is None):
        raise ValueError("risk limits and snapshot must be provided together")
    if risk_limits is not None:
        if not isinstance(risk_limits, EntryRiskLimits) or not isinstance(risk_snapshot, EntryRiskSnapshot):
            raise TypeError("existing risk policy contracts required")
        reasons.update(evaluate_entry_risk(risk_limits, risk_snapshot))
    else:
        reasons.add("risk_policy_missing")
    if emergency_halt or (risk_snapshot is not None and risk_snapshot.emergency_halt):
        reasons.add("emergency_halt")
    if classification is not None and classification.verdict == "REJECTED":
        reasons.add("classification_rejected")
    elif classification is not None and classification.verdict == "UNKNOWN":
        reasons.add("classification_unknown")

    conflict = bool({"raw_sha256_conflict", "classification_rejected"} & reasons)
    evidence_status = (
        "CONFLICTED" if conflict
        else "LOCALLY_CONSISTENT" if (
            observation.raw_payload is not None
            and observation.raw_sha256 is not None
            and observation.available_at is not None
            and observation.slot is not None
            and observation.signature is not None
        ) else "UNKNOWN"
    )
    # Deliberately never promote positive simulation candidates from this
    # adapter: local data does not establish executable quote provenance.
    modes = (("immediate", "BLOCKED"), ("confirmed", "BLOCKED"))
    return RadarIntegrationSnapshot(
        radar=observation.radar, source_id=observation.source_id,
        pool=observation.pool, signature=observation.signature,
        slot=observation.slot,
        available_at=observation.available_at.astimezone(timezone.utc)
        if observation.available_at is not None else None,
        raw_sha256=observation.raw_sha256, coverage=observation.coverage,
        evidence_status=evidence_status, verdict=verdict,
        reasons=tuple(sorted(reasons)), paper_modes=modes,
        operational_authorized=False,
    )
