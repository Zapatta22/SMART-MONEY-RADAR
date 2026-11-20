"""One-shot WebSocket + exactly one getMultipleAccounts baseline RPC request.

The WebSocket receiver is the only task that calls ws.recv(); it persists raw
frames before processing them. Baseline RPC executes in a separate task while
WebSocket notifications remain actively received/archived. No Geyser claim.
"""
from __future__ import annotations
import asyncio,base64,json,time,uuid
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession
from smart_money_radar.services.cpmm_ws_baseline_bridge import inspect_contemporaneous_baseline
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps

ROOT=Path("data/evidence/mainnet/2026-11-20")
OUT=Path("/tmp/smr-cpmm-baseline-live")
WS_ENDPOINT="wss://api.mainnet-beta.solana.com/"
RPC_ENDPOINT="https://api.mainnet-beta.solana.com"
MAX_SECONDS=40
MAX_FRAMES=80
ACCOUNTS=(
 "CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu",
 "D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2",
 "C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU",
 "8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG",
)

def utcnow():return datetime.now(timezone.utc)

def rpc_once(request_raw:bytes):
    requested=utcnow()
    response=None
    failure=None
    try:
        req=Request(RPC_ENDPOINT,data=request_raw,
                    headers={"Content-Type":"application/json"},method="POST")
        with urlopen(req,timeout=11) as conn:
            response=conn.read(2_000_001)
        if len(response)>2_000_000:
            response=None
            failure="response_above_limit"
    except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
        failure=type(exc).__name__
    return requested,utcnow(),response,failure

