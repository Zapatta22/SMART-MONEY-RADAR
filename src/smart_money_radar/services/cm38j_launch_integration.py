"""CM38J adapters over the existing immutable market/volume/CPMM estimates.

No RPC, prices fetched, orders, or prospective paper ticks. Caller-supplied
snapshots are checked by the existing analyzers. These adapters never upgrade
a model estimate or a locally hashed observation to independent attestation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json

from smart_money_radar.domain.cpmm_reserve_snapshot import (
    validate_snapshot, estimate_from_snapshot,
)
from smart_money_radar.services.market_safety_liquidity import (
    assess_token_liquidity,
)
from smart_money_radar.services.market_volume_audit import audit_swap_volume
from smart_money_radar.services.cm38j_metric_provenance import (
    describe_metric, qualify_metric_set,
)

def _missing(*, name, at, start, source=None, ids=(), reason, strategy=None,
             pool=None, unit=None, method=None, kind="UNAVAILABLE"):
    return describe_metric(
        name=name, value=None, start=start, end=at,
        available_at=at, decision_at=at,
        source_id=source, evidence_ids=tuple(ids), quality="UNKNOWN",
        unavailable_reason=reason, radar="launch", strategy=strategy,
        pool=pool, unit=unit, method=method, kind=kind,
    )

def launch_metric_receipts(*, token_mint: str, pool: str, quote_mint: str,
                           at: datetime, strategy: str,
                           safety=None, liquidity=None, swaps=(),
                           min_liquidity_quote=Decimal("100"),
                           max_concentration_fraction=Decimal("0.4"),
                           volume_window=timedelta(minutes=5),
                           amount_in: Decimal | None = None, rpc_store=None,
                           cpmm_history=None, capture_id=None,
                           original_transaction_raw=None, original_manifest=None):
    """Reconcile one pool and a bounded interval, never other-pool quotes.

    The safety/volume contracts validate RAW hashes and time. A model impact
    may be reported separately as an estimate, never as observed execution.
    """
    if strategy not in ("immediate", "confirmed"):
        raise ValueError("Launch strategy required")
    if not isinstance(at, datetime) or at.utcoffset() is None:
        raise ValueError("aware cutoff required")
    if amount_in is not None and (not isinstance(amount_in, Decimal)
                                or not amount_in.is_finite() or amount_in <= 0):
        raise ValueError("positive finite estimate amount required")
    swaps = tuple(swaps)
    if liquidity is not None and liquidity.quote_mint != quote_mint:
        raise ValueError("liquidity quote mint mismatch")
    safety_audit = assess_token_liquidity(
        token=safety, liquidity=liquidity, token_mint=token_mint,
        pool=pool, as_of=at, min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction,
    )
    volume_audit = audit_swap_volume(
        tuple(swaps), pool=pool, token_mint=token_mint,
        quote_mint=quote_mint, as_of=at, window=volume_window,
    )
    if len(set(safety_audit.evidence_ids + volume_audit.evidence_ids)) != (
            len(safety_audit.evidence_ids) + len(volume_audit.evidence_ids)):
        raise ValueError("cross-engine duplicate evidence")
    start = at - volume_window
    if start > at:
        raise ValueError("invalid window")
    reasons = {
        "liquidity": "independent_liquidity_attestation_missing",
        "interval_volume": "independent_volume_attestation_missing",
        "depth": "authenticated_depth_unavailable",
        "market_impact": "observed_execution_impact_unavailable",
        "entry_cost": "observed_entry_cost_unavailable",
        "exit_cost": "observed_exit_cost_unavailable",
        "holder_concentration": "holder_independence_unverified",
        "token_authorities": "token_authority_attestation_missing",
        "manipulation_risk": "market_manipulation_assessment_incomplete",
    }
    metrics = [_missing(name=k, at=at, start=start, strategy=strategy,
                        pool=pool, unit=quote_mint, reason=v)
               for k, v in reasons.items()]
    # An economic observation can be displayed with its original audit result,
    # but the CM38J canonical metric remains UNKNOWN until independent proof.
    reserve = None
    estimate = None
    if liquidity is not None:
        reserve = validate_snapshot(liquidity.reserve_snapshot,
                                    liquidity.verified_raw_reserves)
        if reserve.pool != pool or reserve.available_at != liquidity.envelope.available_at.isoformat():
            raise ValueError("reserve snapshot scope/timestamp mismatch")
        if amount_in is not None:
            estimate = estimate_from_snapshot(reserve, amount_in)
            if estimate.is_observed_quote or estimate.pool != pool:
                raise ValueError("model estimate cannot be observed quote")
    # Local hashes prove byte integrity only, not independent RPC authenticity.
    links = []
    for kind, item in (("token_safety", safety), ("reserves", liquidity)):
        if item is not None:
            env = item.envelope
            links.append({"kind": kind, "evidence_id": env.evidence_id,
                          "source_id": env.source_id, "raw_sha256": env.integrity_sha256,
                          "slot": env.slot, "observed_at": env.observed_at.isoformat(),
                          "available_at": env.available_at.isoformat(),
                          "commitment": env.commitment})
    for swap in swaps:
        if start <= swap.occurred_at <= at:
            links.append({"kind": "swap", "evidence_id": swap.evidence_id,
                          "source_id": swap.source_id, "raw_sha256": swap.raw_sha256,
                          "signature": swap.signature, "side": swap.side,
                          "slot": swap.slot, "observed_at": swap.occurred_at.isoformat(),
                          "available_at": swap.available_at.isoformat(),
                          "commitment": swap.commitment})
    economic = {
        "radar": "launch", "strategy": strategy, "pool": pool,
        "token_mint": token_mint, "quote_mint": quote_mint,
        "window_start": start.isoformat(), "cutoff": at.isoformat(),
        "status": "NOT_COMPUTABLE", "quality": "UNKNOWN",
        "reserve_quote": str(safety_audit.liquidity_quote) if safety_audit.liquidity_quote is not None else None,
        "volume_quote": str(volume_audit.quote_volume) if volume_audit.quote_volume is not None and volume_audit.quality != "CONFLICTED" else None,
        "observation_kind": "LOCAL_UNATTESTED",
        "estimated_impact_fraction": str(estimate.price_impact_fraction) if estimate else None,
        "impact_kind": "MODEL_ESTIMATE" if estimate else "UNAVAILABLE",
        "safety_blocks": list(safety_audit.mandatory_blocks),
        "risk_flags": list(volume_audit.risk_flags),
        "reasons": sorted(set(safety_audit.reasons + volume_audit.reasons)),
        "evidence": sorted(links, key=lambda link: (link["kind"], link["evidence_id"])),
        "operational_authorized": False,
        "prospective_paper_authorized": False,
    }
    # Resolve transaction references against original persisted RPC bytes.
    # Account/reserve snapshots require a separate account evidence contract.
    economic["rpc_archive"] = _resolve_launch_rpc(rpc_store, economic["evidence"], at)
    economic["account_archive"] = _resolve_launch_accounts(
        cpmm_history, capture_id, original_transaction_raw, original_manifest,
        pool, token_mint, quote_mint, at)
    if economic["account_archive"]["status"] == "CONFLICTED":
        economic["safety_blocks"] = sorted(set(economic["safety_blocks"] + ["cpmm_account_archive_conflict"]))
    economic["sha256"] = sha256(json.dumps(economic, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        "economic_qualification": economic,
        "radar": "launch", "strategy": strategy, "pool": pool,
        "cutoff": at.isoformat(), "metrics": metrics,
        "metric_audit": qualify_metric_set(radar="launch", metrics=metrics),
        "observed_reserve_quote": str(safety_audit.liquidity_quote)
          if safety_audit.liquidity_quote is not None else None,
        "observed_reserve_quality": safety_audit.token_safety,
        "observed_volume_quote": str(volume_audit.quote_volume)
          if volume_audit.quote_volume is not None else None,
        "observed_volume_quality": volume_audit.quality,
        "reserve_evidence_ids": tuple(safety_audit.evidence_ids),
        "volume_evidence_ids": tuple(volume_audit.evidence_ids),
        "volume_risk_flags": tuple(volume_audit.risk_flags),
        "safety_blocks": tuple(economic["safety_blocks"]),
        "estimated_output": str(estimate.estimated_output) if estimate else None,
        "estimated_impact_fraction": str(estimate.price_impact_fraction)
          if estimate else None,
        "estimate_kind": "MODEL_ESTIMATE_NOT_OBSERVED" if estimate else None,
        "qualified": False,
        "modes": {"immediate": "BLOCKED", "confirmed": "BLOCKED"},
        "operational_authorized": False,
        "prospective_paper_authorized": False,
    }


def _resolve_launch_rpc(store, links, cutoff):
    """Read-only local archive linkage. Never attests economic amount or finality."""
    from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
    result = []
    if store is None:
        return {"status": "UNKNOWN", "links": result}
    journal = RpcObservationJournal(store)
    with store._connection_scope() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38_rpc_observations'").fetchone()
        for link in links:
            if link["kind"] != "swap":
                continue
            row = conn.execute(
                "SELECT radar,signature,available_at,metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?",
                (link["evidence_id"],)).fetchone() if exists else None
            status = "UNKNOWN"
            if row is not None:
                try:
                    item = journal._read(link["evidence_id"], row[3:])
                    meta = item["metadata"]
                    expected = ("launch", link["signature"], link["source_id"],
                                link["raw_sha256"], link["slot"], "finalized")
                    actual = (meta["radar"], meta["signature"], meta["source_id"],
                              meta["raw_sha256"], meta["slot"], meta["commitment_requested"])
                    if (actual != expected or link["commitment"] != "finalized"
                            or tuple(row[:3]) != (meta["radar"], meta["signature"], meta["available_at"])
                            or item["evidence"].available_at > cutoff
                            or item["evidence"].available_at != datetime.fromisoformat(link["available_at"])):
                        raise ValueError("RPC scope or cutoff conflict")
                    status = "LOCAL_BYTES_LINKED"
                except (ValueError, TypeError, KeyError, AttributeError):
                    status = "CONFLICTED"
            result.append({"evidence_id": link["evidence_id"], "status": status})
    return {"status": "CONFLICTED" if any(x["status"] == "CONFLICTED" for x in result) else "UNKNOWN",
            "links": result}


def _resolve_launch_accounts(history, capture_id, original_raw, original_manifest,
                             pool, token_mint, quote_mint, cutoff):
    """Expose decoded raw reserves only as local point-in-time observations."""
    result = {"status": "UNKNOWN", "independently_authenticated": False,
              "historical_pre_swap_proven": False, "operational_authorized": False}
    if history is None:
        return result
    try:
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
        if capture_id is None:
            if original_raw is None or original_manifest is None:
                return result
            capture = history.reconstruct_latest_for_pool(
                pool=pool, cutoff=cutoff, original_transaction_raw=original_raw,
                original_manifest=original_manifest)
        else:
            capture = history.reconstruct_capture(
                capture_id, original_transaction_raw=original_raw,
                original_manifest=original_manifest, cutoff=cutoff)
        if capture is None:
            return result
        obs = capture.observation
        matches = [x.accounts for x in decode_raydium_cpmm_swaps(json.loads(original_raw))
                   if x.accounts.pool_state == pool]
        if (obs.pool != pool or len(matches) != 1 or token_mint == quote_mint
                or {matches[0].input_token_mint, matches[0].output_token_mint}
                   != {token_mint, quote_mint}):
            raise ValueError("account scope conflict")
        input_is_quote = matches[0].input_token_mint == quote_mint
        result.update(status="LOCAL_PROSPECTIVE_BYTES_LINKED",
                      capture_id=capture.capture_id, slot=obs.slot,
                      source_id=obs.source_id, available_at=obs.available_at.isoformat(),
                      request_sha256=obs.request_sha256, response_sha256=obs.response_sha256,
                      account_sha256=list(obs.account_sha256),
                      quote_reserve_raw=str(obs.effective_input_raw if input_is_quote else obs.effective_output_raw),
                      token_reserve_raw=str(obs.effective_output_raw if input_is_quote else obs.effective_input_raw),
                      trade_fee_rate=obs.declared_trade_fee_rate,
                      creator_fee_rate=obs.declared_creator_fee_rate)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        result["status"] = "CONFLICTED"
    return result
