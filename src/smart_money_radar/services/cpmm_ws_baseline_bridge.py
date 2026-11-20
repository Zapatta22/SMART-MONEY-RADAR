"""Conservative Solana accountSubscribe <-> contemporaneous RPC baseline bridge.

All WebSocket frames are archived by the existing SQLiteGeyserRawStore.
Account notifications may arrive before, during or after an RPC call. A
baseline cannot prove full stream coverage, ledger write ordering, signatures
or historical availability at the beginning of a WS connection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal
import base64
import json

from smart_money_radar.services.prospective_cpmm_account_snapshot import (
    ProspectiveCpmmSnapshot, inspect_prospective_cpmm_response,
)
from smart_money_radar.services.cpmm_public_ws_capture import (
    LiveRpcAccountObservation, PublicCpmmWsSession,
)

Coverage = Literal["UNKNOWN", "PARTIAL", "CONFLICT"]


@dataclass(frozen=True)
class BaselineComparison:
    account: str
    baseline_slot: int
    notification_slot: int
    relationship: Literal[
        "BEFORE_BASELINE_SLOT", "SAME_SLOT_STATE_MATCH",
        "SAME_SLOT_STATE_CONFLICT", "AFTER_BASELINE_SLOT",
        "UNKNOWN", "CONFLICT",
    ]
    baseline_binary_sha256: str
    notification_binary_sha256: str
    notification_raw_sha256: str
    notification_observed_at: str
    reasons: tuple[str, ...]
    transaction_signature: None = None
    write_version: None = None
    economic_execution_authorized: bool = False


@dataclass(frozen=True)
class BaselineAudit:
    baseline_status: str
    baseline_slot: int | None
    baseline_request_sha256: str
    baseline_response_sha256: str
    requested_at: str
    available_at: str
    account_observations: tuple[BaselineComparison, ...]
    coverage: Coverage
    reasons: tuple[str, ...]
    baseline_validated_as_snapshot: bool
    continuous_updates_proven: bool = False
    global_order_proven: bool = False
    provider_independently_authenticated: bool = False
    transaction_signature_proven: bool = False
    economic_execution_authorized: bool = False


def inspect_contemporaneous_baseline(
    *, session: PublicCpmmWsSession,
    response_raw: bytes,
    request_raw: bytes,
    requested_at: datetime,
    available_at: datetime,
    endpoint: str,
    original_swap_slot: int,
    authority: str,
    input_mint: str,
    output_mint: str,
    input_token_program: str,
    output_token_program: str,
    notifications: tuple[tuple[LiveRpcAccountObservation, bytes], ...] = (),
    cutoff: datetime,
) -> BaselineAudit:
    """Reuse existing strict four-account decoder; compare notification bytes.

    Input notification tuples include *original RAW bytes*. An unverified
    observation without its frame cannot be used for any comparison. The
    returned result never upgrades the transport continuity claim to COMPLETE.
    """
    if not isinstance(session,PublicCpmmWsSession):
        raise TypeError("existing WebSocket session required")
    for stamp in (requested_at, available_at, cutoff):
        if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
            raise ValueError("timestamp with timezone required")
    if requested_at > available_at:
        raise ValueError("baseline availability before request")
    if available_at > cutoff:
        raise ValueError("baseline response after cutoff")
    if not isinstance(request_raw,bytes) or not isinstance(response_raw,bytes):
        raise TypeError("original RPC RAW required")
    accounts=session.accounts
    snapshot=inspect_prospective_cpmm_response(
        response_raw=response_raw, request_raw=request_raw,
        source_id="solana-public-mainnet", endpoint=endpoint,
        observed_at=requested_at, available_at=available_at,
        pool=accounts[0], amm_config=accounts[1],
        input_vault=accounts[2], output_vault=accounts[3],
        input_mint=input_mint, output_mint=output_mint,
        authority=authority, input_token_program=input_token_program,
        output_token_program=output_token_program,
        original_swap_slot=original_swap_slot,
    )
    reasons={"ws_receipt_order_is_not_ledger_write_order",
             "no_continuous_delivery_proof",
             "rpc_provider_independent_attestation_missing",
             "subscription_to_baseline_race_unresolved"}
    valid=snapshot.status=="RPC_DECLARED_PROSPECTIVE_ONLY"
    baseline_hashes=snapshot.account_sha256
    if not valid:
        reasons.add("baseline_missing_invalid_or_conflicted")
    try:
        payload=json.loads(response_raw)
        base_accounts=payload["result"]["value"]
        slot=payload["result"]["context"]["slot"]
        binary_hashes=tuple(sha256(base64.b64decode(
            account["data"][0],validate=True)).hexdigest() for account in base_accounts)
    except (ValueError,TypeError,KeyError,IndexError,base64.binascii.Error):
        binary_hashes=()
        slot=None
        reasons.add("baseline_binary_unavailable")
    rows=[]
    for observation,raw in notifications:
        if not isinstance(observation,LiveRpcAccountObservation):
            raise TypeError("observation must be parsed by existing WS adapter")
        if not isinstance(raw,bytes):
            raise TypeError("notification original RAW required")
        if sha256(raw).hexdigest()!=observation.raw_sha256:
            raise ValueError("notification RAW integrity conflict")
        if observation.account not in accounts:
            raise ValueError("notification outside four-account scope")
        seen_time=datetime.fromisoformat(observation.observed_at)
        if seen_time.utcoffset() is None or seen_time>cutoff:
            raise ValueError("notification after cutoff or without timezone")
        j=json.loads(raw)
        sub=j["params"]["subscription"]
        if j.get("method")!="accountNotification" or sub!=observation.subscription_id:
            raise ValueError("notification envelope conflict")
        if j["params"]["result"]["context"]["slot"]!=observation.slot:
            raise ValueError("notification slot changed")
        value=j["params"]["result"]["value"]
        binary=base64.b64decode(value["data"][0],validate=True)
        notification_sha=sha256(binary).hexdigest()
        reasons_for_row=[]
        if not valid or len(binary_hashes)!=4 or slot is None:
            relation="UNKNOWN"
            reasons_for_row.append("baseline_unverified")
        else:
            expected=baseline_hashes[accounts.index(observation.account)]
            if observation.slot<slot:
                relation="BEFORE_BASELINE_SLOT"
                reasons_for_row.append("arrival_time_does_not_prove_ledger_order")
            elif observation.slot>slot:
                relation="AFTER_BASELINE_SLOT"
                reasons_for_row.append("post_snapshot_change_not_continuously_attested")
            elif notification_sha==expected:
                relation="SAME_SLOT_STATE_MATCH"
                reasons_for_row.append("same_slot_does_not_prove_same_write")
            else:
                relation="SAME_SLOT_STATE_CONFLICT"
                reasons_for_row.append("same_slot_payload_differs_without_write_version")
                reasons.add("same_slot_conflicting_binary")
        if observation.status=="CONFLICT":
            relation="CONFLICT"
            reasons_for_row.append("ws_adapter_conflict")
            reasons.add("websocket_notification_conflict")
        rows.append(BaselineComparison(
            account=observation.account,baseline_slot=slot or 0,
            notification_slot=observation.slot,relationship=relation,
            baseline_binary_sha256=baseline_hashes[accounts.index(observation.account)]
                if valid and len(baseline_hashes)==4 else "",
            notification_binary_sha256=notification_sha,
            notification_raw_sha256=observation.raw_sha256,
            notification_observed_at=observation.observed_at,
            reasons=tuple(sorted(reasons_for_row))))
    coverage=("CONFLICT" if "same_slot_conflicting_binary" in reasons or
              "websocket_notification_conflict" in reasons
              else "PARTIAL" if valid else "UNKNOWN")
    return BaselineAudit(
        baseline_status=snapshot.status,baseline_slot=snapshot.slot,
        baseline_request_sha256=sha256(request_raw).hexdigest(),
        baseline_response_sha256=sha256(response_raw).hexdigest(),
        requested_at=requested_at.astimezone(timezone.utc).isoformat(),
        available_at=available_at.astimezone(timezone.utc).isoformat(),
        account_observations=tuple(rows),coverage=coverage,
        reasons=tuple(sorted(reasons)),
        baseline_validated_as_snapshot=valid)
