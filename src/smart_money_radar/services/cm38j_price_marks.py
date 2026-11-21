"""Immutable offline price observations; local integrity is not market attestation."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from smart_money_radar.services.cm38j_controlled_math import controlled_valuation
from smart_money_radar.storage.collector_authority import collector_write

def _time(v):
    t=datetime.fromisoformat(v) if isinstance(v,str) else v
    if not isinstance(t,datetime) or t.utcoffset() is None:raise ValueError("aware time required")
    return t.astimezone(timezone.utc)

def _encode(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False)

def _digest(v):
    return sha256(v.encode()).hexdigest()

def _validate(raw):
    p=json.loads(raw)
    if set(p)!={"asset","quote","source","market_at","available_at","bid","ask"}:
        raise ValueError("invalid quote fields")
    if any(not isinstance(p[k],str) or not p[k].strip() for k in ("asset","quote","source","bid","ask")) or p["asset"]==p["quote"]:
        raise ValueError("invalid mark scope")
    bid,ask=Decimal(p["bid"]),Decimal(p["ask"])
    if not bid.is_finite() or not ask.is_finite() or not 0<bid<=ask:raise ValueError("invalid quote prices")
    if not _time(p["market_at"])<=_time(p["available_at"])<=datetime.now(timezone.utc):
        raise ValueError("future quote")
    return p

def persist_mark(store,raw):
    if not isinstance(raw,str) or len(raw)>65536:raise ValueError("bounded raw quote required")
    p=_validate(raw); eid=_digest(raw)
    with store._connection_scope() as c,collector_write(c,getattr(store,"_collector_authority",None),"smart_money"):
        c.execute("""CREATE TABLE IF NOT EXISTS cm38j_price_marks(
            id TEXT PRIMARY KEY, asset TEXT NOT NULL, quote TEXT NOT NULL, source TEXT NOT NULL,
            market_at TEXT NOT NULL, available_at TEXT NOT NULL, raw TEXT NOT NULL)""")
        for action in ("UPDATE","DELETE"):
            c.execute("CREATE TRIGGER IF NOT EXISTS cm38j_marks_no_"+action.lower()+" BEFORE "+action+" ON cm38j_price_marks BEGIN SELECT RAISE(ABORT,'immutable mark'); END")
        row=(eid,p["asset"],p["quote"],p["source"],_time(p["market_at"]).isoformat(),_time(p["available_at"]).isoformat(),raw)
        old=c.execute("SELECT * FROM cm38j_price_marks WHERE id=?",(eid,)).fetchone()
        if old is not None and tuple(old)!=row:raise ValueError("mark identity conflict")
        if old is None:c.execute("INSERT INTO cm38j_price_marks VALUES(?,?,?,?,?,?,?)",row)
    return eid

def read_mark(conn,*,asset,quote,cutoff,max_age_seconds=300):
    end=_time(cutoff)
    if end>datetime.now(timezone.utc) or type(max_age_seconds) is not int or not 1<=max_age_seconds<=86400:raise ValueError("invalid cutoff or TTL")
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38j_price_marks'").fetchone():return None
    rows=conn.execute("SELECT * FROM cm38j_price_marks WHERE asset=? AND quote=? AND available_at<=? ORDER BY market_at DESC,id LIMIT 1001",(asset,quote,end.isoformat())).fetchall()
    if len(rows)>1000:raise ValueError("unbounded marks")
    marks=[]
    for eid,a,q,s,m,t,raw in rows:
        p=_validate(raw)
        if (eid,a,q,s,m,t)!=(_digest(raw),p["asset"],p["quote"],p["source"],_time(p["market_at"]).isoformat(),_time(p["available_at"]).isoformat()):raise ValueError("mark integrity conflict")
        if _time(t)>end:raise ValueError("future mark")
        if (end-_time(m)).total_seconds()<=max_age_seconds:marks.append((eid,p))
    if not marks:return None
    latest=_time(marks[0][1]["market_at"])
    candidates=[(eid,p) for eid,p in marks if _time(p["market_at"])==latest]
    if len({(Decimal(p["bid"]),Decimal(p["ask"])) for _,p in candidates})!=1:raise ValueError("divergent price marks")
    eid,p=candidates[0]
    return {"evidence_id":eid,**p,"quality":"LOCALLY_CONSISTENT_UNATTESTED","operational_authorized":False}

def valuation_status(conn,*,fifo,cutoff):
    mark=read_mark(conn,asset=fifo["token"],quote=fifo["quote_mint"],cutoff=cutoff)
    return {"mark":mark,"unrealized_pnl":None,"drawdown":None,"status":"NOT_COMPUTABLE",
            "reason":"independent_price_attestation_and_complete_cost_history_missing",
            "operational_authorized":False}
