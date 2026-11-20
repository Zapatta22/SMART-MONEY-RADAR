"""Deterministic WebSocket transport state across bounded reconnections.

Every connection creates a distinct existing PublicCpmmWsSession and journal
ordering domain. Recovery never reuses a finalized stream or treats an ACK as
proof of historical account-write continuity.
"""
from __future__ import annotations

from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
import json
import os
import uuid

from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession
from smart_money_radar.services.cpmm_ws_resilience import (
    DisconnectRecord, WsResiliencePolicy, reconnection_is_new_observation,
)
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore


class BoundedCpmmRecovery:
    def __init__(self,store:SQLiteGeyserRawStore,*,source_id:str,
                 accounts:tuple[str,str,str,str],
                 policy:WsResiliencePolicy|None=None):
        self.store=store
        self.source_id=source_id
        self.accounts=accounts
        self.policy=policy or WsResiliencePolicy()
        self.interrupted_sessions=self.store.recover_interrupted_capture_sessions(self.source_id)
        self.sessions:list[PublicCpmmWsSession]=[]
        self.disconnects:list[DisconnectRecord]=[]
        self.reconnect_attempts=0
        self.current=None
        self.total_notifications=0
        self.coverage="UNKNOWN"

    def new_connection(self,*,recovered_from:DisconnectRecord|None=None,
                       new_session_id:str|None=None)->PublicCpmmWsSession:
        if self.current is not None and self.current.active:
            raise ValueError("previous transport must finish before reconnect")
        if self.sessions:
            if recovered_from is None or not self.disconnects or recovered_from!=self.disconnects[-1]:
                raise ValueError("missing persisted failure identity")
            if self.reconnect_attempts>=self.policy.max_reconnects:
                raise ValueError("reconnect budget exhausted")
        sid=new_session_id or "solana-recovery-"+str(uuid.uuid4())
        if self.sessions and sid==self.sessions[-1].session_id:
            raise ValueError("reconnect requires fresh ordering domain")
        s=PublicCpmmWsSession(self.store,source_id=self.source_id,
                               session_id=sid,accounts=self.accounts)
        s.start()
        self.current=s
        self.sessions.append(s)
        if len(self.sessions)>1:
            self.reconnect_attempts+=1
            self.coverage="UNKNOWN"
        return s

    def note_failure(self,record:DisconnectRecord)->None:
        if self.current is None or record.previous_session_id!=self.current.session_id:
            raise ValueError("failure does not match active transport")
        if not self.current.active:
            raise ValueError("transport not active")
        self.current.mark_disconnect()
        self.store.append_capture_gap(self.source_id,self.current.session_id,record.failure)
        self.current.finish(record.failure)
        self.disconnects.append(record)
        self.coverage="UNKNOWN"


    def classify_failed_transport(self,*,record:DisconnectRecord)->None:
        """Close current journal only after its RAW deliveries are durable."""
        self.note_failure(record)

    def can_retry(self)->bool:
        return bool(self.disconnects) and self.reconnect_attempts < self.policy.max_reconnects

    def finalize(self,outcome:str)->None:
        if self.current is not None and self.current.active:
            self.current.finish(outcome)
        self.coverage="UNKNOWN"

    def recovery_ready(self)->bool:
        if not self.sessions:
            return False
        current=self.sessions[-1]
        if len(self.sessions)==1:
            return False
        return reconnection_is_new_observation(
            previous_session_id=self.sessions[-2].session_id,
            new_session_id=current.session_id,
            acked_accounts=len(current.subscription_accounts),
            baseline_verified=False,  # validated baseline alone cannot attest continuity
            previous_gap=self.disconnects[-1])

    def report(self)->dict:
        return {
            "coverage":"UNKNOWN",
            "account_stream_continuous":False,
            "economic_execution_authorized":False,
            "reconnect_attempts":self.reconnect_attempts,
            "interrupted_sessions_recovered":list(self.interrupted_sessions),
            "session_ids":[s.session_id for s in self.sessions],
            "session_reports":[s.report() for s in self.sessions],
            "disconnections":[asdict(d) for d in self.disconnects],
            "total_notifications":sum(len(s.observations) for s in self.sessions),
            "initial_session_baseline_verified":False,
            "checkpoint_proves_ledger_coverage":False,
        }
