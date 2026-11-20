"""One-shot public RPC capture of prospective CPMM accounts (no historical claims).

This is explicit single-request GitHub Actions sampling. Request and response
are both preserved byte-for-byte; failure does not become a safe baseline.
Never signs, sends transaction, buys/sells, or fetches private credentials.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
import json

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.services.prospective_cpmm_account_snapshot import inspect_prospective_cpmm_response

ROOT=Path("data/evidence/mainnet/2026-11-20")
FIRST=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
ENDPOINT="https://api.mainnet-beta.solana.com"
OUT=Path("/tmp/smr-prospective-cpmm")

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    original=(ROOT/FIRST["raw_file"]).read_bytes()
    if sha256(original).hexdigest()!=FIRST["raw_sha256"]:
        raise ValueError("original proof RAW tampered")
    swaps=decode_raydium_cpmm_swaps(json.loads(original))
    matches=[s for s in swaps if s.accounts.pool_state==FIRST["decoded_cpmm_swaps"][0]["pool"]]
    if len(matches)!=1:
        raise ValueError("CPMM source swap ambiguous")
    accounts=matches[0].accounts
    addresses=[accounts.pool_state,accounts.amm_config,
               accounts.input_vault,accounts.output_vault]
    request={"jsonrpc":"2.0","id":1,"method":"getMultipleAccounts",
             "params":[addresses,{"encoding":"base64","commitment":"finalized"}]}
    request_bytes=json.dumps(request,separators=(",",":"),sort_keys=True).encode()
    (OUT/"request.raw.json").write_bytes(request_bytes)
    manifest={"schema":"smr.prospective-cpmm.v1",
              "purpose":"BASELINE_AFTER_ORIGINAL_SWAP_NOT_HISTORICAL",
              "original_slot":FIRST["slot_observed"],
              "original_signature":FIRST["signature_requested"],
              "original_pool":accounts.pool_state,
              "endpoint":ENDPOINT,
              "request_sha256":sha256(request_bytes).hexdigest(),
              "requested_commitment":"finalized",
              "requests_attempted":1,
              "status":"UNKNOWN",
              "provider_authenticated":False,
              "historical_original_swap_state_verified":False,
              "pre_swap_instruction_order_proven":False,
              "economic_execution_authorized":False,
              "observed_at":None,"available_at":None,
              "reasons":["not_collected"]}
    try:
        request_object=Request(ENDPOINT,data=request_bytes,
                               headers={"Content-Type":"application/json"},method="POST")
        start=datetime.now(timezone.utc)
        with urlopen(request_object,timeout=12) as res:
            response_bytes=res.read(2_000_001)
        end=datetime.now(timezone.utc)
        manifest["observed_at"]=start.isoformat()
        manifest["available_at"]=end.isoformat()
        if len(response_bytes)>2_000_000:
            raise ValueError("rpc_payload_exceeds_bounded_limit")
        (OUT/"response.raw.json").write_bytes(response_bytes)
        manifest["response_sha256"]=sha256(response_bytes).hexdigest()
        result=inspect_prospective_cpmm_response(
            response_raw=response_bytes,request_raw=request_bytes,
            source_id="solana-public-mainnet-triton",endpoint=ENDPOINT,
            observed_at=start,available_at=end,
            pool=accounts.pool_state,amm_config=accounts.amm_config,
            input_vault=accounts.input_vault,output_vault=accounts.output_vault,
            input_mint=accounts.input_token_mint,output_mint=accounts.output_token_mint,
            authority=accounts.authority,
            input_token_program=accounts.input_token_program,
            output_token_program=accounts.output_token_program,
            original_swap_slot=FIRST["slot_observed"])
        manifest.update({
            "status":result.status,"reasons":list(result.reasons),
            "context_slot":result.slot,
            "account_sha256":list(result.account_sha256),
            "input_vault_raw_at_collection":result.input_vault_raw,
            "output_vault_raw_at_collection":result.output_vault_raw,
            "effective_input_raw_at_collection":result.effective_input_raw,
            "effective_output_raw_at_collection":result.effective_output_raw,
            "trade_fee_rate_at_collection":result.declared_trade_fee_rate,
            "creator_fee_rate_at_collection":result.declared_creator_fee_rate,
        })
    except (HTTPError,URLError,TimeoutError,OSError,ValueError) as exc:
        manifest["status"]="UNKNOWN"
        manifest["reasons"]=["rpc_unavailable_or_incomplete",type(exc).__name__]
    (OUT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    for name in ("status","context_slot","response_sha256",
                 "effective_input_raw_at_collection","historical_original_swap_state_verified",
                 "economic_execution_authorized"):
        print("SMR_PROSPECTIVE "+name+"="+str(manifest.get(name,"UNKNOWN")))
    print("SMR_PROSPECTIVE requests_attempted=1")
    print("SMR_PROSPECTIVE finances_disabled=True")

if __name__=="__main__":
    run()
