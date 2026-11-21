"""CM39A: prospective paper gate connected to real synthetic-capital accounts.

The existing CM33/CM34 engine persists synthetic runs. This preflight is
intentionally read-only and cannot create a run, submit a trade or inject ticks.
"""
from __future__ import annotations
from datetime import datetime,timezone
from smart_money_radar.services.market_trust_gate import prospective_preflight
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator
from smart_money_radar.storage.event_store import SQLiteEventStore

def plan_prospective_paper(store,*,account_id,radar,as_of,source_assessment,radar_qualification,
                           audited_request_id=None):
    if not isinstance(store,SQLiteEventStore) or not isinstance(account_id,str) or not account_id:
        raise ValueError("valid existing synthetic account required")
    if not isinstance(as_of,datetime) or as_of.utcoffset() is None or as_of>datetime.now(timezone.utc):
        raise ValueError("future or naive decision cutoff")
    if not isinstance(radar_qualification,dict) or radar_qualification.get("radar")!=radar:
        raise ValueError("radar qualification mismatch")
    gate=prospective_preflight(radar=radar,assessment=source_assessment)
    account=SyntheticCapitalCoordinator(store).snapshot(account_id)
    if radar not in account["allowed_radars"]:
        raise ValueError("independent radar budget scope mismatch")
    reasons=set(gate["reasons"])
    receipt=None
    if audited_request_id is not None:
        from smart_money_radar.services.cm38i_decision_audit import audit_blocked_entry
        receipt=audit_blocked_entry(store,audited_request_id)
        if receipt is None:
            raise ValueError("audited prospective entry request missing")
        if receipt["radar"]!=radar or receipt["account_id"]!=account_id:
            raise ValueError("audited opportunity/account/radar scope mismatch")
        if receipt["status"]!="BLOCKED" or receipt["virtual_ledger_mutated"]:
            raise ValueError("unauthorized audit state")
        reasons.add("persisted_opportunity_entry_remains_blocked")
    from smart_money_radar.services.cm38j_metric_provenance import qualify_metric_set
    receipts=radar_qualification.get("economic_receipts")
    metric_audit=None
    if receipts is not None:
        if not isinstance(receipts,(list,tuple)):
            raise ValueError("economic receipts must be a sequence")
        metric_audit=qualify_metric_set(radar=radar,metrics=list(receipts))
        if not metric_audit["complete_economic_evidence"]:
            reasons.add("cm38j_economic_evidence_incomplete")
        # Completeness is not a provider attestation or prospective approval.
        reasons.add("cm38j_receipts_information_only")
    else:
        reasons.add("cm38j_economic_receipts_missing")
    if not radar_qualification.get("qualified",False):
        reasons.add("radar_economic_qualification_missing")
    if account["capital_available"]=="0":
        reasons.add("synthetic_cash_unavailable")
    if account["strategy_budgets"] is None:
        reasons.add("explicit_strategy_budget_missing")
    return {"radar":radar,"account_id":account_id,"as_of":as_of.astimezone(timezone.utc).isoformat(),
            "status":"BLOCKED","prospective_authorized":False,
            "real_execution_authorized":False,
            "eligible_ticks":0,"entry_count":0,"exit_count":0,
            "ledger_mutated":False,
            "economic_metric_audit":metric_audit,
            "audited_attempt_id":receipt["attempt_id"] if receipt is not None else None,
            "original_rpc_evidence_id":receipt["evidence_id"] if receipt is not None else None,
            "reserved_amount":account["capital_reserved"],
            "equity":account["equity"],
            "reasons":tuple(sorted(reasons))}
