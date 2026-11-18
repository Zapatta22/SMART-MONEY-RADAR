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
from smart_money_radar.data_sources.solana_wrapped_sol_funding import NATIVE_MINT
from validate_damm_v2_mainnet import fetch_transaction, infer_monitored_wallet

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
FALLBACK_RPC = "https://solana-rpc.publicnode.com"


def rpc_call(endpoint: str, method: str, params: list) -> object:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict) or payload.get("id") != 1 or payload.get("error") is not None:
        raise RuntimeError(f"RPC inválido em {method}")
    return payload.get("result")


def _fetch_signatures(
    endpoints: tuple[str, ...], limit: int, pages: int
) -> tuple[list, str]:
    collected = []
    before = None
    first_endpoint = None
    for _ in range(pages):
        options = {"limit": limit, "commitment": "finalized"}
        if before is not None:
            options["before"] = before
        page_result = None
        page_endpoint = None
        errors = []
        for endpoint in endpoints:
            try:
                result = rpc_call(
                    endpoint, "getSignaturesForAddress",
                    [METEORA_DAMM_V2_PROGRAM_ID, options],
                )
                if not isinstance(result, list):
                    raise RuntimeError("RPC não retornou lista de assinaturas")
                page_result = result
                page_endpoint = endpoint
                break
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {str(exc)[:100]}")
        if page_result is None:
            raise RuntimeError(
                "Falha ao obter página de assinaturas nos RPCs: " + " | ".join(errors)
            )
        if first_endpoint is None:
            first_endpoint = page_endpoint
        if not page_result:
            break
        collected.extend(page_result)
        last_signature = page_result[-1].get("signature")
        if not isinstance(last_signature, str) or not last_signature:
            raise RuntimeError("última assinatura da página é inválida")
        before = last_signature
    return collected, first_endpoint or endpoints[0]

def scan(endpoints: tuple[str, ...], limit: int, pages: int) -> dict:
    signatures, signature_rpc = _fetch_signatures(endpoints, limit, pages)
    inspected = 0
    candidates = []
    failures = Counter()
    for item in signatures:
        signature = item.get("signature") if isinstance(item, dict) else None
        if not isinstance(signature, str) or not signature:
            failures["assinatura ausente/inválida"] += 1
            continue

        raw = None
        fetch_errors = []
        for endpoint in endpoints:
            try:
                raw = fetch_transaction(
                    endpoint, signature, max_supported_transaction_version=1
                )
                break
            except Exception as exc:
                fetch_errors.append(f"{type(exc).__name__}: {str(exc)[:100]}")
        if raw is None:
            failures["; ".join(fetch_errors) or "transação indisponível"] += 1
            continue

        inspected += 1
        try:
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
            input_counts = Counter(
                (context.accounts.input_token_account, context.accounts.input_mint)
                for context in result.contexts
            )
            shared_wsol_inputs = [
                {"token_account": account, "operations": count}
                for (account, mint), count in input_counts.items()
                if mint == NATIVE_MINT and count >= 2
            ]
            wsol_roles = {}
            for operation_index, context in enumerate(result.contexts):
                if context.accounts.input_mint == NATIVE_MINT:
                    wsol_roles.setdefault(context.accounts.input_token_account, []).append(
                        {"operation": operation_index, "role": "input"}
                    )
                if context.accounts.output_mint == NATIVE_MINT:
                    wsol_roles.setdefault(context.accounts.output_token_account, []).append(
                        {"operation": operation_index, "role": "output"}
                    )
            shared_wsol_accounts = [
                {"token_account": account, "uses": uses}
                for account, uses in wsol_roles.items()
                if len({use["operation"] for use in uses}) >= 2
            ]
            funding_accounts = set()
            lifecycle_accounts = set()
            if result.reconciliation is not None:
                funding_accounts = {
                    funding.token_account
                    for funding in result.reconciliation.wrapped_sol_fundings
                }
                lifecycle_accounts = {
                    lifecycle.token_account
                    for lifecycle in result.reconciliation.wrapped_sol_lifecycles
                }
            funded_shared_wsol_inputs = [
                item["token_account"] for item in shared_wsol_inputs
                if item["token_account"] in funding_accounts
            ]
            reconciled_shared_wsol_accounts = [
                item["token_account"] for item in shared_wsol_accounts
                if item["token_account"] in funding_accounts | lifecycle_accounts
            ]
            candidate = {
                "signature": signature,
                "slot": raw.get("slot"),
                "matched_swap2_count": len(swaps),
                "pipeline_status": result.status,
                "pipeline_reason": result.reason,
                "swap_account_directions": [
                    {
                        "input_token_account": context.accounts.input_token_account,
                        "input_mint": context.accounts.input_mint,
                        "output_token_account": context.accounts.output_token_account,
                        "output_mint": context.accounts.output_mint,
                        "trade_direction": context.association.event.trade_direction,
                    }
                    for context in result.contexts
                ],
                "shared_wsol_input_accounts": shared_wsol_inputs,
                "shared_wsol_accounts": shared_wsol_accounts,
                "reconciled_shared_wsol_accounts": reconciled_shared_wsol_accounts,
                "funded_shared_wsol_input_accounts": len(funded_shared_wsol_inputs),
            }
            candidates.append(candidate)
            if result.status == "RECONCILED" and (funded_shared_wsol_inputs or reconciled_shared_wsol_accounts):
                return {
                    "status": "FOUND_SHARED_WSOL_MULTI_SWAP",
                    "inspected": inspected,
                    "failures": dict(failures),
                    "signature_rpc": "primary" if signature_rpc == endpoints[0] else "fallback",
                    "candidate": candidate,
                }
        except Exception as exc:
            failures[f"análise {type(exc).__name__}: {str(exc)[:100]}"] += 1

    return {
        "status": "NO_SHARED_WSOL_MULTI_SWAP_FOUND",
        "inspected": inspected,
        "failures": dict(failures),
        "signature_rpc": "primary" if signature_rpc == endpoints[0] else "fallback",
        "multi_swap_candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--rpc-url", default=os.environ.get(
        "SMR_DAMM_V2_SCAN_RPC_URL", os.environ.get("SMR_SOLANA_RPC_URL", DEFAULT_RPC)
    ))
    parser.add_argument("--fallback-rpc-url", default=FALLBACK_RPC)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit deve estar entre 1 e 100")
    if not 1 <= args.pages <= 10:
        parser.error("--pages deve estar entre 1 e 10")
    if not args.rpc_url.startswith("https://") or not args.fallback_rpc_url.startswith("https://"):
        parser.error("RPCs devem usar HTTPS")
    endpoints = tuple(dict.fromkeys((args.rpc_url, args.fallback_rpc_url)))
    try:
        report = scan(endpoints, args.limit, args.pages)
    except Exception as exc:
        report = {"status": "SCAN_ERROR", "reason": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {
        "FOUND_SHARED_WSOL_MULTI_SWAP", "NO_SHARED_WSOL_MULTI_SWAP_FOUND"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
