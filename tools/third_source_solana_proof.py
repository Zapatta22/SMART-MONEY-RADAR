"""One bounded fallback mainnet RPC source, used only after PublicNode returned null.

This collects a distinct endpoint response as observed RAW without claiming
cryptographic provider independence. No wallet operations, no secrets.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
from smart_money_radar.services.solana_public_rpc_read import fetch_public_finalized_transaction
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps

FIRST=Path("data/evidence/mainnet/2026-11-20")
ORIG=json.loads((FIRST/"first-proof.manifest.json").read_bytes())
SIG=ORIG["signature_requested"]
SLOT=ORIG["slot_observed"]
POOL=ORIG["decoded_cpmm_swaps"][0]["pool"]
ENDPOINT="https://public-solana-mainnet.rpcnode.dev"
OUTPUT=Path("/tmp/smr-third-source-proof")

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    result=fetch_public_finalized_transaction(
        endpoint=ENDPOINT,signature=SIG,enabled=True,
        source_id="rpcnode-public-mainnet",timeout_seconds=12)
    report={
        "schema":"smr.third-source-proof.v1",
        "endpoint":ENDPOINT,"source_id":"rpcnode-public-mainnet",
        "source_1":ORIG["rpc_endpoint"],"source_2":"https://solana-rpc.publicnode.com",
        "requested_commitment":"finalized","signature_requested":SIG,
        "slot_expected":SLOT,"pool_expected":POOL,"requests_sent":result.requests_sent,
        "status":result.status,"reasons":list(result.reasons),
        "independent_provider_proven":False,"independent_finality_proven":False,
        "economic_execution_authorized":False,
        "historical_amm_config_verified":False,"historical_reserves_verified":False,
        "network_observed_at":None,"network_available_at":None,
        "comparison_status":"UNKNOWN",
        "report_time":datetime.now(timezone.utc).isoformat(),
    }
    if result.evidence is not None:
        ev=result.evidence
        raw=ev.raw_payload
        name=SIG+".third-source.raw.json"
        (OUTPUT/name).write_bytes(raw)
        report.update({
            "raw_file":name,"raw_sha256":sha256(raw).hexdigest(),
            "network_observed_at":ev.observed_at.isoformat(),
            "network_available_at":ev.available_at.isoformat(),
            "slot_observed":ev.slot,
            "signature_in_response":ev.signature if ev.slot is not None else None,
        })
        payload=json.loads(raw)
        if isinstance(payload.get("result"),dict):
            swaps=decode_raydium_cpmm_swaps(payload)
            matches=[x for x in swaps if x.accounts.pool_state==POOL]
            report["cpmm_swap_count"]=len(swaps)
            report["program_pool_matched"]=bool(matches)
            report["vaults_mints_matched"]=any(
                x.accounts.input_vault==ORIG["decoded_cpmm_swaps"][0]["input_vault"]
                and x.accounts.output_vault==ORIG["decoded_cpmm_swaps"][0]["output_vault"]
                and x.accounts.input_token_mint==ORIG["decoded_cpmm_swaps"][0]["input_mint"]
                and x.accounts.output_token_mint==ORIG["decoded_cpmm_swaps"][0]["output_mint"]
                for x in matches
            )
            first=json.loads((FIRST/ORIG["raw_file"]).read_bytes())["result"]
            second=payload["result"]
            scope=lambda tx:{
                "slot":tx.get("slot"),"blockTime":tx.get("blockTime"),
                "transaction":tx.get("transaction"),"meta":tx.get("meta")}
            digest=lambda d:sha256(json.dumps(d,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            report["canonical_core_sha256_primary"]=digest(scope(first))
            report["canonical_core_sha256_third"]=digest(scope(second))
            report["canonical_core_exact_match"]=report["canonical_core_sha256_primary"]==report["canonical_core_sha256_third"]
            report["fee_lamports_match"]=first["meta"].get("fee")==second["meta"].get("fee")
            report["comparison_status"]=(
                "RPC_CROSS_SOURCE_CONSISTENT_UNATTESTED"
                if ev.slot==SLOT and report["program_pool_matched"] and report["vaults_mints_matched"]
                and report["fee_lamports_match"] else "CONFLICTED_OR_INCOMPLETE"
            )
    (OUTPUT/"third-source.manifest.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n")
    for key in ("status","requests_sent","slot_observed","raw_sha256",
                "comparison_status","canonical_core_exact_match","program_pool_matched",
                "independent_provider_proven","historical_reserves_verified"):
        print("SMR_THIRD "+key+"="+str(report.get(key,"UNKNOWN")))
    print("SMR_THIRD no_real_trades=True")

if __name__=="__main__":
    main()
