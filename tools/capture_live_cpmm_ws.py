"""One-off bounded public Solana WebSocket CPMM capture.

Only accountSubscribe on the exact four scoped addresses. Connection-local
receipt ordering is persisted to the existing Geyser RAW SQLite journal but
is not ledger write_version or proof of complete coverage. Failure/zero
notifications are real observations, not simulated successes.
"""
from __future__ import annotations
import asyncio
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import time
import uuid

from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

ADDRESSES=(
 "CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu",
 "D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2",
 "C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU",
 "8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG",
)
ENDPOINT="wss://api.mainnet-beta.solana.com/"
OUT=Path("/tmp/smr-cpmm-ws-live")
DURATION_SECONDS=35

async def capture()->None:
    import websockets
    OUT.mkdir(parents=True,exist_ok=True)
    db=OUT/"geyser-raw.sqlite"
    session_id="solana-accountsubscribe-"+str(uuid.uuid4())
    store=SQLiteGeyserRawStore(db)
    session=PublicCpmmWsSession(store,source_id="solana-ws-public-mainnet",
                                session_id=session_id,accounts=ADDRESSES)
    session.start()
    started=datetime.now(timezone.utc)
    requests={}
    for i,a in enumerate(ADDRESSES):
        request={"jsonrpc":"2.0","id":i+1,"method":"accountSubscribe",
                 "params":[a,{"encoding":"base64","commitment":"finalized"}]}
        requests[i+1]=a
        (OUT/("request-"+str(i+1)+".raw.json")).write_bytes(
            json.dumps(request,separators=(",",":"),sort_keys=True).encode())
    stats={"endpoint":ENDPOINT,"accounts":list(ADDRESSES),"started_at":started.isoformat(),
           "max_duration_seconds":DURATION_SECONDS,"requests_prepared":4,
           "attempted_connections":1,"received_raw_frames":0,
           "subscriptions_acknowledged":0,"notifications_received":0,
           "baseline_validated":False,"provider_independently_authenticated":False,
           "global_order_verified":False,"coverage":"UNKNOWN",
           "economic_execution_authorized":False,
           "status":"UNKNOWN","error":None}
    deadline=time.monotonic()+DURATION_SECONDS
    outcome="stopped"
    try:
        async with websockets.connect(ENDPOINT,open_timeout=8,close_timeout=2,
                                      max_size=1_000_000,ping_interval=None) as ws:
            for i in range(1,5):
                await ws.send((OUT/("request-"+str(i)+".raw.json")).read_bytes().decode())
            while time.monotonic()<deadline and stats["received_raw_frames"]<60:
                remaining=deadline-time.monotonic()
                try:
                    message=await asyncio.wait_for(ws.recv(),timeout=min(6,max(.01,remaining)))
                except asyncio.TimeoutError:
                    continue
                if not isinstance(message,str):
                    session.gaps.append("binary_unexpected")
                    continue
                raw=message.encode()
                if len(raw)>1_000_000:
                    session.gaps.append("oversize_websocket_frame")
                    continue
                when=datetime.now(timezone.utc)
                index=stats["received_raw_frames"]
                (OUT/("frame-"+f"{index:03d}"+".raw.json")).write_bytes(raw)
                stats["received_raw_frames"]+=1
                try:parsed=json.loads(raw)
                except ValueError:
                    session.process_frame(raw,received_at=when)
                    continue
                if isinstance(parsed,dict) and type(parsed.get("id")) is int:
                    req_id=parsed["id"]
                    account=requests.get(req_id)
                    sub=parsed.get("result")
                    if account is not None and type(sub) is int:
                        session.register_subscription(sub,account)
                        stats["subscriptions_acknowledged"]+=1
                    else:
                        session.gaps.append("subscription_error_or_invalid_ack")
                    session._record(raw,"solana_ws_subscription_ack")
                else:
                    o=session.process_frame(raw,received_at=when)
                    if o is not None:
                        stats["notifications_received"]+=1
                        print("SMR_WS_REAL account="+o.account+" slot="+str(o.slot)+
                              " raw_sha256="+o.raw_sha256+" status="+o.status)
            outcome="finished_bounded_session"
            stats["status"]="OBSERVED_NOTIFICATIONS" if stats["notifications_received"] else "NO_NOTIFICATIONS_OBSERVED"
    except Exception as exc:
        outcome="network_or_provider_failure"
        stats["error"]=type(exc).__name__
        session.mark_disconnect()
    finally:
        try:
            stats["frames_stored"]=session.finish(outcome)
            stats["journal_integrity"]=store.integrity_check()
            stats["journal_frame_report"]=store.verify_wire_session(
                session.source_id,session.session_id,session.session_id)
        finally:
            store.close()
    stats["ended_at"]=datetime.now(timezone.utc).isoformat()
    stats["duration_seconds"]=(datetime.fromisoformat(stats["ended_at"])-started).total_seconds()
    stats["session"]=session.report()
    if stats["frames_stored"]!=session.next_local_sequence:
        raise RuntimeError("journal and delivery sequence disagree")
    (OUT/"manifest.json").write_text(json.dumps(stats,indent=2,sort_keys=True)+"\n")
    print("SMR_WS status="+stats["status"])
    print("SMR_WS subscription_acks="+str(stats["subscriptions_acknowledged"]))
    print("SMR_WS real_notifications="+str(stats["notifications_received"]))
    print("SMR_WS frames_stored="+str(stats["frames_stored"]))
    print("SMR_WS coverage=UNKNOWN")
    print("SMR_WS economic_execution_authorized=False")

if __name__=="__main__":
    asyncio.run(capture())
