"""CM33: durable isolated synthetic replay using the existing paper engine.

Synthetic accounts never consume live/historical signals as executable quotes.
No wallet, network, credentials, or order transport exists here. Historical
and prospective execution remain blocked by the strict evidence gate.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import sqlite3

from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick, replay_paper
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot, evaluate_entry_risk
from smart_money_radar.storage.event_store import SQLiteEventStore

RADARS=("launch","smart_money")
MODES=("immediate","confirmed")
KIND="SYNTHETIC_TEST"

def _encode(v):
    def encode_special(x):
        if isinstance(x,Decimal): return str(x)
        if isinstance(x,datetime): return x.isoformat()
        raise TypeError("unsupported synthetic replay value")
    return json.dumps(v,sort_keys=True,separators=(",",":"),default=encode_special,allow_nan=False)

def _hash(s):
    return sha256(s.encode()).hexdigest()

def _decode_tick(row):
    d=dict(row)
    for k in ("at","market_at"):
        if d.get(k) is not None: d[k]=datetime.fromisoformat(d[k])
    for k in ("price","volume","bid","ask","bid_size","ask_size"):
        if d.get(k) is not None: d[k]=Decimal(d[k])
    return ReplayTick(**d)

def _decode_config(row):
    return PaperConfig(**{k:(v if isinstance(v,bool) or v is None else Decimal(v)) for k,v in row.items()})

def _decode_limits(row):
    return EntryRiskLimits(**{k:Decimal(v) for k,v in row.items()})

def _validate_tick(tick):
    if (not isinstance(tick,ReplayTick) or not isinstance(tick.quote_id,str)
            or not tick.quote_id.strip() or tick.market_at is None
            or any(x is None for x in (tick.bid,tick.ask,tick.bid_size,tick.ask_size))):
        raise ValueError("synthetic tick requires explicit independent quote id, time and finite depth")
    if any(not isinstance(x,Decimal) or not x.is_finite() for x in
           (tick.bid,tick.ask,tick.bid_size,tick.ask_size,tick.price,tick.volume)):
        raise ValueError("invalid synthetic quote")
    if not tick.bid <= tick.price <= tick.ask:
        raise ValueError("reference price outside bid/ask")

def _replay(config,limits,mode,items):
    """Rerun exact committed history; risk derived from preceding simulated state.

    Prefix replay is intentionally bounded; later optimize with a versioned,
    replay-verifiable checkpoint, not a second trading algorithm.
    """
    accepted=[]
    evaluations=[]
    previous=None
    prior_market=None
    prior_report=replay_paper([],config=config,mode=mode)
    day_pnl=Decimal(0)
    day=None
    with localcontext() as ctx:
        ctx.prec=40
        for item in items:
            tick=_decode_tick(item["tick"])
            _validate_tick(tick)
            if previous is not None and (tick.at<=previous or tick.market_at<=prior_market):
                raise ValueError("non-increasing synthetic quote chronology")
            previous=tick.at
            prior_market=tick.market_at
            current_day=tick.at.astimezone(timezone.utc).date()
            if current_day!=day:
                day=current_day
                day_pnl=Decimal(0)
            # Conservative prior-position equity, marked only with current quote.
            liquidation=prior_report.open_quantity*tick.bid*(1-config.slippage_bps/10000)*(1-config.fee_bps/10000)
            equity=prior_report.cash+liquidation
            proposed=min(config.max_entry_cash,prior_report.cash*config.max_exposure)
            risk=EntryRiskSnapshot(equity,proposed,day_pnl,config.slippage_bps,
                tick.ask*tick.ask_size,tick.halted,True)
            reasons=list(evaluate_entry_risk(limits,risk))
            if tick.volume<=0 or tick.ask_size<=0:
                reasons.append("insufficient_market_depth")
            # Synthetic evidence verified only as fixture integrity, never RPC.
            # Risk must also pass on a pending entry's execution quote.
            allowed=tick.entry_allowed and not reasons
            accepted.append(replace(tick,entry_allowed=allowed))
            evaluations.append({"quote_id":tick.quote_id,"signal_id":item["signal_id"],
                "at":tick.at.isoformat(),"entry_allowed":allowed,"reasons":sorted(set(reasons)),
                "policy":"SYNTHETIC_RISK_ONLY"})
            report=replay_paper(accepted,config=config,mode=mode)
            day_pnl+=report.realized_pnl-prior_report.realized_pnl
            prior_report=report
    report=prior_report
    # Net marked equity already includes estimated liquidation costs.
    result=asdict(report)
    result.update({"initial_cash":config.initial_cash,"unrealized_pnl":
        report.final_equity-config.initial_cash-report.realized_pnl,
        "closed_positions":sum(1 for f in report.fills if f.side=="SELL") if report.open_quantity==0 else 0,
        "risk_evaluations":evaluations,"risk_status":"SYNTHETIC_ONLY",
        "performance_evidence":False,"operational_authorized":False})
    return result

def _verify_record(row):
    payload,digest=row
    if _hash(payload)!=digest:
        raise ValueError("synthetic ledger integrity conflict")
    return json.loads(payload)

class SyntheticPaperLedger:
    """Append-only local input journal + deterministic report, one atomic commit.

    A run belongs to exactly one radar, pool, strategy and synthetic account.
    Duplicate IDs are idempotent only when their original bytes match.
    """
    def __init__(self,store: SQLiteEventStore):
        if not isinstance(store,SQLiteEventStore):
            raise TypeError("SQLiteEventStore required")
        self.store=store
    def create(self,*,run_id,radar,pool,strategy,config: PaperConfig,risk_limits: EntryRiskLimits):
        if self.store.read_only: raise ValueError("read-only store")
        if (radar not in RADARS or strategy not in MODES
                or any(not isinstance(v,str) or not v.strip() or len(v)>256 for v in (run_id,pool))
                or not isinstance(config,PaperConfig) or not isinstance(risk_limits,EntryRiskLimits)):
            raise ValueError("invalid synthetic account scope")
        meta=_encode({"run_id":run_id,"radar":radar,"pool":pool,"strategy":strategy,
            "kind":KIND,"config":asdict(config),"limits":asdict(risk_limits)})
        result=_encode(_replay(config,risk_limits,strategy,[]))
        with self.store._connection_scope() as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                old=conn.execute("SELECT metadata,metadata_sha FROM cm33_paper_runs WHERE run_id=?",(run_id,)).fetchone()
                if old is not None:
                    if old!=(meta,_hash(meta)): raise ValueError("run identity conflict")
                    return
                conn.execute("INSERT INTO cm33_paper_runs VALUES(?,?,?,?,?,?)",
                    (run_id,radar,meta,_hash(meta),result,_hash(result)))
    def append(self,run_id,*,tick: ReplayTick,signal_id=None):
        if self.store.read_only: raise ValueError("read-only store")
        _validate_tick(tick)
        if tick.signal!="NONE" and (not isinstance(signal_id,str) or not signal_id.strip()):
            raise ValueError("synthetic signal id required")
        if tick.signal=="NONE" and signal_id is not None:
            raise ValueError("unexpected signal id")
        payload=_encode({"tick":asdict(tick),"signal_id":signal_id})
        digest=_hash(payload)
        with self.store._connection_scope() as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row=conn.execute("SELECT metadata,metadata_sha,report,report_sha FROM cm33_paper_runs WHERE run_id=?",(run_id,)).fetchone()
                if row is None: raise ValueError("unknown synthetic run")
                meta=_verify_record(row[:2])
                _verify_record(row[2:])
                old=conn.execute("SELECT payload,payload_sha FROM cm33_paper_ticks WHERE run_id=? AND quote_id=?",(run_id,tick.quote_id)).fetchone()
                items=conn.execute("SELECT payload,payload_sha FROM cm33_paper_ticks WHERE run_id=? ORDER BY sequence",(run_id,)).fetchall()
                decoded=[_verify_record(x) for x in items]
                config=_decode_config(meta["config"])
                limits=_decode_limits(meta["limits"])
                # Rebuild before applying a new tick, detecting stale/mutated projection.
                if _encode(_replay(config,limits,meta["strategy"],decoded))!=row[2]:
                    raise ValueError("synthetic projection diverges from journal")
                if old is not None:
                    if old!=(payload,digest): raise ValueError("quote identity conflict")
                    return json.loads(row[2])
                if len(items)>=256:
                    raise ValueError("bounded synthetic run limit")
                if signal_id is not None and conn.execute(
                    "SELECT 1 FROM cm33_paper_ticks WHERE run_id=? AND signal_id=?",(run_id,signal_id)).fetchone():
                    raise ValueError("signal already consumed")
                decoded.append(json.loads(payload))
                result=_encode(_replay(config,limits,meta["strategy"],decoded))
                conn.execute("INSERT INTO cm33_paper_ticks VALUES(?,?,?,?,?,?)",
                    (run_id,len(items),tick.quote_id,signal_id,payload,digest))
                conn.execute("UPDATE cm33_paper_runs SET report=?,report_sha=? WHERE run_id=?",
                    (result,_hash(result),run_id))
                return json.loads(result)

def read_synthetic_paper(store):
    """Only show isolated test balances; never aggregate with real performance."""
    result={"launch":[],"smart_money":[]}
    # Existing mock dashboard adapters and pre-CM33 database schemas remain compatible.
    if not isinstance(store,SQLiteEventStore):
        return result
    with store._connection_scope() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm33_paper_runs'").fetchone() is None:
            return result
        rows=conn.execute("SELECT run_id,radar,metadata,metadata_sha,report,report_sha FROM cm33_paper_runs ORDER BY run_id LIMIT 100").fetchall()
        for rid,radar,meta,md,report,rd in rows:
            if radar not in RADARS: continue
            try:
                m=_verify_record((meta,md))
                r=_verify_record((report,rd))
                if m.get("kind")!=KIND or m.get("radar")!=radar or m.get("run_id")!=rid:
                    raise ValueError("synthetic scope conflict")
                items=conn.execute("SELECT payload,payload_sha FROM cm33_paper_ticks WHERE run_id=? ORDER BY sequence",(rid,)).fetchall()
                if _encode(_replay(_decode_config(m["config"]),_decode_limits(m["limits"]),m["strategy"],[_verify_record(x) for x in items]))!=report:
                    raise ValueError("synthetic projection conflict")
                result[radar].append({"run_id":rid,"radar":radar,"pool":m["pool"],"strategy":m["strategy"],"kind":KIND,"report":r})
            except (ValueError,TypeError,KeyError,ArithmeticError):
                result[radar].append({"run_id":rid,"radar":radar,"kind":KIND,"status":"CONFLICTED","report":None})
    return result

def paper_preflight(decision:dict,*,kind:str):
    """Persistable decision outcome; real-history/prospective gate not yet attested."""
    if kind not in ("HISTORICAL_REPLAY","PROSPECTIVE_SIMULATION","LIVE"):
        raise ValueError("unsupported execution context")
    if decision.get("radar") not in RADARS or not decision.get("id"):
        raise ValueError("invalid decision")
    reasons=set(decision.get("reasons",()))
    reasons.add("independent_executable_evidence_required")
    reasons.add("no_execution_adapter_configured")
    if kind=="LIVE": reasons.add("live_execution_disabled")
    return {"decision_id":decision["id"],"radar":decision["radar"],"kind":kind,
            "status":"BLOCKED","reasons":sorted(reasons),"operational_authorized":False,
            "economic_results_credible":False,"fills":[]}