async def run():
    import websockets
    OUT.mkdir(parents=True,exist_ok=True)
    previous=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
    original=(ROOT/previous["raw_file"]).read_bytes()
    assert sha256(original).hexdigest()==previous["raw_sha256"]
    swap=[x for x in decode_raydium_cpmm_swaps(json.loads(original))
          if x.accounts.pool_state==ACCOUNTS[0]]
    assert len(swap)==1
    accounts=swap[0].accounts
    assert (accounts.pool_state,accounts.amm_config,
            accounts.input_vault,accounts.output_vault)==ACCOUNTS
    rpc_request=json.dumps({"jsonrpc":"2.0","id":23,"method":"getMultipleAccounts",
                 "params":[list(ACCOUNTS),{"commitment":"finalized","encoding":"base64"}]},
                sort_keys=True,separators=(",",":")).encode()
    (OUT/"baseline.request.raw.json").write_bytes(rpc_request)
    store=SQLiteGeyserRawStore(OUT/"geyser-raw.sqlite")
    sid="solana-ws-baseline-"+str(uuid.uuid4())
    session=PublicCpmmWsSession(store,source_id="solana-ws-public-mainnet",
                                 session_id=sid,accounts=ACCOUNTS)
    session.start()
    start=utcnow()
    deadline=time.monotonic()+MAX_SECONDS
    notifications=[]
    request_accounts={}
    for i,a in enumerate(ACCOUNTS):
        payload=json.dumps({"jsonrpc":"2.0","id":i+1,"method":"accountSubscribe",
                    "params":[a,{"encoding":"base64","commitment":"finalized"}]},
                    sort_keys=True,separators=(",",":")).encode()
        (OUT/f"ws-request-{i+1}.raw.json").write_bytes(payload)
        request_accounts[i+1]=a
    result={"schema":"smr.cpmm.ws-baseline.v1","endpoint_ws":WS_ENDPOINT,
        "endpoint_rpc":RPC_ENDPOINT,"started_at":start.isoformat(),
        "max_duration_seconds":MAX_SECONDS,"max_frames":MAX_FRAMES,
        "accounts":list(ACCOUNTS),"subscriptions_requested":4,
        "subscriptions_acknowledged":0,"notifications_received":0,
        "frames_received":0,"baseline_rpc_attempts":0,"baseline_status":"UNKNOWN",
        "baseline_slot":None,"baseline_requested_at":None,"baseline_available_at":None,
        "baseline_response_sha256":None,
        "baseline_request_sha256":sha256(rpc_request).hexdigest(),
        "coverage":"UNKNOWN","race_window_closed":False,
        "global_ledger_order_verified":False,"delivery_continuity_attested":False,
        "financial_execution_authorized":False,"error":None,"status":"UNKNOWN"}
    outcome="ended"
    task=None
    try:
        async with websockets.connect(WS_ENDPOINT,open_timeout=8,close_timeout=2,
                        max_size=1_000_000,ping_interval=None) as ws:
            for i in range(1,5):
                await ws.send((OUT/f"ws-request-{i}.raw.json").read_bytes().decode())
            while time.monotonic()<deadline and result["frames_received"]<MAX_FRAMES:
                if result["subscriptions_acknowledged"]==4 and task is None:
                    result["baseline_rpc_attempts"]=1
                    task=asyncio.create_task(asyncio.to_thread(rpc_once,rpc_request))
                try:
                    rawmessage=await asyncio.wait_for(ws.recv(),
                        timeout=min(2,max(.01,deadline-time.monotonic())))
                except asyncio.TimeoutError:
                    continue
                if not isinstance(rawmessage,str):
                    session.gaps.append("unexpected_binary_ws")
                    continue
                raw=rawmessage.encode("utf-8")
                if len(raw)>1_000_000:
                    session.gaps.append("oversized_ws_payload")
                    continue
                index=result["frames_received"]
                (OUT/f"frame-{index:03d}.raw.json").write_bytes(raw)
                result["frames_received"]+=1
                now=utcnow()
                try:j=json.loads(raw)
                except ValueError:
                    session.process_frame(raw,received_at=now)
                    continue
                if isinstance(j,dict) and type(j.get("id")) is int:
                    account=request_accounts.get(j["id"])
                    sub=j.get("result")
                    if account is not None and type(sub) is int:
                        session.register_subscription(sub,account)
                        result["subscriptions_acknowledged"]+=1
                    else:
                        session.gaps.append("subscription_reply_invalid")
                    session._record(raw,"solana_ws_subscription_ack")
                else:
                    observation=session.process_frame(raw,received_at=now)
                    if observation:
                        result["notifications_received"]+=1
                        notifications.append((observation,raw))
                        print("SMR_BASELINE_WS notification_account="+observation.account+
                              " slot="+str(observation.slot))
            outcome="completed_bounded"
            result["status"]="SESSION_COMPLETE_BOUND"
    except Exception as exc:
        result["error"]=type(exc).__name__
        result["status"]="NETWORK_OR_WS_ERROR"
        outcome="interrupted"
        session.mark_disconnect()
    finally:
        # Always finish any in-flight baseline RPC before finalizing the
        # manifest, without assuming its result proves stream continuity.
        if task is not None:
            requested,available,raw,error=await task
            result["baseline_requested_at"]=requested.isoformat()
            result["baseline_available_at"]=available.isoformat()
            result["baseline_rpc_error"]=error
            if raw is not None:
                (OUT/"baseline.response.raw.json").write_bytes(raw)
                result["baseline_response_sha256"]=sha256(raw).hexdigest()
                try:
                    report=inspect_contemporaneous_baseline(
                      session=session,response_raw=raw,request_raw=rpc_request,
                      requested_at=requested,available_at=available,
                      endpoint=RPC_ENDPOINT,original_swap_slot=previous["slot_observed"],
                      authority=accounts.authority,
                      input_mint=accounts.input_token_mint,
                      output_mint=accounts.output_token_mint,
                      input_token_program=accounts.input_token_program,
                      output_token_program=accounts.output_token_program,
                      notifications=tuple(notifications),cutoff=utcnow())
                    result["baseline_status"]=report.baseline_status
                    result["baseline_slot"]=report.baseline_slot
                    result["coverage"]=report.coverage
                    result["baseline_validated_as_snapshot"]=report.baseline_validated_as_snapshot
                    result["notification_comparison"]=[
                        {**z.__dict__,"reasons":list(z.reasons)} for z in report.account_observations]
                    result["audit_reasons"]=list(report.reasons)
                except (ValueError,TypeError,KeyError,IndexError) as exc:
                    result["audit_error"]=type(exc).__name__
        else:
            result["audit_reasons"]=["subscriptions_not_all_acknowledged"]
        result["session_frames_stored"]=session.finish(outcome)
        result["session_report"]=session.report()
        result["journal_integrity"]=store.integrity_check()
        result["journal_report"]=store.verify_wire_session(
            session.source_id,session.session_id,session.session_id)
        store.close()
    result["ended_at"]=utcnow().isoformat()
    result["duration_seconds"]=(datetime.fromisoformat(result["ended_at"])-start).total_seconds()
    if result["session_frames_stored"]!=result["session_report"]["frames_archived"]:
        raise ValueError("journal frame count mismatch")
    (OUT/"manifest.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    for k in ("subscriptions_acknowledged","notifications_received",
              "baseline_rpc_attempts","baseline_slot","baseline_status",
              "coverage","session_frames_stored"):
        print("SMR_BASELINE_WS "+k+"="+str(result.get(k)))
    print("SMR_BASELINE_WS finance_enabled=False")

if __name__=="__main__":
    asyncio.run(run())
