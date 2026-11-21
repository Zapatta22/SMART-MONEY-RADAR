"""CM39A: prospective paper gate connected to real synthetic-capital accounts.

The existing CM33/CM34 engine persists synthetic runs. This preflight is
intentionally read-only and cannot create a run, submit a trade or inject ticks.
"""
from __future__ import annotations
from datetime import datetime,timezone
from smart_money_radar.services.market_trust_gate import prospective_preflight
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator
from smart_money_radar.storage.event_store import SQLiteEventStore

def plan_prospective_paper(store,*,account_id,radar,as_of,source_assessment,radar_qualification):
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
            "reserved_amount":account["capital_reserved"],
            "equity":account["equity"],
            "reasons":tuple(sorted(reasons))}
