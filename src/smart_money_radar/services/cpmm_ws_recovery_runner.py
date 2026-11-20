"""Single-receiver, bounded CPMM WebSocket recovery with existing RAW journal.

The caller supplies WebSocket and RPC transports (real or deterministic fake).
One connection -> one SQLiteGeyserRawStore session/ordering domain -> four fresh
subscriptions -> one fresh RPC baseline. A gap is never closed by reconnecting.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime,timezone
from hashlib import sha256
import json
import time
import uuid
from typing import Callable

from smart_money_radar.services.cpmm_ws_recovery import BoundedCpmmRecovery
from smart_money_radar.services.cpmm_ws_resilience import (
    disconnect_record,WsResiliencePolicy,
)
from smart_money_radar.services.cpmm_ws_baseline_bridge import inspect_contemporaneous_baseline


class CpmmRecoveryRunner:
    def __init__(self, recovery:BoundedCpmmRecovery, *,
                 ws_connect, rpc_fetch, snapshot_identity:dict,
                 duration_seconds:float=75., max_frames:int=80,
                 sleep=asyncio.sleep, clock=time.monotonic,
                 now=lambda:datetime.now(timezone.utc)):
        if not 1<=duration_seconds<=600 or not 4<=max_frames<=1000:
            raise ValueError("bounded session required")
        self.recovery=recovery
        self.ws_connect=ws_connect
        self.rpc_fetch=rpc_fetch
        self.snapshot_identity=dict(snapshot_identity)
        self.duration_seconds=duration_seconds
        self.max_frames=max_frames
        self.sleep=sleep
        self.clock=clock
        self.now=now
        self.manifest={"schema":"smr.cpmm.ws-recovery.v1",
            "coverage":"UNKNOWN","financial_execution_authorized":False,
            "global_order_proven":False,"continuous_delivery_proven":False,
            "recovery_live_proven":False,"connections":[],"gaps":[],
            "rpc_baseline_calls":0,"stop_reason":None,
            "live_real_reconnection_observed":False,
            "all_raw_frames_in_sqlite":True,
            "backfill_or_continuity_proven":False}

    async def run(self)->dict:
        deadline=self.clock()+self.duration_seconds
        source=self.recovery.source_id
        owner_id=str(uuid.uuid4())
        # Recovery and exclusive ownership are a single SQLite transaction.
        self.manifest["recovered_incomplete_session_ids"] = (
            self.recovery.store.recover_incomplete_capture_sessions(
                source_id=source,owner_id=owner_id))
        prev_failure=None
        failure_phase="connect"
        try:
            while self.clock()<deadline and len(self.manifest["connections"])<=self.recovery.policy.max_reconnects:
                if prev_failure is not None:
                    if not self.recovery.can_retry():
                        self.manifest["stop_reason"]="reconnect_budget_exhausted"
                        break
                    delay=self.recovery.policy.backoff(
                        self.recovery.reconnect_attempts+1,seed=prev_failure.previous_session_id)
                    if self.clock()+delay>=deadline:
                        self.manifest["stop_reason"]="deadline_before_reconnect"
                        break
                    await self.sleep(delay)
                session=self.recovery.new_connection(recovered_from=prev_failure)
                scope=session.session_id
                report={"session_id":scope,"previous_session_id":
                        prev_failure.previous_session_id if prev_failure else None,
                        "subscriptions_acknowledged":0,"frames":0,
                        "baseline_attempts":0,"baseline_status":"UNKNOWN",
                        "baseline_slot":None,"notifications":0,"error":None,
                        "coverage":"UNKNOWN","baseline_after_reconnect":bool(prev_failure),
                        "new_ordering_domain":scope}
                self.manifest["connections"].append(report)
                raw_notifications=[]
                baseline_task=None
                report["websocket_requests"]=[]
                report["wire_raw_frames_sha256"]=[]
                report["rpc_baseline_request_raw"]=None
                report["rpc_baseline_response_raw"]=None
                connection_healthy=False
                failure_phase="connect"
                failure_record=None
                try:
                    async with self.ws_connect() as ws:
                        failure_phase="subscribe"
                        expected={}
                        for i,account in enumerate(self.recovery.accounts,1):
                            request=json.dumps({"jsonrpc":"2.0","id":i,
                                "method":"accountSubscribe","params":[account,{
                                "encoding":"base64","commitment":"finalized"}]},
                                sort_keys=True,separators=(",",":")).encode()
                            expected[i]=account
                            report["websocket_requests"].append(request.decode())
                            await ws.send(request.decode())
                        while self.clock()<deadline and report["frames"]<self.max_frames:
                            if len(session.subscription_accounts)==4 and baseline_task is None:
                                if self.manifest["rpc_baseline_calls"]>=1+self.recovery.policy.max_reconnects:
                                    raise RuntimeError("rpc_baseline_budget_exhausted")
                                failure_phase="baseline"
                                req=json.dumps({"jsonrpc":"2.0","id":23,
                                    "method":"getMultipleAccounts","params":[
                                    list(self.recovery.accounts),{
                                    "encoding":"base64","commitment":"finalized"}]},
                                    sort_keys=True,separators=(",",":")).encode()
                                report["baseline_request_sha256"]=sha256(req).hexdigest()
                                report["rpc_baseline_request_raw"]=req.decode()
                                report["baseline_attempts"]=1
                                failure_phase="persist"
                                session._record(req,"solana_rpc_baseline_request")
                                failure_phase="baseline"
                                self.manifest["rpc_baseline_calls"]+=1
                                baseline_task=asyncio.create_task(self.rpc_fetch(req))
                                # Let the baseline request enter its coroutine before
                                # the next WS receive can immediately disconnect.
                                await asyncio.sleep(0)
                            failure_phase="receive"
                            try:
                                message=await asyncio.wait_for(ws.recv(),
                                    timeout=min(self.recovery.policy.read_timeout_seconds,
                                                max(.01,deadline-self.clock())))
                            except asyncio.TimeoutError:
                                # A silent but live connection has no new ledger evidence.
                                continue
                            if not isinstance(message,str):
                                raise ValueError("nontext_frame")
                            raw=message.encode()
                            if len(raw)>1_000_000:raise ValueError("oversized_frame")
                            # Journal FIRST. Rejecting or conflicting frames cannot be processed.
                            parsed=json.loads(raw)
                            if type(parsed) is not dict:raise ValueError("nonobject_frame")
                            when=self.now()
                            failure_phase="persist"
                            if type(parsed.get("id")) is int:
                                req_id=parsed["id"]
                                acc=expected.get(req_id)
                                sub=parsed.get("result")
                                session._record(raw,"solana_ws_subscription_ack")
                                failure_phase="subscribe"
                                report["wire_raw_frames_sha256"].append(sha256(raw).hexdigest())
                                report["frames"]+=1
                                if acc is None or type(sub) is not int:
                                    raise ValueError("subscription_ack_invalid")
                                session.register_subscription(sub,acc)
                                report["subscriptions_acknowledged"]+=1
                            else:
                                observation=session.process_frame(raw,received_at=when)
                                report["wire_raw_frames_sha256"].append(sha256(raw).hexdigest())
                                report["frames"]+=1
                                if observation:
                                    raw_notifications.append((observation,raw))
                                    report["notifications"]+=1
                            failure_phase="receive"
                            if baseline_task and baseline_task.done():
                                try:
                                    if baseline_task.cancelled():
                                        raise RuntimeError("rpc_baseline_cancelled")
                                    rpc_result=baseline_task.result()
                                    if (not isinstance(rpc_result,tuple) or
                                        len(rpc_result)!=4 or rpc_result[3] is not None):
                                        raise RuntimeError("rpc_baseline_unavailable")
                                except Exception as exc:
                                    failure_phase="baseline"
                                    raise RuntimeError("rpc_baseline_failed") from exc
                            if report["notifications"] and baseline_task and baseline_task.done():
                                break
                        connection_healthy=True
                except asyncio.CancelledError:
                    self.manifest["stop_reason"]="operator_cancelled"
                    self.recovery.finalize("cancelled")
                    raise
                except Exception as exc:
                    err=disconnect_record(session_id=session.session_id,exc=exc,
                        phase=failure_phase,frames=session.next_local_sequence,when=self.now())
                    report["error"]={"type":err.error_type,"phase":err.phase,
                        "message":err.error_message,"classification":err.failure}
                    self.manifest["gaps"].append(err.__dict__)
                    if err.failure=="PERSISTENCE_FAILED":
                        self.manifest["all_raw_frames_in_sqlite"]=False
                    # Keep the originating journal open just long enough to
                    # archive a completed RPC result. Never validate on disconnect.
                    failure_record=err
                    prev_failure=err
                finally:
                    if baseline_task is not None:
                        # Never wait indefinitely for an RPC after WS disconnect.
                        # The result remains bound to this originating session.
                        try:
                            # Bounded drain: late RPC bytes still belong to this
                            # journal, not to the next WebSocket session.
                            requested,available,response,error=await asyncio.wait_for(
                                baseline_task,timeout=max(0.01,min(
                                    0.25 if failure_record is not None else 11.,
                                    deadline-self.clock())))
                            report["baseline_requested_at"]=requested.isoformat()
                            report["baseline_available_at"]=available.isoformat()
                            report["baseline_rpc_error"]=error
                            if response is not None:
                                if not isinstance(response,bytes):
                                    raise ValueError("rpc_response_not_bytes")
                                # Persist the exact response while this session remains active.
                                # A late response from an old or closed socket is not eligible.
                                if session.active:
                                    failure_phase="persist"
                                    session._record(response,"solana_rpc_baseline_response")
                                    failure_phase="baseline"
                                else:
                                    report["baseline_rejection"]="origin_session_closed"
                                report["baseline_response_sha256"]=sha256(response).hexdigest()
                                report["rpc_baseline_response_raw"]=response.decode()
                                if not session.active:
                                    raise ValueError("baseline_origin_session_not_active")
                                if failure_record is not None:
                                    report["baseline_rejection"]="websocket_disconnected"
                                    raise ValueError("baseline_ws_session_disconnected")
                                if available>self.now():
                                    raise ValueError("rpc_baseline_after_cutoff")
                                if error is not None:
                                    raise ValueError("rpc_baseline_transport_error")
                                if self.clock()>=deadline:
                                    report["baseline_rejection"]="global_deadline_elapsed"
                                    raise ValueError("rpc_baseline_global_deadline")
                                try:
                                    body=json.loads(response)
                                    candidate_slot=body["result"]["context"]["slot"]
                                except (ValueError,TypeError,KeyError,IndexError):
                                    candidate_slot=None
                                if type(candidate_slot) is int:
                                    reference_slot=self.snapshot_identity["original_swap_slot"]
                                    prior_slots=[item["baseline_slot"]
                                        for item in self.manifest["connections"][:-1]
                                        if item.get("baseline_verified_as_snapshot") is True
                                        and type(item.get("baseline_slot")) is int]
                                    if (candidate_slot<reference_slot or
                                        prior_slots and candidate_slot<max(prior_slots)):
                                        report["baseline_rejection"]="regressive_rpc_slot"
                                        raise ValueError("rpc_baseline_regressive_slot")
                                audit=inspect_contemporaneous_baseline(
                                    session=session,request_raw=req,response_raw=response,
                                    requested_at=requested,available_at=available,
                                    endpoint=self.snapshot_identity["endpoint"],
                                    original_swap_slot=self.snapshot_identity["original_swap_slot"],
                                    authority=self.snapshot_identity["authority"],
                                    input_mint=self.snapshot_identity["input_mint"],
                                    output_mint=self.snapshot_identity["output_mint"],
                                    input_token_program=self.snapshot_identity["input_token_program"],
                                    output_token_program=self.snapshot_identity["output_token_program"],
                                    notifications=tuple(raw_notifications),cutoff=self.now())
                                report["baseline_status"]=audit.baseline_status
                                report["baseline_slot"]=audit.baseline_slot
                                report["baseline_verified_as_snapshot"]=audit.baseline_validated_as_snapshot
                                report["notification_relationships"]=[
                                    a.relationship for a in audit.account_observations]
                        except asyncio.CancelledError:
                            report["baseline_error"]="CancelledError"
                        except asyncio.TimeoutError:
                            report["baseline_error"]="RPC_TIMEOUT"
                        except Exception as exc:
                            report["baseline_error"]=type(exc).__name__
                            if failure_phase=="persist":
                                self.manifest["all_raw_frames_in_sqlite"]=False
                                report["persistence_error"]=type(exc).__name__
                                self.manifest["stop_reason"]="persistence_failed_no_retry"
                                connection_healthy=False
                        if report.get("baseline_error") or report.get("baseline_rpc_error"):
                            report["baseline_status"]="UNKNOWN"
                            report["baseline_verified_as_snapshot"]=False
                        if baseline_task.done() and baseline_task.cancelled():
                            report.setdefault("baseline_error","CancelledError")
                    if failure_record is not None and session.active:
                        self.recovery.note_failure(failure_record)
                    elif session.active and connection_healthy:
                        session.finish("bounded_end")
                    elif session.active:
                        session.finish("interrupted_unknown")
                    report["journal"]=self.recovery.store.get_capture_session(source,scope)
                    report["journal_verified"]=None
                    try:
                        report["journal_verified"]=self.recovery.store.verify_wire_session(
                            source,scope,scope)
                    except ValueError:
                        report["journal_error"]="tainted_or_interrupted"
                    report["coverage"]="UNKNOWN"
                    report["notification_signatures_attested"]=False
                if self.manifest["stop_reason"]=="persistence_failed_no_retry":
                    break
                if connection_healthy:
                    self.manifest["stop_reason"]="bounded_session_end"
                    break
                if report["error"] and report["error"]["classification"]=="PERSISTENCE_FAILED":
                    self.manifest["stop_reason"]="persistence_failed_no_retry"
                    break
            if self.manifest["stop_reason"] is None:
                self.manifest["stop_reason"]=(
                    "reconnect_budget_exhausted" if
                    len(self.manifest["connections"])>=1+self.recovery.policy.max_reconnects
                    and bool(self.manifest["gaps"])
                    else "retry_or_deadline_exhausted")
            return self.manifest
        finally:
            try:
                self.recovery.finalize("runner_end")
            finally:
                self.recovery.store.release_capture_source_lease(
                    source_id=source,owner_id=owner_id)
