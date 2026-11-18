#!/usr/bin/env python3
"""Procura transações Mainnet com múltiplos swap2 DAMM v2 e wSOL compartilhado.

Consulta apenas dados públicos do RPC. Não persiste payload RAW nem executa ordens.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from smart_money_radar.data_sources.damm_v2_analyzer import analyze_damm_v2_swap_events
from smart_money_radar.data_sources.damm_v2_decoder import METEORA_DAMM_V2_PROGRAM_ID
from smart_money_radar.data_sources.damm_v2_transaction_pipeline import process_damm_v2_transaction
from validate_damm_v2_mainnet import fetch_transaction, infer_monitored_wallet

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def rpc_call(endpoint: str, method: str, params: list) -> object:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict) or payload.get("id") != 1 or payload.get("error") is not None:
        raise RuntimeError(f"RPC inválido em {method}")
    return payload.get("result")


def scan(endpoint: str, limit: int) -> dict:
    signatures = rpc_call(endpoint, "getSignaturesForAddress", [
        METEORA_DAMM_V2_PROGRAM_ID, {"limit": limit, "commitment": "finalized"}
    ])
    if not isinstance(signatures, list):
        raise RuntimeError("RPC não retornou lista de assinaturas")
    inspected = 0
    candidates = []
    failures = 0
    for item in signatures:
        signature = item.get("signature") if isinstance(item, dict) else None
        if not isinstance(signature, str) or not signature:
            failures += 1
            continue
        try:
            raw = fetch_transaction(endpoint, signature)
            inspected += 1
            associations = analyze_damm_v2_swap_events({"result": raw})
            swaps = [
                association for association in associations
                if association.status == "MATCHED"
                and association.instruction is not None
                and association.instruction.instruction_name == "swap2"
            ]
            if len(swaps) < 2:
                continue
            wallet = infer_monitored_wallet(raw)
            result = process_damm_v2_transaction(
                {"result": raw}, monitored_wallet=wallet, signature=signature,
                observed_at=datetime.now(timezone.utc),
                parser_version="smr-damm-v2-multi-swap-mainnet-scan",
            )
            shared_funding_accounts = []
            if result.status == "RECONCILED" and result.reconciliation is not None:
                input_counts = Counter(
                    context.accounts.input_token_account for context in result.contexts
                )
                shared_funding_accounts = [
                    funding.token_account
                    for funding in result.reconciliation.wrapped_sol_fundings
                    if input_counts[funding.token_account] >= 2
                ]
            candidate = {
                "signature": signature,
                "slot": raw.get("slot"),
                "matched_swap2_count": len(swaps),
                "pipeline_status": result.status,
                "shared_wsol_input_accounts": len(shared_funding_accounts),
            }
            candidates.append(candidate)
            if shared_funding_accounts:
                return {
                    "status": "FOUND_SHARED_WSOL_MULTI_SWAP",
                    "inspected": inspected,
                    "failures": failures,
                    "candidate": candidate,
                }
        except Exception:
            failures += 1
    return {
        "status": "NO_SHARED_WSOL_MULTI_SWAP_FOUND",
        "inspected": inspected,
        "failures": failures,
        "multi_swap_candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--rpc-url", default=os.environ.get("SMR_SOLANA_RPC_URL", DEFAULT_RPC))
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit deve estar entre 1 e 100")
    if not args.rpc_url.startswith("https://"):
        parser.error("RPC deve usar HTTPS")
    try:
        report = scan(args.rpc_url, args.limit)
    except Exception as exc:
        report = {"status": "SCAN_ERROR", "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {
        "FOUND_SHARED_WSOL_MULTI_SWAP", "NO_SHARED_WSOL_MULTI_SWAP_FOUND"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
