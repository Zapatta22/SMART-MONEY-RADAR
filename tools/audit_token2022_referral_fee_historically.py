#!/usr/bin/env python3
"""Audita a taxa Token-2022 de referral com snapshots históricos pré/pós-transação.

Requer um endpoint Helius Historical Accounts habilitado e um RPC Mainnet padrão.
Não persiste dados, não avança checkpoints e nunca libera reconciliação.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

from smart_money_radar.data_sources.damm_v2_fee_math import calculate_transfer_fee
from smart_money_radar.data_sources.helius_historical_account import (
    get_historical_account_info,
    get_historical_account_info_before_transaction,
)
from smart_money_radar.data_sources.solana_transaction_position import get_transaction_index
from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    decode_transfer_fee_amount,
    decode_transfer_fee_config,
)

TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def rpc_result(endpoint: str, method: str, params: list) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0", "id": "smr-historical-fee-audit",
        "method": method, "params": params,
    }).encode()
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise RuntimeError(f"envelope inválido em {method}")
    if payload.get("id") != "smr-historical-fee-audit":
        raise RuntimeError(f"ID divergente em {method}")
    if payload.get("error") is not None:
        error = payload["error"]
        code = error.get("code") if isinstance(error, dict) else None
        raise RuntimeError(f"{method} rejeitado pelo RPC (code={code})")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"resultado ausente em {method}")
    return result


def epoch_for_slot(endpoint: str, slot: int) -> int:
    schedule = rpc_result(endpoint, "getEpochSchedule", [])
    first_normal_slot = schedule.get("firstNormalSlot")
    first_normal_epoch = schedule.get("firstNormalEpoch")
    slots_per_epoch = schedule.get("slotsPerEpoch")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (first_normal_slot, first_normal_epoch, slots_per_epoch)
    ) or slots_per_epoch == 0:
        raise RuntimeError("getEpochSchedule retornou campos inválidos")
    if slot < first_normal_slot:
        raise RuntimeError("slot em período warmup não suportado por este auditor")
    return first_normal_epoch + (slot - first_normal_slot) // slots_per_epoch


def audit(
    standard_rpc: str,
    historical_rpc: str,
    signature: str,
    slot: int,
    mint: str,
    referral_account: str,
    gross_amounts_raw: list[int],
) -> dict:
    index = get_transaction_index(standard_rpc, slot, signature)
    epoch = epoch_for_slot(standard_rpc, slot)
    mint_before = get_historical_account_info_before_transaction(
        historical_rpc, mint, slot, index
    )
    mint_after = get_historical_account_info(
        historical_rpc, mint, slot, index
    )
    if mint_before.owner != TOKEN_2022_PROGRAM_ID or mint_after.owner != TOKEN_2022_PROGRAM_ID:
        raise RuntimeError("mint histórico não pertence ao Token-2022")
    config_before = decode_transfer_fee_config(mint_before.data)
    config_after = decode_transfer_fee_config(mint_after.data)
    if config_before != config_after:
        raise RuntimeError("TransferFeeConfig mudou durante a transação; revisão manual necessária")
    rate = config_before.fee_for_epoch(epoch)
    if not gross_amounts_raw or any(
        isinstance(amount, bool) or not isinstance(amount, int) or amount < 0
        for amount in gross_amounts_raw
    ):
        raise ValueError("gross_amounts_raw deve conter valores inteiros não negativos")
    expected_fees = [
        calculate_transfer_fee(amount, rate.basis_points, rate.maximum_fee)
        for amount in gross_amounts_raw
    ]
    expected_fee = sum(expected_fees)
    referral_before = get_historical_account_info_before_transaction(
        historical_rpc, referral_account, slot, index
    )
    referral_after = get_historical_account_info(
        historical_rpc, referral_account, slot, index
    )
    if referral_before.owner != TOKEN_2022_PROGRAM_ID or referral_after.owner != TOKEN_2022_PROGRAM_ID:
        raise RuntimeError("conta referral histórica não pertence ao Token-2022")
    withheld_before = decode_transfer_fee_amount(referral_before.data).withheld_amount
    withheld_after = decode_transfer_fee_amount(referral_after.data).withheld_amount
    withheld_delta = withheld_after - withheld_before
    if withheld_delta < 0:
        raise RuntimeError("withheld amount diminuiu; estado histórico inconsistente")
    return {
        "status": "HISTORICAL_FEE_MATCH" if withheld_delta == expected_fee else "FEE_MISMATCH",
        "signature": signature,
        "slot": slot,
        "transaction_index": index,
        "epoch": epoch,
        "mint": mint,
        "referral_account": referral_account,
        "gross_amounts_raw": gross_amounts_raw,
        "expected_fee_per_transfer_raw": expected_fees,
        "transfer_fee_config": {
            "older_transfer_fee": {
                "epoch": config_before.older_transfer_fee.epoch,
                "maximum_fee": config_before.older_transfer_fee.maximum_fee,
                "basis_points": config_before.older_transfer_fee.basis_points,
            },
            "newer_transfer_fee": {
                "epoch": config_before.newer_transfer_fee.epoch,
                "maximum_fee": config_before.newer_transfer_fee.maximum_fee,
                "basis_points": config_before.newer_transfer_fee.basis_points,
            },
        },
        "selected_rate": {
            "epoch": rate.epoch,
            "maximum_fee": rate.maximum_fee,
            "basis_points": rate.basis_points,
        },
        "expected_fee_raw": expected_fee,
        "withheld_before_raw": withheld_before,
        "withheld_after_raw": withheld_after,
        "withheld_delta_raw": withheld_delta,
        "mint_last_updated_before": {
            "slot": mint_before.last_updated_slot,
            "transaction_index": mint_before.last_updated_transaction_index,
        },
        "mint_last_updated_after": {
            "slot": mint_after.last_updated_slot,
            "transaction_index": mint_after.last_updated_transaction_index,
        },
        "referral_last_updated_before": {
            "slot": referral_before.last_updated_slot,
            "transaction_index": referral_before.last_updated_transaction_index,
        },
        "referral_last_updated_after": {
            "slot": referral_after.last_updated_slot,
            "transaction_index": referral_after.last_updated_transaction_index,
        },
        "reconciliation_released": False,
        "note": "withheld_delta é agregado por conta; informe todas as transferências da mesma conta/mint nesta transação. Auditoria somente leitura; não persiste bundle nem avança checkpoint.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--slot", required=True, type=int)
    parser.add_argument("--mint", required=True)
    parser.add_argument("--referral-account", required=True)
    parser.add_argument(
        "--gross-amount-raw", required=True, action="append", type=int,
        help="valor bruto de cada transferência para a conta referral na transação; repetir para cada perna",
    )
    parser.add_argument(
        "--rpc-url",
        default=os.environ.get("SMR_SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
    )
    parser.add_argument(
        "--historical-rpc-url",
        default=os.environ.get("SMR_HELIUS_HISTORICAL_RPC_URL"),
    )
    args = parser.parse_args()
    if not args.historical_rpc_url:
        parser.error("defina SMR_HELIUS_HISTORICAL_RPC_URL ou --historical-rpc-url")
    if args.slot < 0 or any(amount < 0 for amount in args.gross_amount_raw):
        parser.error("slot e gross amount devem ser não negativos")
    try:
        result = audit(
            args.rpc_url, args.historical_rpc_url, args.signature, args.slot,
            args.mint, args.referral_account, args.gross_amount_raw,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "HISTORICAL_FEE_AUDIT_INCOMPLETE",
            "reason": f"{type(exc).__name__}: {exc}",
            "reconciliation_released": False,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "HISTORICAL_FEE_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
