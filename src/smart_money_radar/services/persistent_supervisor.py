"""CM36: fenced, bounded, offline operational supervisor.

Coordinates existing read-only archive/intelligence producers and synthetic
capital reconciliation. No network transport or order executor is enabled.
Each cycle prepares read-only work, then commits under a generation fence.
An expired owner cannot renew, publish a decision, profile, or checkpoint.
Legacy collectors and independent local tools are NOT placed under this
lease: integrating their writer paths is a separate live-gate requirement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import json
import sqlite3
import sys
import time
import uuid

from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.synthetic_paper_ledger import RADARS, _encode, _hash, _verify_record, paper_preflight
from smart_money_radar.services.operational_controls import read_control_state
from smart_money_radar.services.radar_event_bridge import launch_events_from_archive, smart_money_events_from_archive
from smart_money_radar.services.radar_intelligence import read_intelligence_reports
from smart_money_radar.services.wallet_discovery import WalletDiscoveryPolicy, discover_wallets, _write_wallet_snapshot
from smart_money_radar.services.synthetic_capital import read_capital_accounts

from smart_money_radar.storage.collector_authority import AuthorityLost, CollectorAuthority, collector_control_revision, verify_collector_authority

@dataclass(frozen=True)
class SupervisorPolicy:
    lease_seconds: float=30.0
    interval_seconds: float=5.0
    max_backoff_seconds: float=60.0
    max_failures: int=5
    batch_limit: int=20
    def __post_init__(self):
        if (any(type(x) not in (float,int) or not isfinite(x) or x<=0
                for x in (self.lease_seconds,self.interval_seconds,self.max_backoff_seconds))
            or not self.interval_seconds<self.lease_seconds
            or self.max_backoff_seconds<self.interval_seconds
            or type(self.max_failures) is not int or not 1<=self.max_failures<=20
            or type(self.batch_limit) is not int or not 1<=self.batch_limit<=100):
            raise ValueError("invalid supervisor policy")

def _number(value):
    if type(value) not in (int,float) or not isfinite(value) or value<0:
        raise ValueError("invalid supervisor clock")
    return float(value)

def _stamp(now):
    return datetime.fromtimestamp(now,timezone.utc)

def _transient_sqlite_lock(exc):
    code = getattr(exc, "sqlite_errorcode", None)
    return isinstance(exc, sqlite3.OperationalError) and isinstance(code, int) and (
        code & 0xFF
    ) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)

def _lease(conn):
    row=conn.execute("SELECT generation,owner,heartbeat,expires,status,payload_sha FROM cm36_supervisor_lease WHERE singleton=1").fetchone()
    if row is None:return None
    generation,owner,heartbeat,expires,status,digest=row
    if (_hash(_encode([generation,owner,heartbeat,expires,status]))!=digest
        or type(generation) is not int or generation<1 or not owner
        or status not in ("ACTIVE","STOPPED") or not isfinite(heartbeat)
        or not isfinite(expires) or expires<heartbeat):
        raise AuthorityLost("lease integrity conflict")
    return row[:5]

def _write_lease(conn,generation,owner,now,expires,status):
    vals=[generation,owner,float(now),float(expires),status]
    conn.execute("INSERT INTO cm36_supervisor_lease VALUES(1,?,?,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET generation=excluded.generation,owner=excluded.owner,heartbeat=excluded.heartbeat,expires=excluded.expires,status=excluded.status,payload_sha=excluded.payload_sha",
        (*vals,_hash(_encode(vals))))

def _task(conn,radar):
    row=conn.execute("SELECT payload,payload_sha FROM cm36_supervisor_tasks WHERE radar=?",(radar,)).fetchone()
    if row is None:
        return {"radar":radar,"status":"IDLE","failures":0,"next_due":0.0,
            "last_activity":None,"checkpoint":None,"cycles":0,"last_error":None,
            "connection":"NOT_CONNECTED","coverage":"UNKNOWN","pending":True}
    task=_verify_record(row)
    if task.get("radar")!=radar:raise ValueError("task identity conflict")
    return task

def _put_task(conn,task):
    payload=_encode(task)
    conn.execute("INSERT INTO cm36_supervisor_tasks VALUES(?,?,?) ON CONFLICT(radar) DO UPDATE SET payload=excluded.payload,payload_sha=excluded.payload_sha",
        (task["radar"],payload,_hash(payload)))

def _alert(conn,radar,kind,identity,now):
    # Repeated observation does not create repeated alerts. No raw secrets or
    # exception text are exposed on the read-only dashboard.
    aid=_hash(_encode([radar,kind,identity]))
    payload=_encode({"id":aid,"radar":radar,"kind":kind,"at":_stamp(now).isoformat(),"identity":identity})
    conn.execute("INSERT OR IGNORE INTO cm36_supervisor_alerts VALUES(?,?,?,?)",(aid,radar,payload,_hash(payload)))

class PersistentSupervisor:
    """One owner per database, fenced generations; no takeover of live adapters."""
    def __init__(self,store,*,policy=SupervisorPolicy(),discovery_policy=WalletDiscoveryPolicy(),
                 scopes=None,clock=time.time,economic_account_id=None,economic_notional=None,
                 launch_history=None):
        if not isinstance(store,SQLiteEventStore) or store.read_only or not isinstance(policy,SupervisorPolicy):
            raise ValueError("writable SQLite store and policy required")
        if str(store.database_path)==":memory:":raise ValueError("persistent database required")
        self.store=store;self.policy=policy;self.discovery_policy=discovery_policy
        self.scopes=dict(scopes or {}); self.clock=clock
        self.owner=uuid.uuid4().hex;self.generation=None
        self.economic_account_id=economic_account_id
        self.economic_notional=economic_notional
        self.launch_history=launch_history
        if (economic_account_id is None)!=(economic_notional is None):
            raise ValueError("explicit offline economic account and notional required")

    def _connection_scope(self):
        # Do not inherit the collector's long wait when competing for a lease.
        return self.store._connection_scope(
            busy_timeout_seconds=min(0.25, self.policy.interval_seconds / 4)
        )

    def acquire(self):
        with self._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE");now=_number(self.clock());old=_lease(conn)
            if old and now<old[2]:raise AuthorityLost("clock regressed")
            if old and old[4]=="ACTIVE" and now<old[3]:
                raise AuthorityLost("active supervisor already owns database")
            # Durable distinction between standalone and previously managed.
            marker=conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm36_managed_marker' AND type='table'").fetchone()
            if marker and old is None:
                raise AuthorityLost("managed lease missing; explicit recovery required")
            conn.execute("CREATE TABLE IF NOT EXISTS cm36_managed_marker (singleton INTEGER PRIMARY KEY CHECK(singleton=1))")
            conn.execute("INSERT OR IGNORE INTO cm36_managed_marker VALUES(1)")
            generation=old[0]+1 if old else 1
            _write_lease(conn,generation,self.owner,now,now+self.policy.lease_seconds,"ACTIVE")
            if old and old[4]=="ACTIVE":
                _alert(conn,"supervisor","WATCHDOG_EXPIRED",str(old[0]),now)
            _alert(conn,"supervisor","STARTED",str(generation),now)
        self.generation=generation
        return generation
    def _fence(self,conn):
        now=_number(self.clock());lease=_lease(conn)
        if (lease is None or lease[0]!=self.generation or lease[1]!=self.owner
            or lease[4]!="ACTIVE" or now<lease[2] or now>=lease[3]):
            raise AuthorityLost("supervisor generation expired or replaced")
        return now
    def collector_authority(self, radar):
        """Capture the current generation, not a mutable supervisor reference."""
        if radar not in RADARS:
            raise ValueError("invalid radar")
        with self._connection_scope() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            self._fence(conn)
            token = CollectorAuthority(str(self.store.database_path.resolve()),
                                       self.generation,self.owner,radar,self.clock,
                                       collector_control_revision(conn,radar))
            verify_collector_authority(conn,token,radar)
        return token

    def bind_collector_store(self, store, radar):
        """Issue a new immutable handle without activating network access."""
        return store.bind_collector(self.collector_authority(radar))

    def heartbeat(self):
        with self._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE");now=self._fence(conn)
            _write_lease(conn,self.generation,self.owner,now,now+self.policy.lease_seconds,"ACTIVE")
        return now
    def stop(self):
        with self._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE");now=self._fence(conn)
            _write_lease(conn,self.generation,self.owner,now,now,"STOPPED")
            _alert(conn,"supervisor","STOPPED",str(self.generation),now)
    def _prepare(self,radar,now):
        # Only bounded archive reads and pure analysis; no independent write
        # transaction, no RPC calls, no synthetic or real orders generated.
        point=_stamp(now)
        if radar=="launch":
            events=launch_events_from_archive(self.store.list_cpmm_launch_archived_event_inputs(limit=self.policy.batch_limit))
            profile=None
        else:
            events=smart_money_events_from_archive(self.store.list_smr_archived_event_inputs(limit=self.policy.batch_limit))
            profile=discover_wallets(self.store,as_of=point,policy=self.discovery_policy)
        from dataclasses import asdict
        source=[asdict(e) for e in events]
        data=read_intelligence_reports(self.store,{radar:source},scopes=self.scopes,as_of=point,
            cpmm_history=self.launch_history if radar=="launch" else None)[radar]
        lookup={e["id"]:e for e in source}
        results=[]
        for decision in data:
            event=lookup[decision["event_id"]]
            if decision.get("operational_authorized") is not False:raise ValueError("unexpected authorization")
            # Serialize datetimes, Decimals via existing canonical codec.
            payload={"event":event,"decision":decision,"paper":paper_preflight(decision,kind="PROSPECTIVE_SIMULATION")}
            results.append((event["id"],_hash(_encode(event)),payload))
        return profile,results
    def _blocked(self,conn,radar):
        c=read_control_state(conn)
        return c["emergency_halt"] or c["radars"][radar]!="RUNNING"
    def step(self,radar):
        if radar not in RADARS:raise ValueError("invalid radar")
        with self._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE");now=self._fence(conn);task=_task(conn,radar)
            if self._blocked(conn,radar):
                task.update(status="PAUSED",pending=True);_put_task(conn,task);return task
            if task["failures"]>=self.policy.max_failures:
                return task # explicit reviewed reset is future work, no infinite retry
            if now<task["next_due"]:return task
        try:
            profile,results=self._prepare(radar,now)
        except Exception as exc:
            if isinstance(exc,AuthorityLost) or _transient_sqlite_lock(exc):raise
            return self._failure(radar,type(exc).__name__)
        try:
            economic_store=None
            if radar=="smart_money" and self.economic_account_id is not None:
                economic_store=self.bind_collector_store(self.store,radar)
            with self._connection_scope() as conn,conn:
                conn.execute("BEGIN IMMEDIATE");finished=self._fence(conn)
                task=_task(conn,radar)
                if self._blocked(conn,radar):
                    task.update(status="PAUSED",pending=True);_put_task(conn,task);return task
                if profile is not None:_write_wallet_snapshot(conn,profile)
                new=0
                for eid,ed,payload in results:
                    old=conn.execute("SELECT payload,payload_sha FROM cm36_decision_journal WHERE radar=? AND event_id=? AND event_sha=?",(radar,eid,ed)).fetchone()
                    if old:
                        old_obj=_verify_record(old)
                        if _hash(_encode(old_obj["event"]))!=ed:raise ValueError("decision journal event conflict")
                        continue
                    if radar=="smart_money":
                        payload["causal_economic_attempt"]=self._economic_attempt(
                            conn,economic_store,payload["event"],_stamp(now))
                    encoded=_encode(payload)
                    conn.execute("INSERT INTO cm36_decision_journal VALUES(?,?,?,?,?)",(radar,eid,ed,encoded,_hash(encoded)))
                    _alert(conn,radar,"ARCHIVED_EVENT_BLOCKED",ed,finished)
                    new+=1
                if task["failures"]:_alert(conn,radar,"RECOVERED",str(self.generation)+":"+str(task["cycles"]),finished)
                task.update(status="READY",failures=0,last_error=None,next_due=finished+self.policy.interval_seconds,
                    last_activity=_stamp(finished).isoformat(),cycles=task["cycles"]+1,
                    checkpoint=results[-1][0] if results else task["checkpoint"],
                    pending=False,processed_new=new)
                _put_task(conn,task)
                # Verify immediately before commit; no other owner can acquire
                # the same database until this write transaction commits.
                self._fence(conn)
                return task
        except AuthorityLost:raise
        except (sqlite3.Error,ValueError,TypeError,KeyError,ArithmeticError) as exc:
            if _transient_sqlite_lock(exc):raise
            return self._failure(radar,type(exc).__name__)
    def _economic_attempt(self,conn,bound,event,point):
        """Reuse CM38I under the existing generation-fenced journal commit."""
        if bound is None:
            return {"status":"BLOCKED","reason":"offline_economic_account_not_configured"}
        if event.get("direction") not in ("BUY","SELL") or not event.get("wallet_address"):
            return {"status":"BLOCKED","reason":"economic_scope_unknown"}
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_economic_evidence_links'").fetchone():
            return {"status":"BLOCKED","reason":"economic_rpc_link_missing"}
        op=event["source_reference"].removeprefix("swap_replay_archive:")
        rows=conn.execute("""SELECT evidence_id FROM cm38_economic_evidence_links
            WHERE radar='smart_money' AND wallet_address=? AND signature=?
              AND entity_type='replay_opportunity' AND entity_id=? AND linked_at<=?""",
            (event["wallet_address"],event["signature"],op,point.isoformat())).fetchall()
        if len(rows)!=1:
            return {"status":"BLOCKED","reason":"economic_rpc_link_missing_or_ambiguous"}
        from smart_money_radar.services.cm38i_decision_audit import record_blocked_virtual_entry
        token,quote=(event["output_mint"],event["input_mint"]) if event["direction"]=="BUY" else (event["input_mint"],event["output_mint"])
        if not token or not quote:
            return {"status":"BLOCKED","reason":"economic_scope_unknown"}
        request_id="cm36:"+_hash(_encode(["smart_money",op,rows[0][0]]))
        return record_blocked_virtual_entry(bound,request_id=request_id,
            account_id=self.economic_account_id,radar="smart_money",strategy="confirmed",
            evidence_id=rows[0][0],decision_at=point,requested_notional=self.economic_notional,
            economic_scope=(event["wallet_address"],token,quote),_connection=conn)

    def _failure(self,radar,error):
        with self._connection_scope() as conn,conn:
            conn.execute("BEGIN IMMEDIATE");now=self._fence(conn);task=_task(conn,radar)
            n=task["failures"]+1
            task.update(status="FAULTED" if n>=self.policy.max_failures else "BACKOFF",failures=n,
                last_error=error,next_due=now+min(self.policy.max_backoff_seconds,self.policy.interval_seconds*2**(n-1)),pending=True)
            _put_task(conn,task)
            _alert(conn,radar,"TASK_FAILURE",str(self.generation)+":"+str(task["cycles"])+":"+str(n)+":"+error,now)
            return task
    def cycle(self, *, stop_event=None):
        if self._retry_busy(self.heartbeat, stop_event) is None:
            return None
        results={}
        for radar in RADARS:
            task = self._retry_busy(lambda: self.step(radar), stop_event)
            if task is None or self._retry_busy(self.heartbeat, stop_event) is None:
                return None
            results[radar] = task
        # Existing capital replay validates restoration and consistency, not
        # execution. Failed reconciliation never authorizes new entries.
        capital = self._retry_busy(lambda: read_capital_accounts(self.store), stop_event)
        if capital is None:
            return None
        return {"tasks":results,"capital":capital,"live_authorized":False,
                "execution_enabled":False}

    def _retry_busy(self, operation, stop_event=None):
        deadline = time.monotonic() + min(1.0, self.policy.interval_seconds)
        max_wait = min(0.25, self.policy.interval_seconds / 4)
        delay = 0.025
        while stop_event is None or not stop_event.is_set():
            try:
                with self.store._bounded_lock_wait(seconds=max_wait, deadline=deadline):
                    return operation()
            except sqlite3.OperationalError as exc:
                remaining = deadline - time.monotonic()
                if not _transient_sqlite_lock(exc) or remaining <= 0:
                    raise
                wait = min(delay, remaining)
                if stop_event is None:
                    time.sleep(wait)
                elif stop_event.wait(wait):
                    return None
                if time.monotonic() >= deadline:
                    raise
                delay *= 2
        return None

    def run(self,stop_event,*,max_cycles=None):
        if max_cycles is not None and (type(max_cycles) is not int or max_cycles<1):
            raise ValueError("invalid cycle budget")
        if self._retry_busy(self.acquire, stop_event) is None:
            return 0
        count=0
        try:
            while not stop_event.is_set():
                if self.cycle(stop_event=stop_event) is None:
                    break
                count+=1
                if max_cycles is not None and count>=max_cycles:break
                # Event wait permits immediate controlled shutdown without spin.
                stop_event.wait(self.policy.interval_seconds)
        finally:
            active_error = sys.exception()
            try:
                self._retry_busy(self.stop)
            except AuthorityLost:
                pass
            except sqlite3.Error as cleanup_error:
                if active_error is None:
                    raise
                active_error.add_note(f"supervisor shutdown SQLite error: {cleanup_error}")
        return count

def read_supervisor_status(store,*,now=None):
    result={"status":"NOT_STARTED","authority":"NONE","radars":{},
        "alerts":[],"live_authorized":False,"execution_enabled":False,
        "autonomy_24h_verified":False,"scope":"OFFLINE_ARCHIVE"}
    if not isinstance(store,SQLiteEventStore):return result
    try:
        with store._connection_scope() as conn,conn:
            conn.execute("BEGIN")
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm36_supervisor_lease'").fetchone():return result
            lease=_lease(conn)
            clock=_number(time.time() if now is None else now)
            if lease:
                generation,owner,heartbeat,expires,status=lease
                result.update(generation=generation,last_heartbeat=_stamp(heartbeat).isoformat(),
                    expires_at=_stamp(expires).isoformat(),status=("STOPPED" if status=="STOPPED" else
                    "CLOCK_CONFLICT" if clock<heartbeat else "EXPIRED" if clock>=expires else "ACTIVE"),
                    authority="GENERATION_FENCED")
            for r in RADARS:
                result["radars"][r]=_task(conn,r)
            for aid,payload,digest in conn.execute("SELECT id,payload,payload_sha FROM cm36_supervisor_alerts ORDER BY rowid DESC LIMIT 50"):
                item=_verify_record((payload,digest))
                if item["id"]!=aid:raise ValueError("alert identity conflict")
                result["alerts"].append(item)
    except (ValueError,TypeError,KeyError,ArithmeticError,AuthorityLost,sqlite3.Error):
        result.update(status="CONFLICTED",radars={},alerts=[])
    return result
