"""CM34 local operational policy journal. No HTTP write route exists.

Only explicitly injected in-process operator capabilities may change the
local synthetic control state. This is NOT remote/mobile authentication.
Restart reads the immutable journal; emergency halt is sticky and no live
transition is supported. Alert records are the transition receipts themselves.
"""
from datetime import datetime,timezone
import hmac
import json
from hashlib import sha256
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.synthetic_paper_ledger import _encode,_hash,_verify_record,RADARS

GENESIS="0"*64
ACTIONS=("START","PAUSE","PAUSE_ENTRIES","RESUME_ENTRIES","EMERGENCY_HALT","RADAR_FAULT","RADAR_RECOVERED")
def _chain(p,seq,eid,d):
    return _hash(_encode([p,seq,eid,d]))

def _load(conn):
    state={"radars":{r:"PAUSED" for r in RADARS},"entries_paused":True,
        "emergency_halt":False,"live_authorized":False,"control_surface":"LOCAL_ONLY",
        "remote_writes_enabled":False,"autonomy_24h_verified":False,"alerts":[]}
    events=[]; prev=GENESIS; last=None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm34_operational_journal'").fetchone():
        return state,events,prev
    for seq,eid,payload,digest,p,chain in conn.execute(
        "SELECT seq,event_id,payload,payload_sha,previous_sha,chain_sha FROM cm34_operational_journal ORDER BY seq"):
        if seq!=len(events) or p!=prev or chain!=_chain(p,seq,eid,digest):
            raise ValueError("operation journal chain conflict")
        e=_verify_record((payload,digest))
        at=datetime.fromisoformat(e["at"])
        if e["id"]!=eid or at.utcoffset() is None or (last is not None and at<last):
            raise ValueError("operation identity/time conflict")
        last=at; action=e["action"]; radar=e["radar"]
        if action not in ACTIONS or not e.get("actor"): raise ValueError("invalid control action")
        if action in ("START","PAUSE","RADAR_FAULT","RADAR_RECOVERED"):
            if radar not in RADARS: raise ValueError("invalid radar target")
            if action=="START":
                if state["emergency_halt"]: raise ValueError("sticky halt")
                state["radars"][radar]="RUNNING"
            elif action=="PAUSE": state["radars"][radar]="PAUSED"
            elif action=="RADAR_FAULT": state["radars"][radar]="FAULTED"
            else: state["radars"][radar]="PAUSED"
        elif radar is not None: raise ValueError("global action has radar target")
        elif action=="PAUSE_ENTRIES": state["entries_paused"]=True
        elif action=="RESUME_ENTRIES":
            if state["emergency_halt"]: raise ValueError("sticky halt")
            state["entries_paused"]=False
        elif action=="EMERGENCY_HALT":
            state["emergency_halt"]=True;state["entries_paused"]=True
            state["radars"]={r:"PAUSED" for r in RADARS}
        events.append(e);prev=chain
    state["alerts"]=events[-50:]
    return state,events,prev

def read_control_state(conn):
    try: return _load(conn)[0]
    except (ValueError,KeyError,TypeError,ArithmeticError):
        return {"radars":{r:"FAULTED" for r in RADARS},"entries_paused":True,"emergency_halt":True,
            "live_authorized":False,"remote_writes_enabled":False,"autonomy_24h_verified":False,
            "control_surface":"LOCAL_ONLY","status":"CONFLICTED","alerts":[]}

def read_operational_status(store):
    if not isinstance(store,SQLiteEventStore):
        return {"radars":{r:"PAUSED" for r in RADARS},"entries_paused":True,"emergency_halt":False,
                "live_authorized":False,"remote_writes_enabled":False,"autonomy_24h_verified":False,"alerts":[]}
    with store._connection_scope() as conn:
        return read_control_state(conn)

class LocalOperationalControls:
    """Trusted local process capability; token is never persisted or served."""
    def __init__(self,store,*,operator_capability:bytes):
        if not isinstance(store,SQLiteEventStore) or not isinstance(operator_capability,bytes) or len(operator_capability)<32:
            raise ValueError("local operator capability required")
        self.store=store
        self._capability=operator_capability
    def apply(self,*,capability:bytes,event_id,action,actor,at,radar=None,reason):
        if not isinstance(capability,bytes) or not hmac.compare_digest(capability,self._capability):
            raise PermissionError("unauthorized local control")
        if self.store.read_only: raise PermissionError("read-only store")
        if action not in ACTIONS or any(not isinstance(v,str) or not v.strip() or len(v)>256 for v in (event_id,actor,reason)):
            raise ValueError("invalid local control request")
        if not isinstance(at,datetime) or at.utcoffset() is None: raise ValueError("timezone required")
        e={"id":event_id,"action":action,"actor":actor,"at":at.astimezone(timezone.utc).isoformat(),
            "radar":radar,"reason":reason}
        payload=_encode(e); digest=_hash(payload)
        with self.store._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE")
            state,events,prev=_load(conn)
            for old in events:
                if old["id"]==event_id:
                    if old!=e: raise ValueError("control request id conflict")
                    return state
            if action in ("START","RESUME_ENTRIES") and state["emergency_halt"]:
                raise ValueError("emergency halt requires future reviewed reset policy")
            conn.execute("INSERT INTO cm34_operational_journal VALUES(?,?,?,?,?,?)",
                (len(events),event_id,payload,digest,prev,_chain(prev,len(events),event_id,digest)))
            return _load(conn)[0]
