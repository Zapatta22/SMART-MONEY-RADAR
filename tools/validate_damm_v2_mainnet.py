#!/usr/bin/env python3
"""Valida uma transação DAMM v2 da Solana Mainnet sem persistir o payload RAW."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from smart_money_radar.data_sources.damm_v2_transaction_pipeline import (
    process_damm_v2_transaction,
)

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def fetch_transaction(endpoint: str, signature: str) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {
            "commitment": "finalized",
            "encoding": "json",
            "maxSupportedTransactionVersion": 0,
        }],
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Falha ao consultar RPC ({type(exc).__name__}).") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("RPC retornou JSON inválido.") from exc

    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise RuntimeError("Resposta RPC/JSON-RPC inválida.")
    if payload.get("id") != 1:
        raise RuntimeError("ID da resposta RPC divergente.")
    if payload.get("error") is not None:
        raise RuntimeError(f"RPC retornou erro: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Transação não encontrada no RPC.")
    signatures = result.get("transaction", {}).get("signatures")
    if not isinstance(signatures, list) or not signatures or signatures[0] != signature:
        raise RuntimeError("Assinatura primária da resposta não confere.")
    return result


def infer_monitored_wallet(result: dict) -> str:
    transaction = result["transaction"]
    message = transaction["message"]
    required = message["header"]["numRequiredSignatures"]
    keys = message["accountKeys"]
    if isinstance(required, bool) or not isinstance(required, int) or required < 1:
        raise RuntimeError("Quantidade de signatários inválida.")
    signers = set(keys[:required])
    meta = result["meta"]
    owners = {
        item.get("owner")
        for field in ("preTokenBalances", "postTokenBalances")
        for item in meta.get(field, [])
        if isinstance(item, dict) and isinstance(item.get("owner"), str)
    }
    candidates = sorted(signers & owners)
    if len(candidates) != 1:
        raise RuntimeError(
            "Não foi possível identificar uma única carteira monitorada "
            f"entre signatários e proprietários de token accounts (candidatos={len(candidates)})."
        )
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signature", default=os.environ.get("SMR_DAMM_V2_SIGNATURE"))
    parser.add_argument(
        "--rpc-url",
        default=os.environ.get("SMR_SOLANA_RPC_URL", DEFAULT_RPC),
    )
    args = parser.parse_args()
    if not args.signature:
        parser.error("informe --signature ou SMR_DAMM_V2_SIGNATURE")
    if not args.rpc_url.startswith("https://"):
        parser.error("RPC deve usar HTTPS")

    try:
        raw = fetch_transaction(args.rpc_url, args.signature)
        wallet = infer_monitored_wallet(raw)
        output = process_damm_v2_transaction(
            {"result": raw},
            monitored_wallet=wallet,
            signature=args.signature,
            observed_at=datetime.now(timezone.utc),
            parser_version="smr-damm-v2-mainnet-validation",
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}, ensure_ascii=False))
        return 2

    report = {
        "status": output.status,
        "reason": output.reason,
        "slot": raw.get("slot"),
        "signature": args.signature,
        "monitored_wallet": wallet,
        "associations": len(output.associations),
        "association_statuses": [item.status for item in output.associations],
        "transfer_evidence_statuses": [item.status for item in output.transfer_evidence],
        "reconciliation_status": (
            output.reconciliation.status if output.reconciliation else None
        ),
        "bundles": len(output.bundles),
        "classification_sides": [item.classification.side for item in output.bundles],
        "expected_account_deltas": [
            {
                "token_account": item.token_account,
                "mint": item.mint,
                "decimals": item.decimals,
                "expected_delta_raw": item.expected_delta_raw,
            }
            for item in (
                output.reconciliation.expected_account_deltas
                if output.reconciliation else ()
            )
        ],
        "observed_account_deltas": [
            {
                "token_account": item.token_account,
                "mint": item.mint,
                "decimals": item.decimals,
                "delta_raw": item.delta_raw,
                "owner": item.owner,
            }
            for item in (output.balance_deltas.deltas if output.balance_deltas else ())
            if output.reconciliation and any(
                expected.token_account == item.token_account
                for expected in output.reconciliation.expected_account_deltas
            )
        ],
        "decoded_transfers": [
            {
                "type": item.instruction_type,
                "outer_index": item.instruction_index,
                "inner_index": item.inner_instruction_index,
                "cpi_path": item.cpi_path,
                "source": item.source_account,
                "destination": item.destination_account,
                "mint": item.mint,
                "amount_raw": item.amount_raw,
                "fee_raw": item.fee_amount_raw,
            }
            for item in output.transfers
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if output.status == "RECONCILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
