#!/usr/bin/env python3
"""Valida uma transação DAMM v2 da Solana Mainnet sem persistir o payload RAW."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from smart_money_radar.data_sources.damm_v2_transaction_pipeline import (
    process_damm_v2_transaction,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    TOKEN_2022_PROGRAM_ID,
    decode_solana_token_transfers,
)
from smart_money_radar.data_sources.solana_transaction_position import get_transaction_index
from smart_money_radar.data_sources.token2022_fee_absence_proof import (
    build_no_transfer_fee_proof,
)
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    _is_descendant_transfer,
)

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def fetch_transaction(endpoint: str, signature: str, *, max_supported_transaction_version: int = 1) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [signature, {
            "commitment": "finalized",
            "encoding": "json",
            "maxSupportedTransactionVersion": max_supported_transaction_version,
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


def fetch_current_account(endpoint: str, address: str) -> tuple[str, bytes, int]:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "getAccountInfo",
        "params": [address, {"commitment": "finalized", "encoding": "base64"}],
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Falha ao consultar mint atual ({type(exc).__name__}).") from exc
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != 2:
        raise RuntimeError("Resposta getAccountInfo inválida.")
    if payload.get("error") is not None:
        raise RuntimeError("getAccountInfo rejeitado pelo RPC.")
    result = payload.get("result")
    value = result.get("value") if isinstance(result, dict) else None
    context = result.get("context") if isinstance(result, dict) else None
    if not isinstance(value, dict) or not isinstance(context, dict):
        raise RuntimeError("Mint atual ausente ou resposta sem context.")
    owner = value.get("owner")
    data = value.get("data")
    slot = context.get("slot")
    if not isinstance(owner, str) or not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
        raise RuntimeError("Formato do mint atual inválido.")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise RuntimeError("Context slot do mint atual inválido.")
    try:
        raw_data = base64.b64decode(data[0], validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Dados base64 do mint inválidos.") from exc
    return owner, raw_data, slot


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
        "--prove-no-transfer-fee-mint",
        action="append",
        default=[],
        help="mint Token-2022 para verificar ausência imutável de TransferFeeConfig",
    )
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
        keys = raw["transaction"]["message"]["accountKeys"]
        fee_absence_proofs = []
        for mint in args.prove_no_transfer_fee_mint:
            if isinstance(raw.get("slot"), bool) or not isinstance(raw.get("slot"), int):
                raise RuntimeError("slot da transação ausente para prova de taxa zero")
            tx_index = get_transaction_index(args.rpc_url, raw["slot"], args.signature)
            owner, mint_data, snapshot_slot = fetch_current_account(args.rpc_url, mint)
            transfers = decode_solana_token_transfers({"result": raw})
            mint_transfer_observed = any(
                transfer.execution_status == "EXECUTED"
                and transfer.program_id == TOKEN_2022_PROGRAM_ID
                and transfer.mint == mint
                for transfer in transfers
            )
            fee_absence_proofs.append(build_no_transfer_fee_proof(
                mint=mint,
                signature=args.signature,
                transaction_slot=raw["slot"],
                transaction_index=tx_index,
                current_snapshot_slot=snapshot_slot,
                owner=owner,
                mint_data=mint_data,
                transaction_successful=raw.get("meta", {}).get("err") is None,
                mint_transfer_observed=mint_transfer_observed,
            ))
        output = process_damm_v2_transaction(
            {"result": raw},
            monitored_wallet=wallet,
            signature=args.signature,
            observed_at=datetime.now(timezone.utc),
            parser_version="smr-damm-v2-mainnet-validation",
            transfer_fee_absence_proofs=tuple(fee_absence_proofs),
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
        "association_details": [
            {
                "instruction_index": item.instruction_index,
                "event_inner_instruction_index": item.event_inner_instruction_index,
                "stack_height": item.stack_height,
                "cpi_path": item.cpi_path,
                "status": item.status,
                "event": (
                    {
                        "trade_direction": item.event.trade_direction,
                        "collect_fee_mode": item.event.collect_fee_mode,
                        "swap_mode": item.event.swap_mode,
                        "has_referral": item.event.has_referral,
                        "amount_0": item.event.amount_0,
                        "amount_1": item.event.amount_1,
                        "included_transfer_fee_amount_in": item.event.included_transfer_fee_amount_in,
                        "included_transfer_fee_amount_out": item.event.included_transfer_fee_amount_out,
                        "excluded_transfer_fee_amount_out": item.event.excluded_transfer_fee_amount_out,
                        "referral_fee": item.event.swap_result.referral_fee,
                        "output_amount": item.event.swap_result.output_amount,
                    }
                    if item.event else None
                ),
            }
            for item in output.associations
        ],
        "transfer_evidence_statuses": [item.status for item in output.transfer_evidence],
        "transfer_evidence": [
            {
                "status": item.status,
                "instruction_index": item.instruction_index,
                "inner_instruction_index": item.inner_instruction_index,
                "cpi_path": item.cpi_path,
                "input_transfer_index": (
                    item.input_transfer.instruction_index
                    if item.input_transfer else None
                ),
                "output_transfer_index": (
                    item.output_transfer.instruction_index
                    if item.output_transfer else None
                ),
                "referral_transfer_index": (
                    item.referral_transfer.instruction_index
                    if item.referral_transfer else None
                ),
                "reason": item.reason,
                "transfer_fee_review_required": item.transfer_fee_review_required,
            }
            for item in output.transfer_evidence
        ],
        "reconciliation_status": (
            output.reconciliation.status if output.reconciliation else None
        ),
        "transfer_fee_absence_proofs": [
            {
                "mint": proof.mint,
                "signature": proof.signature,
                "transaction_slot": proof.transaction_slot,
                "transaction_index": proof.transaction_index,
                "current_snapshot_slot": proof.current_snapshot_slot,
                "fee_amount_raw": proof.fee_amount_raw,
                "basis": proof.basis,
            }
            for proof in (
                output.reconciliation.transfer_fee_absence_proofs
                if output.reconciliation else tuple(fee_absence_proofs)
            )
        ],
        "wrapped_sol_fundings": [
            {
                "token_account": item.token_account,
                "source_wallet": item.source_wallet,
                "amount_raw": item.amount_raw,
                "system_transfer_index": item.system_transfer_index,
                "system_transfer_indices": list(item.system_transfer_indices),
                "sync_native_index": item.sync_native_index,
                "lamports_delta_raw": item.lamports_delta_raw,
            }
            for item in (
                output.reconciliation.wrapped_sol_fundings
                if output.reconciliation else ()
            )
        ],
        "wrapped_sol_lifecycles": [
            {
                "token_account": item.token_account,
                "owner_wallet": item.owner_wallet,
                "create_indices": list(item.create_indices),
                "system_transfer_indices": list(item.system_transfer_indices),
                "sync_native_indices": list(item.sync_native_indices),
                "token_transfer_indices": list(item.token_transfer_indices),
                "close_account_indices": list(item.close_account_indices),
                "funding_amount_raw": item.funding_amount_raw,
                "cycle_balances_before_close": list(item.cycle_balances_before_close),
                "lamports_delta_raw": item.lamports_delta_raw,
            }
            for item in (
                output.reconciliation.wrapped_sol_lifecycles
                if output.reconciliation else ()
            )
        ],
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
        "transfer_candidate_details": [
            {
                "instruction_index": context.association.instruction_index,
                "cpi_path": context.association.cpi_path,
                "input_candidates": [
                    {
                        "transfer_index": index,
                        "inner_instruction_index": transfer.inner_instruction_index,
                        "cpi_path": transfer.cpi_path,
                        "source": transfer.source_account,
                        "destination": transfer.destination_account,
                        "mint": transfer.mint,
                        "amount_raw": transfer.amount_raw,
                    }
                    for index, transfer in enumerate(output.transfers)
                    if transfer.execution_status == "EXECUTED"
                    and _is_descendant_transfer(transfer, context.association)
                    and transfer.source_account == context.accounts.input_token_account
                    and transfer.destination_account == context.accounts.input_vault
                ],
                "output_candidates": [
                    {
                        "transfer_index": index,
                        "inner_instruction_index": transfer.inner_instruction_index,
                        "cpi_path": transfer.cpi_path,
                        "source": transfer.source_account,
                        "destination": transfer.destination_account,
                        "mint": transfer.mint,
                        "amount_raw": transfer.amount_raw,
                    }
                    for index, transfer in enumerate(output.transfers)
                    if transfer.execution_status == "EXECUTED"
                    and _is_descendant_transfer(transfer, context.association)
                    and transfer.source_account == context.accounts.output_vault
                    and transfer.destination_account == context.accounts.output_token_account
                ],
                "referral_candidates": [
                    {
                        "transfer_index": index,
                        "inner_instruction_index": transfer.inner_instruction_index,
                        "cpi_path": transfer.cpi_path,
                        "source": transfer.source_account,
                        "destination": transfer.destination_account,
                        "mint": transfer.mint,
                        "amount_raw": transfer.amount_raw,
                    }
                    for index, transfer in enumerate(output.transfers)
                    if transfer.execution_status == "EXECUTED"
                    and _is_descendant_transfer(transfer, context.association)
                    and context.accounts.referral_token_account
                    and transfer.destination_account == context.accounts.referral_token_account
                ],
            }
            for context in output.contexts
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
        "swap_accounts": [
            {
                "input_token_account": item.accounts.input_token_account,
                "output_token_account": item.accounts.output_token_account,
                "input_vault": item.accounts.input_vault,
                "output_vault": item.accounts.output_vault,
                "input_mint": item.accounts.input_mint,
                "output_mint": item.accounts.output_mint,
                "token_a_vault": item.accounts.token_a_vault,
                "token_b_vault": item.accounts.token_b_vault,
                "referral_token_account": item.accounts.referral_token_account,
            }
            for item in output.contexts
        ],
        "target_account_lamports": [
            {
                "account": account,
                "account_index": keys.index(account) if account in keys else None,
                "pre_lamports": raw["meta"]["preBalances"][keys.index(account)] if account in keys and keys.index(account) < len(raw["meta"].get("preBalances", [])) else None,
                "post_lamports": raw["meta"]["postBalances"][keys.index(account)] if account in keys and keys.index(account) < len(raw["meta"].get("postBalances", [])) else None,
            }
            for account in sorted({
                value
                for context in output.contexts
                for value in (
                    context.accounts.input_token_account,
                    context.accounts.output_token_account,
                    context.accounts.input_vault,
                    context.accounts.output_vault,
                )
            })
        ],
        "outer_instruction_accounts": [
            {
                "index": index,
                "program": (
                    instruction.get("programId")
                    or keys[instruction["programIdIndex"]]
                    if isinstance(instruction.get("programIdIndex"), int)
                    and instruction["programIdIndex"] < len(keys)
                    else instruction.get("programId", "?")
                ),
                "accounts": [
                    keys[value] if isinstance(value, int) and value < len(keys) else value
                    for value in instruction.get("accounts", [])
                ],
                "data": instruction.get("data"),
            }
            for index, instruction in enumerate(raw["transaction"]["message"]["instructions"])
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if output.status == "RECONCILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
