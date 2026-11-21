"""CM37G: authenticated synthetic capital commands, no real capital movement."""
from decimal import Decimal
from dataclasses import fields
import re
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator,CapitalLimits,_load,_snapshot
from smart_money_radar.services.synthetic_paper_ledger import _verify_record,_encode,_hash
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits
from smart_money_radar.domain.paper_replay import PaperConfig

def _d(value):
    if not isinstance(value,str) or not re.fullmatch(r"[0-9]{1,18}(\.[0-9]{1,12})?",value):
        raise ValueError("decimal string required")
    return Decimal(value)

def _fields(obj,cls):
    if not isinstance(obj,dict) or set(obj)!={f.name for f in fields(cls)}:
        raise ValueError("invalid policy fields")
    return cls(**{k:_d(v) for k,v in obj.items()})

def apply_capital_command(store,action,policy,event_id,at):
    """Server-side validation before reuse of the existing capital journal."""
    if not isinstance(policy,dict): raise ValueError("missing policy")
    account=policy.get("account_id")
    if not isinstance(account,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",account):
        raise ValueError("invalid account")
    limits=_fields(policy.get("limits"),CapitalLimits)
    coordinator=SyntheticCapitalCoordinator(store)
    if action=="CAPITAL_CREATE":
        if set(policy)!={"account_id","initial","currency","radars","limits"}:
            raise ValueError("invalid account creation fields")
        radars=policy["radars"]
        if not isinstance(radars,list) or any(x not in ("launch","smart_money") for x in radars):
            raise ValueError("invalid radar scope")
        if policy["currency"]!="USDC": raise ValueError("evaluation currency must be USDC")
        # A creation receipt and its immutable account metadata are committed
        # together. The new account principal is synthetic, never a transfer.
        coordinator.create(account_id=account,initial=_d(policy["initial"]),currency="USDC",
            radars=tuple(radars),limits=limits,admin_event_id=event_id,admin_at=at)
        return coordinator.snapshot(account)
    if action!="CAPITAL_POLICY" or set(policy) not in ({"account_id","limits","config","entry_risk"},{"account_id","limits","config","entry_risk","budgets"}):
        raise ValueError("invalid policy update")
    cfg=policy["config"]
    if not isinstance(cfg,dict) or set(cfg)!={"initial_cash","max_entry_cash","max_exposure","fee_bps","slippage_bps","stop_loss","take_profit","max_entry_deviation_bps","allow_partial_fills"}:
        raise ValueError("invalid run configuration")
    if type(cfg["allow_partial_fills"]) is not bool: raise ValueError("boolean required")
    kwargs={k:_d(v) for k,v in cfg.items() if k not in ("allow_partial_fills","max_entry_deviation_bps")}
    kwargs["allow_partial_fills"]=cfg["allow_partial_fills"]
    kwargs["max_entry_deviation_bps"]=None if cfg["max_entry_deviation_bps"] is None else _d(cfg["max_entry_deviation_bps"])
    config=PaperConfig(**kwargs)
    risk=_fields(policy["entry_risk"],EntryRiskLimits)
    return coordinator.update_future_policy(account,event_id=event_id,limits=limits,config=config,risk_limits=risk,at=at,budgets=policy.get("budgets"))

def read_capital_command(conn,event_id):
    rows=conn.execute("SELECT account_id FROM cm34_capital_journal WHERE event_id=?",(event_id,)).fetchall()
    if not rows:return None
    if len(rows)!=1:raise ValueError("capital command identity conflict")
    state=_load(conn,rows[0][0])
    return next(e for e in state[2] if e["id"]==event_id)
