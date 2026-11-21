"""CM32: independent point-in-time decision reports over persisted radar events.

No prices, liquidity, identity, operational authority or market coverage are
invented. Existing consensus, market and risk policies remain authoritative.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

from smart_money_radar.domain.paper_entry_risk_policy import (
    EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk,
)
from smart_money_radar.services.market_safety_liquidity import (
    LiquiditySnapshot, TokenSafetySnapshot, assess_token_liquidity,
)
from smart_money_radar.services.market_volume_audit import SwapVolumeEvidence, audit_swap_volume
from smart_money_radar.services.market_opportunity_bridge import classify_with_market_evidence
from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
from smart_money_radar.services.wallet_consensus import WalletConsensusService
from smart_money_radar.services.wallet_signals import WalletSignalService
from smart_money_radar.services.sqlite_market_history import archived_volume_at
from smart_money_radar.storage.event_store import SQLiteEventStore

@dataclass(frozen=True)
class IntelligenceScope:
    token_mint: str
    quote_mint: str
    min_liquidity_quote: Decimal
    max_concentration_fraction: Decimal
    wallets: tuple[str, ...] = ()
    window: timedelta = timedelta(minutes=5)
    max_publication_delay: timedelta = timedelta(minutes=5)
    min_confidence: Decimal = Decimal("0.8")

@dataclass(frozen=True)
class MarketInputs:
    safety: TokenSafetySnapshot | None = None
    liquidity: LiquiditySnapshot | None = None
    swaps: tuple[SwapVolumeEvidence, ...] = ()

def _time(value):
    if isinstance(value,str):
        value=datetime.fromisoformat(value)
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware decision time required")
    return value.astimezone(timezone.utc)

def _id(parts):
    return sha256(json.dumps(parts,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def evaluate_archived_event(event: dict, *, store, as_of: datetime,
                            scope: IntelligenceScope | None = None,
                            market: MarketInputs | None = None,
                            risk_limits: EntryRiskLimits | None = None,
                            risk_snapshot: EntryRiskSnapshot | None = None) -> dict:
    """Evaluate only within the archived event's scope and availability cutoff.

    Market/risk arguments are explicit offline inputs, not trusted live proofs.
    A scored observation is never an entry or exit authorization.
    """
    point=_time(as_of)
    radar=event["radar"]
    if radar not in ("launch","smart_money") or event.get("operational_authorized") is not False:
        raise ValueError("invalid radar event")
    if not event.get("id") or not event.get("pool"):
        raise ValueError("event identity required")
    publication=_time(event["available_at"]) if event.get("available_at") else None
    reasons=set(event.get("reasons",()))
    verdict="UNKNOWN"
    direction=event.get("direction") if radar=="smart_money" else None
    evidence_ids=[event["source_reference"]] if event.get("source_reference") else []
    score=None
    consensus=None
    market_result=None
    volume_result=None
    archived_market=None
    qualified_consensus=None
    risk_reasons=[]
    risk_status="UNKNOWN"
    market=market or MarketInputs()
    if (risk_limits is None)!=(risk_snapshot is None):
        raise ValueError("risk limits and snapshot must be supplied together")
    if publication is None or publication>point:
        reasons.add("event_unavailable_at_cutoff")
        direction=None
        evidence_ids=[]
    elif event.get("evidence_quality")=="CONFLICTED":
        verdict="REJECTED"
        reasons.add("event_evidence_conflicted")
    elif scope is None:
        reasons.add("explicit_market_scope_missing")
    else:
        if (not scope.token_mint or not scope.quote_mint or scope.token_mint==scope.quote_mint):
            raise ValueError("distinct scoped mints required")
        if radar=="launch":
            if set(event.get("token_mints",()))!={scope.token_mint,scope.quote_mint}:
                raise ValueError("launch token/pool scope mismatch")
            if scope.wallets:
                raise ValueError("wallet consensus does not belong to Launch Radar")
            market_result=assess_token_liquidity(token=market.safety,liquidity=market.liquidity,
                token_mint=scope.token_mint,pool=event["pool"],as_of=point,
                min_liquidity_quote=scope.min_liquidity_quote,
                max_concentration_fraction=scope.max_concentration_fraction)
            volume_result=audit_swap_volume(market.swaps,pool=event["pool"],token_mint=scope.token_mint,
                quote_mint=scope.quote_mint,as_of=point,window=scope.window)
            reasons.update(market_result.reasons)
            reasons.update(volume_result.reasons)
            reasons.update(market_result.mandatory_blocks)
            reasons.update(volume_result.risk_flags)
            evidence_ids.extend(market_result.evidence_ids+volume_result.evidence_ids)
            if market_result.mandatory_blocks or volume_result.risk_flags:
                verdict="REJECTED"
            # A creation instruction is not a current tradable reserve or a quote.
            reasons.add("initialization_not_executable_price")
        else:
            if set((event.get("input_mint"),event.get("output_mint")))!={scope.token_mint,scope.quote_mint}:
                raise ValueError("smart money token/pool scope mismatch")
            if isinstance(store,SQLiteEventStore) and event.get("program"):
                from smart_money_radar.services.wallet_discovery import WalletDiscoveryPolicy,qualified_consensus_at
                qualified_consensus=qualified_consensus_at(store,as_of=point,
                    policy=WalletDiscoveryPolicy(quote_mints=(scope.quote_mint,),manual_wallets=scope.wallets),
                    program=event["program"],pool=event["pool"],base_mint=scope.token_mint,
                    quote_mint=scope.quote_mint,window=scope.window,
                    max_publication_delay=scope.max_publication_delay,min_confidence=scope.min_confidence)
                reasons.update(qualified_consensus["consensus"]["reasons"])
                reasons.add("manual_consensus_observational_only")
            if not event.get("program") or not scope.wallets:
                reasons.add("explicit_consensus_scope_missing")
            elif event.get("wallet_address") not in scope.wallets:
                reasons.add("event_wallet_not_in_scope")
            else:
                consensus=WalletConsensusService(WalletSignalService(store)).get_report(
                    wallets=scope.wallets,program=event["program"],pool=event["pool"],
                    base_mint=scope.token_mint,quote_mint=scope.quote_mint,as_of=point,
                    window=scope.window,max_publication_delay=scope.max_publication_delay,
                    min_confidence=scope.min_confidence)
                evidence_ids.extend("wallet-signature:"+s for m in consensus.members for s in m.signatures)
                reasons.update(consensus.reasons)
                if isinstance(store,SQLiteEventStore):
                    archived_market=archived_volume_at(store,wallets=scope.wallets,
                        program=event["program"],pool=event["pool"],token_mint=scope.token_mint,
                        quote_mint=scope.quote_mint,as_of=point,window=scope.window,
                        min_confidence=scope.min_confidence)
                    reasons.update(archived_market.volume.reasons)
                    if archived_market.excluded_receipts:
                        reasons.add("archived_market_receipts_excluded")
                base=OpportunityEvidence(scope.token_mint,"solana",event["pool"],point,
                    event["source_id"],"UNKNOWN","UNKNOWN","UNKNOWN",None,None,
                    False,False,None,None)
                audit=classify_with_market_evidence(base=base,consensus=consensus,
                    safety=market.safety,liquidity=market.liquidity,swaps=market.swaps,
                    quote_mint=scope.quote_mint,min_liquidity_quote=scope.min_liquidity_quote,
                    max_concentration_fraction=scope.max_concentration_fraction,volume_window=scope.window)
                score=audit.classification.score
                verdict=audit.classification.verdict if audit.classification.verdict in ("REJECTED","UNKNOWN") else "UNKNOWN"
                direction=consensus.direction
                market_result,volume_result=audit.safety,audit.volume
                reasons.update(audit.classification.reasons)
                reasons.update(audit.safety.reasons)
                reasons.update(audit.volume.reasons)
                evidence_ids.extend(audit.evidence_ids)
    # Caller credentials, declared provider flags and risk snapshots cannot
    # upgrade the archived event. Preserve actual rejection rules and force
    # unverified evidence through the original risk policy.
    if risk_snapshot is not None:
        bound=replace(risk_snapshot,evidence_verified=False,
            verified_liquidity_quote=Decimal(0))
        risk_reasons=list(evaluate_entry_risk(risk_limits,bound))
        risk_status="BLOCKED"
    else:
        risk_reasons=["risk_snapshot_missing"]
    reasons.update(risk_reasons)
    reasons.update(("independent_source_attestation_missing","execution_quote_unverified"))
    if event.get("evidence_quality")=="CONFLICTED":
        verdict="REJECTED"
    result={
        "event_id":event["id"],"radar":radar,"pool":event["pool"],
        "source_id":event["source_id"],"origin":event["origin"],
        "event_available_at":event.get("available_at"),"as_of":point.isoformat(),
        "evidence_ids":sorted(set(evidence_ids)),"raw_sha256":event.get("raw_sha256"),
        "direction":direction,"score":score,"confidence":"UNKNOWN","verdict":verdict,
        "coverage":"UNKNOWN","risk_status":risk_status,"risk_reasons":risk_reasons,
        "reasons":sorted(reasons),"consensus":asdict(consensus) if consensus else None,
        "market":asdict(market_result) if market_result else None,
        "volume":asdict(volume_result) if volume_result else None,
        "archived_market":asdict(archived_market) if archived_market else None,
        "qualified_consensus":qualified_consensus,
        "paper_modes":{"immediate":"BLOCKED","confirmed":"BLOCKED"},
        "operational_authorized":False,
    }
    # Stable decision identifier: includes as_of, policy output, scope and exact evidence.
    result["id"]="decision:"+_id([result,asdict(scope) if scope else None,
                                   asdict(risk_limits) if risk_limits else None,
                                   asdict(risk_snapshot) if risk_snapshot else None])
    return result

def read_intelligence_reports(store, events: dict, *, scopes: dict | None = None,
                              as_of: datetime | None = None) -> dict:
    """Read-only view; no inferred quote mint or wallet qualification.

    No configured scopes means explicit UNKNOWN decisions. Optional trusted
    server-side scopes are keyed by (radar, pool); dashboard clients cannot
    supply or modify risk policy. Each malformed event fails closed separately.
    """
    reports={"launch":[],"smart_money":[]}
    point=_time(as_of) if as_of is not None else None
    scopes=scopes or {}
    for radar in reports:
        seen=set()
        for event in events.get(radar,()):
            if event.get("radar")!=radar or event.get("id") in seen:
                continue
            if point is not None and event.get("available_at"):
                try:
                    if _time(event["available_at"])>point:
                        continue
                except ValueError:
                    pass
            seen.add(event.get("id"))
            try:
                # Default decision time is the first publication, not wall-clock now.
                decision_at=point or (_time(event["available_at"]) if event.get("available_at") else None)
                if decision_at is None:
                    continue
                report=evaluate_archived_event(event,store=store,as_of=decision_at,
                    scope=scopes.get((radar,event["pool"])))
            except (ValueError,TypeError,KeyError,ArithmeticError):
                report={"id":"decision:invalid:"+_id(event),"event_id":event.get("id"),
                    "radar":radar,"pool":event.get("pool"),"origin":event.get("origin"),
                    "source_id":event.get("source_id"),"event_available_at":event.get("available_at"),
                    "score":None,"confidence":"UNKNOWN","verdict":"REJECTED",
                    "risk_status":"BLOCKED","risk_reasons":["invalid_intelligence_input"],
                    "reasons":["invalid_intelligence_input"],"evidence_ids":[],
                    "paper_modes":{"immediate":"BLOCKED","confirmed":"BLOCKED"},
                    "operational_authorized":False}
            reports[radar].append(report)
    return reports
