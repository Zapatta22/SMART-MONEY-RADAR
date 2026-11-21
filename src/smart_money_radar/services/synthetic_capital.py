"""CM34: conservative multi-pool synthetic capital allocation.

Reuses CM33 replay and its durable position projection. A capital allocation
escrows the ENTIRE initial budget (including fees) until a run is explicitly
settled with no position/pending order. Shared capital cannot be double spent.
No real-money or historical execution adapter is exposed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json

from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk
from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick
from smart_money_radar.services.synthetic_paper_ledger import (
    RADARS, MODES, KIND, SyntheticPaperLedger, _encode, _hash, _verify_record,
    _decode_config, _decode_limits, _replay,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

ZERO=Decimal(0)
ONE=Decimal(1)
GENESIS="0"*64

@dataclass(frozen=True)
class CapitalLimits:
    total_exposure: Decimal
    per_radar: Decimal
    per_strategy: Decimal
    per_token: Decimal
    per_pool: Decimal
    per_wallet: Decimal
    max_daily_loss: Decimal
    max_drawdown: Decimal
    def __post_init__(self):
        if any(not isinstance(v,Decimal) or not v.is_finite() or not ZERO<v<=ONE
               for v in asdict(self).values()):
            raise ValueError("capital fractions must be finite and in (0,1]")

def _identity(value):
    if not isinstance(value,str) or not value.strip() or len(value)>256 or "\\x00" in value:
        raise ValueError("identity required")
    return value

def _time(value):
    if isinstance(value,str):
        value=datetime.fromisoformat(value)
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError("timezone required")
    return value.astimezone(timezone.utc)

def _decimal(v):
    if not isinstance(v,Decimal) or not v.is_finite() or v<=ZERO:
        raise ValueError("positive finite Decimal required")
    return v

def _chain(prev,seq,eid,digest):
    return _hash(_encode([prev,seq,eid,digest]))

def _events(conn,account):
    previous=GENESIS
    events=[]
    for seq,eid,payload,digest,p,c in conn.execute(
        "SELECT seq,event_id,payload,payload_sha,previous_sha,chain_sha FROM cm34_capital_journal WHERE account_id=? ORDER BY seq",
        (account,)):
        if seq!=len(events) or p!=previous or c!=_chain(p,seq,eid,digest):
            raise ValueError("capital journal chain conflict")
        obj=_verify_record((payload,digest))
        if obj["id"]!=eid: raise ValueError("capital event identity conflict")
        events.append(obj)
        previous=c
    return events,previous

def _append_event(conn,account,events,prev,event):
    payload=_encode(event)
    digest=_hash(payload)
    conn.execute("INSERT INTO cm34_capital_journal VALUES(?,?,?,?,?,?,?)",
        (account,len(events),event["id"],payload,digest,prev,
         _chain(prev,len(events),event["id"],digest)))

def _load(conn,account):
    row=conn.execute("SELECT metadata,metadata_sha FROM cm34_capital_accounts WHERE account_id=?",(account,)).fetchone()
    if row is None: raise ValueError("unknown synthetic capital account")
    meta=_verify_record(row)
    if meta["account_id"]!=account or meta["kind"]!=KIND: raise ValueError("capital identity conflict")
    limits=CapitalLimits(**{k:Decimal(v) for k,v in meta["limits"].items()})
    events,prev=_events(conn,account)
    active={}
    settled={}
    cash=Decimal(meta["initial"])
    last=None
    realized_by_day={}
    peak=cash
    latest_equity=cash
    for ev in events:
        at=_time(ev["at"])
        if last is not None and at<last: raise ValueError("capital chronology conflict")
        last=at
        rid=ev["run_id"]
        if ev["type"]=="POLICY":
            if rid!="__capital_policy__" or active:
                raise ValueError("policy change with active reservations")
            candidate=CapitalLimits(**{k:Decimal(v) for k,v in ev["limits"].items()})
            config=_decode_config(ev["future_config"])
            risk=_decode_limits(ev["future_risk"])
            if config.max_entry_cash>config.initial_cash or risk.max_position_fraction>candidate.total_exposure:
                raise ValueError("invalid future run policy")
            limits=candidate
            meta=dict(meta,future_config=ev["future_config"],future_risk=ev["future_risk"])
            if Decimal(ev["equity"])!=latest_equity:
                raise ValueError("policy cannot modify capital")
        elif ev["type"]=="RESERVE":
            if rid=="__capital_policy__" or rid in active or rid in settled: raise ValueError("duplicate allocation")
            budget=Decimal(ev["budget"])
            if budget<=0 or budget>cash: raise ValueError("invalid reserved amount")
            cash-=budget
            active[rid]=ev
        elif ev["type"]=="SETTLE":
            r=active.pop(rid,None)
            if r is None: raise ValueError("settlement without allocation")
            returned=Decimal(ev["returned"])
            pnl=Decimal(ev["pnl"])
            if returned<0 or returned-Decimal(r["budget"])!=pnl: raise ValueError("settlement arithmetic conflict")
            cash+=returned
            settled[rid]=ev
            day=at.date().isoformat()
            realized_by_day[day]=realized_by_day.get(day,ZERO)+pnl
        elif ev["type"]=="MARK":
            if rid not in active: raise ValueError("mark without allocation")
        else:
            raise ValueError("unknown capital event")
        equity=Decimal(ev["equity"])
        if equity<0 or not equity.is_finite(): raise ValueError("invalid equity")
        latest_equity=equity
        peak=max(peak,equity)
    bindings={}
    for rid,binding,digest in conn.execute("SELECT run_id,binding,binding_sha FROM cm34_capital_runs WHERE account_id=?",(account,)):
        bindings[rid]=_verify_record((binding,digest))
    if set(bindings)!=set(active)|set(settled): raise ValueError("capital/run linkage conflict")
    reports={}
    for rid,reservation in {**active,**{r:next(e for e in events if e["run_id"]==r and e["type"]=="RESERVE") for r in settled}}.items():
        if bindings[rid]!=reservation: raise ValueError("capital reservation conflict")
        row=conn.execute("SELECT metadata,metadata_sha,report,report_sha FROM cm33_paper_runs WHERE run_id=?",(rid,)).fetchone()
        if row is None: raise ValueError("missing allocated run")
        run=_verify_record(row[:2]); report=_verify_record(row[2:])
        if (run["run_id"],run["radar"],run["pool"],run["strategy"],run["config"]["initial_cash"]) != (
            rid,reservation["radar"],reservation["pool"],reservation["strategy"],reservation["budget"]):
            raise ValueError("allocated run scope conflict")
        if run["kind"]!=KIND: raise ValueError("non-synthetic allocation")
        items=conn.execute("SELECT sequence,quote_id,signal_id,payload,payload_sha FROM cm33_paper_ticks WHERE run_id=? ORDER BY sequence",(rid,)).fetchall()
        decoded=[]
        for seq,qid,sid,payload,digest in items:
            obj=_verify_record((payload,digest))
            if seq!=len(decoded) or obj["tick"]["quote_id"]!=qid or obj["signal_id"]!=sid:
                raise ValueError("allocated tick linkage conflict")
            decoded.append(obj)
        if _encode(_replay(_decode_config(run["config"]),_decode_limits(run["limits"]),run["strategy"],decoded))!=row[2]:
            raise ValueError("allocated position projection conflict")
        reports[rid]=report
        if rid in settled:
            if (Decimal(report["cash"])!=Decimal(settled[rid]["returned"])
                    or Decimal(report["open_quantity"])!=ZERO or report["pending_side"] is not None
                    or report["awaiting_confirmation"]):
                raise ValueError("settled position changed")
        marks=[e for e in events if e["run_id"]==rid and e["type"]=="MARK"]
        if len(marks)!=len(decoded): raise ValueError("allocated tick/capital mark gap")
        if marks and marks[-1]["report_sha"]!=row[3]: raise ValueError("allocated report mark conflict")
    reserved=sum((Decimal(e["budget"]) for e in active.values()),ZERO)
    equity=cash+sum((Decimal(reports[r]["final_equity"]) for r in active),ZERO)
    if equity!=latest_equity: raise ValueError("capital equity reconciliation conflict")
    drawdown=(peak-equity)/peak if peak>0 else ONE
    return meta,limits,events,prev,active,settled,reports,cash,reserved,equity,peak,drawdown,last,realized_by_day

def _snapshot(state,as_of=None):
    meta,limits,events,prev,active,settled,reports,cash,reserved,equity,peak,drawdown,last,pnl=state
    axis=("radar","strategy","token","pool","wallet")
    exposure={}
    for field in axis:
        grouped={}
        for v in active.values():
            key=v[field]; grouped[key]=grouped.get(key,ZERO)+Decimal(v["budget"])
        exposure[field]={k:str(v) for k,v in sorted(grouped.items())}
    point=_time(as_of) if as_of is not None else last
    realized=sum((Decimal(r["realized_pnl"]) for r in reports.values()),ZERO)
    unrealized=sum((Decimal(reports[r]["unrealized_pnl"]) for r in active),ZERO)
    # Daily risk derives from the changes in realized PnL at each committed quote,
    # not from settlement date; settlement merely releases escrow.
    daily=sum((Decimal(e.get("realized_delta","0")) for e in events
               if e["type"]=="MARK" and point is not None and _time(e["at"]).date()==point.date()),ZERO)
    return {"account_id":meta["account_id"],"kind":KIND,"currency":meta["currency"],"allowed_radars":meta["radars"],
        "initial_capital":meta["initial"],"capital_available":str(cash),"capital_reserved":str(reserved),
        "risk_limits":{k:str(v) for k,v in asdict(limits).items()},"future_run_config":meta.get("future_config"),"future_entry_risk":meta.get("future_risk"),
        "equity":str(equity),"peak_equity":str(peak),"drawdown":str(drawdown),
        "realized_pnl":str(realized),"unrealized_pnl":str(unrealized),"daily_realized_pnl":str(daily),
        "exposure":exposure,"positions":[{"run_id":r,"radar":v["radar"],"pool":v["pool"],
            "strategy":v["strategy"],"token":v["token"],"wallet":v["wallet"],"budget":v["budget"],
            "report":reports[r]} for r,v in sorted(active.items())],
        "settled_runs":len(settled),"event_count":len(events),"operational_authorized":False,
        "performance_evidence":False,"risk_status":"SYNTHETIC_ONLY"}

class SyntheticCapitalCoordinator:
    """All mutations serialized under BEGIN IMMEDIATE, sharing CM33 connection."""
    def __init__(self,store):
        if not isinstance(store,SQLiteEventStore): raise TypeError("SQLiteEventStore required")
        self.store=store
    def create(self,*,account_id,initial:Decimal,currency,radars,limits:CapitalLimits):
        if self.store.read_only: raise ValueError("read-only")
        _identity(account_id); _identity(currency); _decimal(initial)
        if not isinstance(limits,CapitalLimits) or not isinstance(radars,tuple) or not radars or set(radars)-set(RADARS) or len(set(radars))!=len(radars):
            raise ValueError("invalid account policy")
        meta=_encode({"account_id":account_id,"kind":KIND,"initial":str(initial),"currency":currency,
            "radars":sorted(radars),"limits":asdict(limits)})
        with self.store._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE")
            old=conn.execute("SELECT metadata,metadata_sha FROM cm34_capital_accounts WHERE account_id=?",(account_id,)).fetchone()
            if old:
                if old!=(meta,_hash(meta)): raise ValueError("account conflict")
                return
            conn.execute("INSERT INTO cm34_capital_accounts VALUES(?,?,?)",(account_id,meta,_hash(meta)))
    def update_future_policy(self,account_id,*,event_id,limits:CapitalLimits,config:PaperConfig,risk_limits:EntryRiskLimits,at):
        """Change future synthetic risk only; never touch principal or reserves.
        Fully settled accounts only; historical replay stays immutable.
        This local core is not an HTTP command or a real order adapter.
        """
        if self.store.read_only: raise ValueError("read-only")
        _identity(event_id);point=_time(at)
        if not isinstance(limits,CapitalLimits) or not isinstance(config,PaperConfig) or not isinstance(risk_limits,EntryRiskLimits):
            raise ValueError("typed synthetic policy required")
        if config.max_entry_cash>config.initial_cash or risk_limits.max_position_fraction>limits.total_exposure:
            raise ValueError("inconsistent future policy")
        with self.store._connection_scope() as conn,conn,localcontext() as ctx:
            ctx.prec=40
            conn.execute("BEGIN IMMEDIATE")
            state=_load(conn,account_id)
            meta,prior,events,prev,active,settled,reports,cash,reserved,equity,peak,dd,last,pnl=state
            ev={"type":"POLICY","id":event_id,"run_id":"__capital_policy__","at":point.isoformat(),
                "limits":{k:str(v) for k,v in asdict(limits).items()},
                "future_config":json.loads(_encode(asdict(config))),
                "future_risk":json.loads(_encode(asdict(risk_limits))),"equity":str(equity)}
            for old in events:
                if old["id"]==event_id:
                    ev["equity"]=old["equity"]
                    if ev!=old: raise ValueError("policy request id conflict")
                    return _snapshot(state)
            if active or reserved!=ZERO or (last is not None and point<last):
                raise ValueError("settle all reservations before changing policy")
            if config.initial_cash>cash or config.initial_cash>equity*limits.total_exposure:
                raise ValueError("future allocation exceeds available capital")
            if dd>=limits.max_drawdown:
                raise ValueError("new drawdown limit already breached")
            _append_event(conn,account_id,events,prev,ev)
            return _snapshot(_load(conn,account_id),point)

    def reserve(self,account_id,*,event_id,run_id,radar,pool,token,wallet,strategy,config:PaperConfig,risk_limits:EntryRiskLimits,at):
        """Escrow an entire virtual subaccount, including fees, before any order."""
        if self.store.read_only: raise ValueError("read-only")
        for v in (event_id,run_id,pool,token,wallet): _identity(v)
        if radar not in RADARS or strategy not in MODES or not isinstance(config,PaperConfig) or not isinstance(risk_limits,EntryRiskLimits):
            raise ValueError("invalid synthetic allocation")
        point=_time(at); budget=config.initial_cash
        with self.store._connection_scope() as conn,conn,localcontext() as ctx:
            ctx.prec=40
            conn.execute("BEGIN IMMEDIATE")
            state=_load(conn,account_id)
            meta,limits,events,prev,active,settled,reports,cash,reserved,equity,peak,dd,last,pnl=state
            run_meta=_encode({"run_id":run_id,"radar":radar,"pool":pool,"strategy":strategy,
                "kind":KIND,"config":asdict(config),"limits":asdict(risk_limits)})
            ev={"type":"RESERVE","id":event_id,"run_id":run_id,"at":point.isoformat(),
                "radar":radar,"pool":pool,"token":token,"wallet":wallet,"strategy":strategy,
                "budget":str(budget),"run_metadata_sha":_hash(run_meta),"equity":str(equity)}
            for old in events:
                if old["id"]==event_id:
                    ev["equity"]=old["equity"]
                    if ev!=old: raise ValueError("reservation id conflict")
                    return _snapshot(state)
            if run_id=="__capital_policy__" or radar not in meta["radars"] or (last is not None and point<last):
                raise ValueError("allocation scope/time mismatch")
            if meta.get("future_config") is not None and (json.loads(_encode(asdict(config)))!=meta["future_config"] or json.loads(_encode(asdict(risk_limits)))!=meta["future_risk"]):
                raise ValueError("allocation does not match current audited future policy")
            if conn.execute("SELECT 1 FROM cm33_paper_runs WHERE run_id=?",(run_id,)).fetchone():
                raise ValueError("run already exists")
            from smart_money_radar.services.operational_controls import read_control_state
            ctl=read_control_state(conn)
            if ctl["emergency_halt"] or ctl["radars"][radar]!="RUNNING" or ctl["entries_paused"]:
                raise ValueError("operational pause blocks reservation")
            if equity<=0 or budget>cash or reserved+budget>equity*limits.total_exposure:
                raise ValueError("insufficient capital or aggregate exposure")
            for axis,limit in (("radar",limits.per_radar),("strategy",limits.per_strategy),
                ("token",limits.per_token),("pool",limits.per_pool),("wallet",limits.per_wallet)):
                used=sum((Decimal(v["budget"]) for v in active.values() if v[axis]==ev[axis]),ZERO)
                if used+budget>equity*limit: raise ValueError(axis+" exposure limit")
            daily=Decimal(_snapshot(state,point)["daily_realized_pnl"])
            if daily<=-equity*limits.max_daily_loss or dd>=limits.max_drawdown:
                raise ValueError("capital loss or drawdown limit")
            report=_encode(_replay(config,risk_limits,strategy,[]))
            conn.execute("INSERT INTO cm33_paper_runs VALUES(?,?,?,?,?,?)",(run_id,radar,run_meta,_hash(run_meta),report,_hash(report)))
            binding=_encode(ev)
            conn.execute("INSERT INTO cm34_capital_runs VALUES(?,?,?,?)",(account_id,run_id,binding,_hash(binding)))
            _append_event(conn,account_id,events,prev,ev)
            return _snapshot(_load(conn,account_id),point)
    def tick(self,account_id,*,run_id,tick:ReplayTick,signal_id=None):
        if self.store.read_only: raise ValueError("read-only")
        point=_time(tick.at)
        with self.store._connection_scope() as conn,conn,localcontext() as ctx:
            ctx.prec=40
            conn.execute("BEGIN IMMEDIATE")
            state=_load(conn,account_id)
            meta,limits,events,prev,active,settled,reports,cash,reserved,equity,peak,dd,last,pnl=state
            if run_id not in active: raise ValueError("allocation inactive")
            input_payload=_encode({"tick":asdict(tick),"signal_id":signal_id})
            eid="mark:"+_hash(_encode([run_id,tick.quote_id]))
            for old in events:
                if old["id"]==eid:
                    if old.get("input_sha")!=_hash(input_payload): raise ValueError("quote conflict")
                    return _snapshot(state,point)
            if last is not None and point<last: raise ValueError("capital cutoff regression")
            r=active[run_id]
            if signal_id is not None:
                # Across a shared capital account, a signal is consumed only once
                # per radar/strategy, independent of pool or run.
                if any(e.get("signal_id")==signal_id and e.get("radar")==r["radar"] and e.get("strategy")==r["strategy"] for e in events if e["type"]=="MARK"):
                    raise ValueError("capital signal already consumed")
            from smart_money_radar.services.operational_controls import read_control_state
            ctl=read_control_state(conn)
            halted=ctl["emergency_halt"] or tick.halted
            daily=Decimal(_snapshot(state,point)["daily_realized_pnl"])
            blocked=(halted or ctl["entries_paused"] or ctl["radars"][r["radar"]]!="RUNNING"
                or equity<=0 or daily<=-equity*limits.max_daily_loss or dd>=limits.max_drawdown
                or reserved>equity*limits.total_exposure)
            for axis,limit in (("radar",limits.per_radar),("strategy",limits.per_strategy),
                ("token",limits.per_token),("pool",limits.per_pool),("wallet",limits.per_wallet)):
                used=sum((Decimal(v["budget"]) for v in active.values() if v[axis]==r[axis]),ZERO)
                blocked=blocked or used>equity*limit
            effective=replace(tick,entry_allowed=tick.entry_allowed and not blocked,halted=halted)
            before=Decimal(reports[run_id]["realized_pnl"])
            result=SyntheticPaperLedger(self.store)._append(run_id,tick=effective,signal_id=signal_id,connection=conn)
            new_equity=equity-Decimal(reports[run_id]["final_equity"])+Decimal(result["final_equity"])
            ev={"type":"MARK","id":eid,"run_id":run_id,"at":point.isoformat(),"equity":str(new_equity),
                "report_sha":_hash(_encode(result)),"input_sha":_hash(input_payload),
                "signal_id":signal_id,"radar":r["radar"],"strategy":r["strategy"],
                "realized_delta":str(Decimal(result["realized_pnl"])-before),"capital_entry_blocked":bool(blocked)}
            _append_event(conn,account_id,events,prev,ev)
            return _snapshot(_load(conn,account_id),point)
    def settle(self,account_id,*,run_id,event_id,at):
        if self.store.read_only: raise ValueError("read-only")
        _identity(event_id);point=_time(at)
        with self.store._connection_scope() as conn,conn,localcontext() as ctx:
            ctx.prec=40
            conn.execute("BEGIN IMMEDIATE")
            state=_load(conn,account_id)
            meta,limits,events,prev,active,settled,reports,cash,reserved,equity,peak,dd,last,pnl=state
            for old in events:
                if old["id"]==event_id:
                    if old["type"]!="SETTLE" or old["run_id"]!=run_id or old["at"]!=point.isoformat():
                        raise ValueError("settlement conflict")
                    return _snapshot(state)
            if run_id not in active or (last is not None and point<last): raise ValueError("inactive or past settlement")
            r=reports[run_id]
            if Decimal(r["open_quantity"])!=ZERO or r["pending_side"] or r["awaiting_confirmation"]:
                raise ValueError("open exposure or order prevents release")
            returned=Decimal(r["cash"])
            ev={"type":"SETTLE","id":event_id,"run_id":run_id,"at":point.isoformat(),"returned":str(returned),
                "pnl":str(returned-Decimal(active[run_id]["budget"])),"equity":str(equity)}
            _append_event(conn,account_id,events,prev,ev)
            return _snapshot(_load(conn,account_id),point)
    def snapshot(self,account_id):
        with self.store._connection_scope() as conn,localcontext() as ctx:
            ctx.prec=40
            conn.execute("BEGIN")
            return _snapshot(_load(conn,account_id))

def read_capital_accounts(store):
    if not isinstance(store,SQLiteEventStore): return []
    with store._connection_scope() as conn,localcontext() as ctx:
        ctx.prec=40
        conn.execute("BEGIN")
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm34_capital_accounts'").fetchone():
            return []
        result=[]
        for (aid,) in conn.execute("SELECT account_id FROM cm34_capital_accounts ORDER BY account_id LIMIT 100"):
            try:
                state=_load(conn,aid)
                snapshot=_snapshot(state)
                # Only integrity-verified journal rows; no interpolation, price
                # lookup, invented timestamps or cross-currency aggregation.
                journal=state[2]
                snapshot["equity_history"]=[
                    {"at":e["at"],"equity":e["equity"],"type":e["type"],"run_id":e["run_id"]}
                    for e in journal[-500:]]
                snapshot["history_truncated"]=len(journal)>500
                settled=state[5]
                wins=sum(Decimal(e["pnl"])>0 for e in settled.values())
                snapshot["settled_winning_runs"]=wins
                snapshot["settled_win_rate"]=str(Decimal(wins)/len(settled)) if settled else None
                snapshot["win_rate_unit"]="SETTLED_SYNTHETIC_RUNS_NOT_TRADES"
                result.append(snapshot)
            except (ValueError,TypeError,KeyError,ArithmeticError):
                result.append({"account_id":aid,"kind":KIND,"status":"CONFLICTED","operational_authorized":False})
        return result
