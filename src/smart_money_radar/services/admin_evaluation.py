"""CM37D: isolated, in-process operational command evaluation.

The isolated evaluation HTTP adapter may import this module. The caller must create a new private
evaluation directory. Existing production databases cannot be supplied.
The existing local control journal remains the source of truth.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
from smart_money_radar.services.admin_security import AdminSecurity
from smart_money_radar.services.operational_controls import LocalOperationalControls, read_operational_status
from smart_money_radar.storage.event_store import SQLiteEventStore


class IsolatedAdminEvaluation:
    def __init__(self,root,*,password,clock):
        self.root=Path(root)
        # Fail if the directory exists; no arbitrary DB path accepted.
        self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        self.security=AdminSecurity.provision(self.root/"admin.sqlite",password,clock=clock)
        self.store=SQLiteEventStore(self.root/"evaluation.sqlite")
        # Admin capability stays in memory and is not a financial signing key.
        self._capability=secrets.token_bytes(32)
        self._controls=LocalOperationalControls(self.store,operator_capability=self._capability)
        self._clock=clock

    def login(self,password):
        return self.security.login(password)

    def confirm(self,*args,**kwargs):
        return self.security.confirm(*args,**kwargs)

    def execute(self,token,csrf,*,request_id,action,radar=None,confirmation=None,policy=None):
        """Consume authorization once, use the established control transition.

        Authorization and operational journals are distinct files. A crash
        after consuming the receipt cannot cause automatic retry or duplicate
        execution. Query the actual local journal to resolve the outcome.
        """
        receipt=self.security.authorize(token,csrf,request_id=request_id,action=action,
            radar=radar,confirmation=confirmation,policy=policy)
        event_id="cm37-eval-"+hashlib.sha256(request_id.encode()).hexdigest()
        at=datetime.fromtimestamp(self._clock(),timezone.utc)
        try:
            if action in ("CAPITAL_CREATE","CAPITAL_POLICY"):
                from smart_money_radar.services.admin_capital_policy import apply_capital_command
                state=apply_capital_command(self.store,action,policy,event_id,at)
                return {"event_id":event_id,"request_id":request_id,"status":"APPLIED","executed":True,"state":state,"remote_writes_enabled":False}
            state=self._controls.apply(capability=self._capability,event_id=event_id,
                action=receipt["action"],radar=receipt["radar"],actor="admin-evaluation",
                at=at,reason="isolated authenticated command")
        except (ValueError,PermissionError,sqlite3.Error):
            # Record that execution was rejected, never claim a transition.
            return {"event_id":event_id,"request_id":request_id,"status":"REJECTED_OR_UNKNOWN",
                    "executed":False,"state":read_operational_status(self.store),
                    "remote_writes_enabled":False}
        return {"event_id":event_id,"request_id":request_id,"status":"APPLIED",
                "executed":True,"state":state,"remote_writes_enabled":False}

    def outcome(self,request_id):
        """Read the existing journal; missing event is unknown, not success."""
        eid="cm37-eval-"+hashlib.sha256(request_id.encode()).hexdigest()
        from smart_money_radar.services.operational_controls import _load
        with self.store._connection_scope() as conn:
            conn.execute("BEGIN")
            state,events,_=_load(conn)
            event=next((e for e in events if e["id"]==eid),None)
            if event is None:
                from smart_money_radar.services.admin_capital_policy import read_capital_command
                event=read_capital_command(conn,eid)
            return {"status":"APPLIED" if event else "NO_COMMITTED_TRANSITION",
                    "event":event,"state":state,"remote_writes_enabled":False}

    def close(self):
        self.store.close()
