"""One-shot WebSocket + exactly one getMultipleAccounts baseline RPC request.

The WebSocket receiver is the only task that calls ws.recv(); it persists raw
frames before processing them. Baseline RPC executes in a separate task while
WebSocket notifications remain actively received/archived. No Geyser claim.
"""
from __future__ import annotations
import asyncio,base64,json,time,uuid,os
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession
from smart_money_radar.services.cpmm_ws_baseline_bridge import inspect_contemporaneous_baseline
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.services.cpmm_ws_recovery import BoundedCpmmRecovery
from smart_money_radar.services.cpmm_ws_recovery_runner import CpmmRecoveryRunner
from smart_money_radar.services.cpmm_ws_resilience import (
    WsResiliencePolicy, disconnect_record, reconnection_is_new_observation,
)
POLICY=WsResiliencePolicy()


ROOT=Path("data/evidence/mainnet/2026-11-20")
OUT=Path("/tmp/smr-cpmm-baseline-live")
WS_ENDPOINT="wss://api.mainnet-beta.solana.com/"
RPC_ENDPOINT="https://api.mainnet-beta.solana.com"
MAX_SECONDS=75
MAX_FRAMES=80
# Network capture must be explicitly enabled by the bounded GitHub workflow.
LIVE_CAPTURE_OPT_IN=os.environ.get("SMR_LIVE_CAPTURE_OPT_IN")=="READ_ONLY_BOUNDED_CM27"
STOP_AFTER_FIRST_VALID_NOTIFICATION=True
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
    """Use existing recovery controller for the complete bounded live capture."""
    if not LIVE_CAPTURE_OPT_IN:
        raise RuntimeError("network capture requires explicit read-only CM27 opt-in")
    import websockets
    OUT.mkdir(parents=True,exist_ok=True)
    previous=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
    raw=(ROOT/previous["raw_file"]).read_bytes()
    if sha256(raw).hexdigest()!=previous["raw_sha256"]:
        raise ValueError("preserved original swap RAW hash mismatch")
    matches=[x for x in decode_raydium_cpmm_swaps(json.loads(raw))
             if x.accounts.pool_state==ACCOUNTS[0]]
    if len(matches)!=1:
        raise ValueError("CPMM pool identity cannot be resolved")
    a=matches[0].accounts
    if (a.pool_state,a.amm_config,a.input_vault,a.output_vault)!=ACCOUNTS:
        raise ValueError("scope differs from original CPMM fixture")
    # Fresh evidence workspace; never silently merge data from another run.
    existing=OUT/"geyser-raw.sqlite"
    if existing.exists():
        raise RuntimeError("existing live journal: preserve it before a new run")
    store=SQLiteGeyserRawStore(existing)
    recovery=BoundedCpmmRecovery(store,source_id="solana-ws-public-mainnet",
                                  accounts=ACCOUNTS,policy=POLICY)
    identity={"endpoint":RPC_ENDPOINT,"original_swap_slot":previous["slot_observed"],
        "authority":a.authority,"input_mint":a.input_token_mint,
        "output_mint":a.output_token_mint,
        "input_token_program":a.input_token_program,
        "output_token_program":a.output_token_program}
    def ws_connect():
        return websockets.connect(WS_ENDPOINT,open_timeout=8,close_timeout=2,
                    max_size=1_000_000,ping_interval=POLICY.ping_interval_seconds,
                    ping_timeout=POLICY.ping_timeout_seconds)
    async def fetch_rpc(request_raw):
        return await asyncio.to_thread(rpc_once,request_raw)
    runner=CpmmRecoveryRunner(recovery,ws_connect=ws_connect,
         rpc_fetch=fetch_rpc,snapshot_identity=identity,
         duration_seconds=MAX_SECONDS,max_frames=MAX_FRAMES)
    try:
        manifest=await runner.run()
        manifest["endpoint_ws"]=WS_ENDPOINT
        manifest["endpoint_rpc"]=RPC_ENDPOINT
        manifest["account_scope"]=list(ACCOUNTS)
        manifest["runtime"]="real_solana_public_rpc_websocket"
        manifest["keepalive_ping_seconds"]=POLICY.ping_interval_seconds
        manifest["keepalive_timeout_seconds"]=POLICY.ping_timeout_seconds
        manifest["journal_integrity"]=store.integrity_check()
        manifest["journal_sessions"]=recovery.report()
        # A live connection may be stable but not prove reconnection. Never
        # promote raw WebSocket observations to network history coverage.
        manifest["live_verification_category"]=(
            "D_REAL_NOTIFICATION" if manifest["observed_notifications"]>0
            else "B_NATURAL_DISCONNECTION_RECOVERED"
            if manifest["recovery_live_proven"]
            else "A_STABLE_SUBSCRIPTIONS_BASELINE"
            if manifest["stable_baseline_observed"]
            else "C_UNVALIDATED_OR_RECOVERY_FAILURE")
        manifest["coverage"]="UNKNOWN"
        manifest["financial_execution_authorized"]=False
        (OUT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,
                                        indent=2,default=str)+"\n")
        print("SMR_RECOVERY connections="+str(len(manifest["connections"])))
        print("SMR_RECOVERY rpc_baselines="+str(manifest["rpc_baseline_calls"]))
        print("SMR_RECOVERY gaps="+str(len(manifest["gaps"])))
        print("SMR_RECOVERY coverage=UNKNOWN")
        print("SMR_RECOVERY economic_execution=False")
    finally:
        store.close()

if __name__=="__main__":
    asyncio.run(run())
