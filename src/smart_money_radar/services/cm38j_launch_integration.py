"""CM38J adapters over the existing immutable market/volume/CPMM estimates.

No RPC, prices fetched, orders, or prospective paper ticks. Caller-supplied
snapshots are checked by the existing analyzers. These adapters never upgrade
a model estimate or a locally hashed observation to independent attestation.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
from hashlib import sha256
import json

from smart_money_radar.domain.cpmm_binary_state import decode_amm_config, decode_pool_state
from smart_money_radar.domain.cpmm_integer_estimator import (
    CPMMFeeRates, FEE_RATE_DENOMINATOR,
    estimate_exact_input as estimate_integer_exact_input,
    estimate_exact_output as estimate_integer_exact_output,
)
from smart_money_radar.domain.cpmm_reserve_estimator import estimate_exact_input
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
from smart_money_radar.services.launch_cpmm_historical_reconciliation import (
    reconcile_launch_historical_swap,
)

_MAX_RESERVE_AGE = timedelta(minutes=5)
CPMM_LOCAL_LIQUIDITY_BLOCK = "cpmm_local_quote_reserve_below_minimum"

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
                           original_transaction_raw=None, original_manifest=None,
                           sell_amount_in: Decimal | None = None,
                           buy_amount_out: Decimal | None = None,
                           sell_amount_out: Decimal | None = None):
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
    if sell_amount_in is not None and (not isinstance(sell_amount_in, Decimal)
                                      or not sell_amount_in.is_finite() or sell_amount_in <= 0):
        raise ValueError("positive finite sell estimate amount required")
    for amount in (buy_amount_out, sell_amount_out):
        if amount is not None and (not isinstance(amount, Decimal)
                                   or not amount.is_finite() or amount <= 0):
            raise ValueError("positive finite exact output amount required")
    swaps = tuple(swaps)
    if liquidity is not None and liquidity.quote_mint != quote_mint:
        raise ValueError("liquidity quote mint mismatch")
    safety_audit = assess_token_liquidity(
        token=safety, liquidity=liquidity, token_mint=token_mint,
        pool=pool, as_of=at, min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction,
        max_age=_MAX_RESERVE_AGE,
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
            try:
                estimate = estimate_from_snapshot(reserve, amount_in)
            except DecimalException:
                estimate = None
            if estimate is not None and (estimate.is_observed_quote or estimate.pool != pool):
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
    integer_scenarios = (
        ("buy_integer_model", "EXACT_INPUT", quote_mint, token_mint, amount_in),
        ("sell_integer_model", "EXACT_INPUT", token_mint, quote_mint, sell_amount_in),
        ("buy_integer_exact_output_model", "EXACT_OUTPUT", quote_mint, token_mint, buy_amount_out),
        ("sell_integer_exact_output_model", "EXACT_OUTPUT", token_mint, quote_mint, sell_amount_out),
    )
    economic["account_archive"] = _resolve_launch_accounts(
        cpmm_history, capture_id, original_transaction_raw, original_manifest,
        pool, token_mint, quote_mint, at,
        tuple(scenario for scenario in integer_scenarios if scenario[-1] is not None),
        declared_reserve=reserve, min_liquidity_quote=min_liquidity_quote,
    )
    archive = economic["account_archive"]
    liquidity_check = archive.get("liquidity_check", {})
    reserve_conflict = liquidity_check.get("reconciliation") == "SAME_SLOT_CONFLICT"
    if liquidity_check.get("status") == "LOCAL_BELOW_MINIMUM":
        economic["safety_blocks"].append(CPMM_LOCAL_LIQUIDITY_BLOCK)
    if reserve_conflict:
        estimate = None
        economic.update(reserve_quote=None, estimated_impact_fraction=None, impact_kind="UNAVAILABLE")
    if (archive["status"] == "LOCAL_PROSPECTIVE_BYTES_LINKED"
            and (amount_in is not None or sell_amount_in is not None)):
        # Generic trade-fee-only scenario; creator fee allocation/rounding
        # is not established by this model. Never present as total cost.
        q = Decimal(archive["quote_reserve_normalized"])
        t = Decimal(archive["token_reserve_normalized"])
        fee = Decimal(archive["trade_fee_rate"]) / Decimal(100)
        for key, amount, x, y, unit_in, unit_out in (
            ("buy_model", amount_in, q, t, "quote", "token"),
            ("sell_model", sell_amount_in, t, q, "token", "quote"),
        ):
            if amount is None or x <= 0 or y <= 0:
                continue
            try:
                model = estimate_exact_input(pool=pool, slot=archive["slot"],
                    reserve_in=x, reserve_out=y, amount_in=amount, fee_bps=fee)
            except (DecimalException, ValueError):
                continue
            archive[key] = {
                f"input_{unit_in}": str(amount),
                f"estimated_output_{unit_out}": str(model.estimated_output),
                "fee_inclusive_impact_fraction": str(model.price_impact_fraction),
                "trade_fee_bps": str(fee), "creator_fee_included": False,
                "kind": "GENERIC_TRADE_FEE_ONLY_NOT_EXECUTABLE",
                "operational_authorized": False}
    if archive["status"] == "CONFLICTED":
        economic["safety_blocks"].append("cpmm_account_archive_conflict")
    economic["safety_blocks"].sort()
    economic["sha256"] = sha256(json.dumps(economic, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        "economic_qualification": economic,
        "radar": "launch", "strategy": strategy, "pool": pool,
        "cutoff": at.isoformat(), "metrics": metrics,
        "metric_audit": qualify_metric_set(radar="launch", metrics=metrics),
        "observed_reserve_quote": economic["reserve_quote"],
        "observed_reserve_quality": "CONFLICTED" if reserve_conflict else safety_audit.token_safety,
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
                             pool, token_mint, quote_mint, cutoff, integer_scenarios,
                             *, declared_reserve, min_liquidity_quote):
    """Expose decoded raw reserves only as local point-in-time observations."""
    result = {"status": "UNKNOWN", "independently_authenticated": False,
              "historical_pre_swap_proven": False, "operational_authorized": False}
    if history is None:
        return result
    try:
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
        if original_raw is None and original_manifest is None:
            if capture_id is None:
                ids = history.candidate_capture_ids(pool=pool, cutoff=cutoff, limit=1)
                if not ids:
                    return result
                capture_id = ids[0]
            original = history.get_original(capture_id)
            if original is None:
                return result
            original_raw, original_manifest = original
        elif original_raw is None or original_manifest is None:
            raise ValueError("incomplete original evidence")
        if capture_id is None:
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
        matches = [x for x in decode_raydium_cpmm_swaps(json.loads(original_raw))
                   if x.accounts.pool_state == pool]
        if obs.pool != pool or len(matches) != 1 or token_mint == quote_mint:
            raise ValueError("account scope conflict")
        swap = matches[0]
        if {swap.accounts.input_token_mint, swap.accounts.output_token_mint} != {token_mint, quote_mint}:
            raise ValueError("account mint scope conflict")
        input_is_quote = swap.accounts.input_token_mint == quote_mint
        result.update(status="LOCAL_PROSPECTIVE_BYTES_LINKED",
                      capture_id=capture.capture_id, slot=obs.slot,
                      source_id=obs.source_id, available_at=obs.available_at.isoformat(),
                      request_sha256=obs.request_sha256, response_sha256=obs.response_sha256,
                      account_sha256=list(obs.account_sha256),
                      quote_reserve_raw=str(obs.effective_input_raw if input_is_quote else obs.effective_output_raw),
                      token_reserve_raw=str(obs.effective_output_raw if input_is_quote else obs.effective_input_raw),
                      trade_fee_rate=obs.declared_trade_fee_rate,
                      creator_fee_rate=obs.declared_creator_fee_rate)
        # Decimals declared by the validated pool account, not independent mint proof.
        accounts = json.loads(capture.response_raw)["result"]["value"]
        state = decode_pool_state(base64.b64decode(accounts[0]["data"][0], validate=True))
        decimals = {state.token_0_mint: state.mint_0_decimals,
                    state.token_1_mint: state.mint_1_decimals}
        if set(decimals) != {token_mint, quote_mint}:
            raise ValueError("pool decimals scope conflict")
        with localcontext() as ctx:
            ctx.prec = 50
            token = Decimal(result["token_reserve_raw"]).scaleb(-decimals[token_mint])
            quote = Decimal(result["quote_reserve_raw"]).scaleb(-decimals[quote_mint])
            result.update(token_decimals=decimals[token_mint], quote_decimals=decimals[quote_mint],
                          decimals_provenance="POOL_DECLARED_NOT_MINT_ATTESTED",
                          token_reserve_normalized=str(token), quote_reserve_normalized=str(quote),
                          estimated_spot_quote_per_token=str(quote/token) if token>0 and quote>0 else None,
                          estimated_pool_value_quote=str(quote*2) if token>0 and quote>0 else None,
                          normalized_values_status="LOCAL_ESTIMATE_NOT_EXECUTABLE")
        check = _check_archive_liquidity(
            declared_reserve=declared_reserve, observation=obs, cutoff=cutoff,
            min_quote=min_liquidity_quote, quote=quote, token=token,
            quote_decimals=decimals[quote_mint], token_decimals=decimals[token_mint],
        )
        result["liquidity_check"] = check
        if check["reconciliation"] == "SAME_SLOT_CONFLICT":
            result["status"] = "CONFLICTED"
            return result
        result["historical_swap_reconciliation"] = reconcile_launch_historical_swap(
            transaction_raw=original_raw, manifest=original_manifest, cutoff=cutoff,
            swap=swap, quote_mint=quote_mint, pool_decimals=decimals,
        )
        if integer_scenarios:
            config = decode_amm_config(base64.b64decode(accounts[1]["data"][0], validate=True))
            reserves = {
                token_mint: int(result["token_reserve_raw"]),
                quote_mint: int(result["quote_reserve_raw"]),
            }
            for key, mode, input_mint, output_mint, amount in integer_scenarios:
                result[key] = _estimate_integer_scenario(
                    mode, input_mint, output_mint, amount, decimals, reserves, state, config,
                )

    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        result["status"] = "CONFLICTED"
    return result


def _check_archive_liquidity(*, declared_reserve, observation, cutoff, min_quote,
                             quote, token, quote_decimals, token_decimals):
    reconciliation = "DECLARATION_MISSING"
    mismatches = []
    if declared_reserve is not None:
        if declared_reserve.slot != observation.slot:
            reconciliation = "DIFFERENT_SLOT"
        else:
            # Same-slot comparisons detect disagreement in the declared state.
            # They cannot establish intra-slot ordering or independent attestation.
            mismatches = [name for name, archived, declared in (
                ("quote_reserve", quote, declared_reserve.reserve_in),
                ("token_reserve", token, declared_reserve.reserve_out),
                ("quote_decimals", quote_decimals, declared_reserve.input_decimals),
                ("token_decimals", token_decimals, declared_reserve.output_decimals),
            ) if archived != declared]
            reconciliation = "SAME_SLOT_CONFLICT" if mismatches else "SAME_SLOT_MATCH"

    if mismatches:
        status = "CONFLICTED"
    elif cutoff - observation.observed_at > _MAX_RESERVE_AGE:
        status = "STALE"
    elif quote < min_quote:
        status = "LOCAL_BELOW_MINIMUM"
    else:
        status = "LOCAL_MEETS_MINIMUM"
    return {
        "status": status,
        "reconciliation": reconciliation,
        "mismatches": mismatches,
        "observed_at": observation.observed_at.isoformat(),
        "declared_slot": declared_reserve.slot if declared_reserve is not None else None,
        "minimum_quote_reserve": str(min_quote),
        "independently_authenticated": False,
    }


def _raw_amount(amount: Decimal, decimals: int) -> int:
    if not 0 <= amount.adjusted() + decimals <= 19:
        raise ValueError("scenario amount must fit in positive raw token units")
    sign, digits, exponent = amount.as_tuple()
    scaled = Decimal((sign, digits, exponent + decimals))
    integral = int(scaled)
    if integral != scaled or integral > (1 << 64) - 1:
        raise ValueError("scenario amount must be exactly representable as raw u64")
    return integral


def _estimate_integer_scenario(mode, input_mint, output_mint, amount, decimals,
                               reserves, state, config):
    result = {
        "status": "UNAVAILABLE",
        "kind": "RAYDIUM_CPMM_INTEGER_NOT_EXECUTABLE",
        "mode": mode,
        "input_mint": input_mint,
        "output_mint": output_mint,
        "operational_authorized": False,
    }
    if state.creator_fee_on is None or state.enable_creator_fee is None:
        result["reason"] = "creator_fee_policy_unavailable"
        return result
    amount_mint = input_mint if mode == "EXACT_INPUT" else output_mint
    try:
        amount_raw = _raw_amount(amount, decimals[amount_mint])
    except ValueError:
        result["reason"] = "scenario_amount_not_positive_raw_u64"
        return result

    creator_fee_on_input = (
        state.creator_fee_on == 0
        or state.creator_fee_on == 1 and input_mint == state.token_0_mint
        or state.creator_fee_on == 2 and input_mint == state.token_1_mint
    )
    try:
        fees = CPMMFeeRates(
            trade_fee_rate=config.trade_fee_rate,
            creator_fee_rate=config.creator_fee_rate if state.enable_creator_fee else 0,
            protocol_fee_rate=config.protocol_fee_rate,
            fund_fee_rate=config.fund_fee_rate,
            creator_fee_on_input=creator_fee_on_input,
        )
    except ValueError:
        result["reason"] = "invalid_cpmm_fee_rates"
        return result
    try:
        if mode == "EXACT_INPUT":
            estimate = estimate_integer_exact_input(
                reserve_in=reserves[input_mint], reserve_out=reserves[output_mint],
                amount_in=amount_raw, fees=fees,
            )
        else:
            estimate = estimate_integer_exact_output(
                reserve_in=reserves[input_mint], reserve_out=reserves[output_mint],
                amount_out=amount_raw, fees=fees,
            )
    except ValueError:
        result["reason"] = "scenario_outside_cpmm_curve_bounds"
        return result
    result.update(
        status="MODEL_ESTIMATE",
        fee_provenance="POOL_AND_AMM_CONFIG_LOCAL_BYTES",
        fee_rate_denominator=FEE_RATE_DENOMINATOR,
        trade_fee_rate=fees.trade_fee_rate,
        creator_fee_rate=fees.creator_fee_rate,
        protocol_fee_rate=fees.protocol_fee_rate,
        fund_fee_rate=fees.fund_fee_rate,
        creator_fee_enabled=state.enable_creator_fee,
        creator_fee_mode=state.creator_fee_on,
        creator_fee_on_input=estimate.creator_fee_on_input,
        input_amount_raw=str(estimate.input_amount),
        output_amount_raw=str(estimate.output_amount),
        trade_fee_raw=str(estimate.trade_fee),
        creator_fee_raw=str(estimate.creator_fee),
        protocol_fee_raw=str(estimate.protocol_fee),
        fund_fee_raw=str(estimate.fund_fee),
    )
    return result
