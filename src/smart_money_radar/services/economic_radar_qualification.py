"""CM38E/F: audited information-only qualification using existing radar engines.

No parallel collector, decoder, market scorer or wallet consensus implementation.
RPC bytes and local links are not independent provider authentication. All
positive operational, trade and prospective execution claims fail closed.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from decimal import Decimal

from smart_money_radar.services.market_opportunity_bridge import classify_with_market_evidence
from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
from smart_money_radar.services.wallet_consensus import WalletConsensusReport
from smart_money_radar.services.wallet_discovery import WalletDiscoveryPolicy,discover_wallets
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.cm38j_metric_provenance import (
    describe_metric, qualify_metric_set, SMART_MONEY_INDICATORS,
)
from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts

def _cutoff(value):
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware cutoff required")
    utc=value.astimezone(timezone.utc)
    if utc>datetime.now(timezone.utc):
        raise ValueError("future decision is prohibited")
    return utc

def qualify_launch_at(store,*,signature,base:OpportunityEvidence,consensus:WalletConsensusReport,
                      safety=None,liquidity=None,swaps=(),quote_mint,
                      min_liquidity_quote=Decimal("100"),
                      max_concentration_fraction=Decimal("0.4")):
    """Reuse the existing safety, liquidity, volume and opportunity classifier.

    A source claim from the caller cannot upgrade an incomplete observation.
    Detailed risk findings and information-only score remain available.
    """
    if not isinstance(store,SQLiteEventStore) or not isinstance(base,OpportunityEvidence):
        raise TypeError("existing store and opportunity evidence required")
    point=_cutoff(base.as_of)
    if base.chain!="solana": raise ValueError("Solana required")
    rpc=RpcObservationJournal(store).assess(radar="launch",signature=signature,cutoff=point)
    safe_base=replace(base,source_status="CONFLICTED" if rpc["status"]=="CONFLICTED" or base.source_status=="CONFLICTED" else "UNKNOWN",
                      history_coverage="UNKNOWN",wallet_independence_verified=False,
                      liquidity_verified=False,volume_verified=False)
    # The legacy classifier requires these two independence contracts to
    # agree. Do not trust a caller's positive consensus claim without an
    # independently linked owner-identity attestation.
    safe_consensus=replace(consensus,independence_verified=False,
                           actionable=False,
                           reasons=tuple(sorted(set(consensus.reasons)|{"independence_not_attested"})))
    audit=classify_with_market_evidence(
        base=safe_base,consensus=safe_consensus,safety=safety,liquidity=liquidity,
        swaps=tuple(swaps),quote_mint=quote_mint,
        min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction)
    reasons=set(audit.classification.reasons)
    reasons.update(rpc["reasons"])
    reasons.add("independent_finalization_unverified")
    reasons.add("holder_ownership_independence_unknown")
    if safety is None: reasons.add("mint_freeze_token2022_safety_missing")
    if liquidity is None: reasons.add("liquidity_reserves_unverified")
    if not swaps: reasons.add("volume_economic_reconciliation_missing")
    receipt_bundle=launch_metric_receipts(token_mint=base.token_mint,
        pool=base.pool, quote_mint=quote_mint, at=point,
        strategy="immediate", safety=safety, liquidity=liquidity,
        swaps=tuple(swaps), min_liquidity_quote=min_liquidity_quote,
        max_concentration_fraction=max_concentration_fraction)
    return {"radar":"launch","signature":signature,"cutoff":point.isoformat(),
            "economic_receipts":receipt_bundle["metrics"],
            "economic_receipt_audit":receipt_bundle["metric_audit"],
            "estimated_impact_fraction":receipt_bundle["estimated_impact_fraction"],
            "pool":base.pool,"token_mint":base.token_mint,
            "classification":audit.classification,
            "safety":audit.safety,"volume":audit.volume,
            "original_market_evidence_ids":audit.evidence_ids,
            "linked_rpc_evidence_ids":tuple(rpc["evidence_ids"]),
            "source_trust":rpc["trust"],
            "reasons":tuple(sorted(reasons)),
            "modes":(("immediate","BLOCKED"),("confirmed","BLOCKED")),
            "qualified":False,"prospective_paper_authorized":False,
            "operational_authorized":False}

def qualify_smart_money_at(store,*,as_of,policy:WalletDiscoveryPolicy=WalletDiscoveryPolicy()):
    """Recheck each local economic operation against original RPC RAW links.

    No verified PnL, win-rate, profitability, correlation or owner independence
    is fabricated from directional swaps. Profile counts remain informational.
    """
    if not isinstance(store,SQLiteEventStore): raise TypeError("SQLiteEventStore required")
    point=_cutoff(as_of)
    discovery=discover_wallets(store,as_of=point,policy=policy)
    profiles=[]
    with store._connection_scope() as conn:
        conn.execute("BEGIN")
        has_links=bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38_economic_evidence_links'").fetchone())
        for original in discovery["profiles"]:
            profile=dict(original)
            linked=0;missing=0;conflicted=0;ids=[]
            for operation in original["evidence"]:
                if not has_links:
                    missing+=1;continue
                row=conn.execute(
                    """SELECT l.evidence_id,o.metadata,o.metadata_sha,o.raw
                       FROM cm38_economic_evidence_links l
                       JOIN cm38_rpc_observations o ON l.evidence_id=o.evidence_id
                       WHERE l.radar='smart_money' AND l.wallet_address=? AND l.signature=?
                         AND l.entity_type='swap_and_classification' AND l.entity_id=?""",
                    (original["wallet"],operation["signature"],operation["operation_id"])
                ).fetchone()
                if row is None:
                    missing+=1;continue
                eid,metadata,digest,raw=row
                try:
                    verified=RpcObservationJournal._read(eid,(metadata,digest,raw))
                    meta=verified["metadata"]
                    if (meta["signature"]!=operation["signature"] or
                            meta["radar"]!="smart_money" or
                            meta["commitment_requested"]!="confirmed" or
                            datetime.fromisoformat(meta["available_at"])>point or
                            datetime.fromisoformat(meta["available_at"])>datetime.fromisoformat(operation["available_at"])):
                        raise ValueError("economic link scope or lookahead conflict")
                except (ValueError,KeyError,TypeError,AttributeError):
                    conflicted+=1;continue
                linked+=1;ids.append(eid)
            reasons=set(original["reasons"])
            if missing:reasons.add("economic_rpc_link_missing")
            if conflicted:reasons.add("economic_rpc_link_corrupted")
            reasons.update(("realized_pnl_unverified","fees_and_costs_unverified",
                            "drawdown_unverified","wallet_owner_independence_unverified",
                            "historical_coverage_unknown"))
            economic_receipts=[describe_metric(name=name,value=None,
                start=point-timedelta(days=30),end=point,available_at=point,
                decision_at=point,quality="UNKNOWN",
                unavailable_reason="economic_cost_basis_or_attestation_missing",
                radar="smart_money",method="CM35_DISCOVERY_WITH_CM38_RAW_LINK_AUDIT")
                for name in SMART_MONEY_INDICATORS]
            profile.update({"economic_receipts":economic_receipts,
                            "economic_receipt_audit":qualify_metric_set(
                                radar="smart_money",metrics=economic_receipts),
                            "rpc_linked_operations":linked,
                            "rpc_unlinked_operations":missing,
                            "rpc_conflicted_operations":conflicted,
                            "original_rpc_evidence_ids":tuple(sorted(set(ids))),
                            "realized_pnl":None,"win_rate":None,"drawdown":None,
                            "fees":None,"consistency":None,
                            "economic_status":"CONFLICTED" if conflicted else "UNKNOWN",
                            "qualified":False,"eligible_for_consensus":False,
                            "operational_authorized":False,"reasons":sorted(reasons)})
            profiles.append(profile)
    return {"radar":"smart_money","as_of":point.isoformat(),
            "origin":"CM35_DISCOVERY_WITH_CM38_RAW_LINK_AUDIT",
            "profiles":profiles,"qualified_wallets":[],
            "qualified_count":0,"consensus":"INSUFFICIENT",
            "wallet_independence":"UNKNOWN","economic_metrics":"UNKNOWN",
            "historical_coverage":"UNKNOWN",
            "operational_authorized":False,
            "prospective_paper_authorized":False,
            "snapshot_id":discovery["snapshot_id"]}
