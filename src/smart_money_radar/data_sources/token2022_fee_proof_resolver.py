"""Resolve provas de taxa zero Token-2022 para referrals no pipeline de carteira."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from smart_money_radar.data_sources.damm_v2_transaction_pipeline import (
    process_damm_v2_transaction,
)
from smart_money_radar.data_sources.solana_transaction_position import get_transaction_index
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    TOKEN_2022_PROGRAM_ID,
)
from smart_money_radar.data_sources.token2022_fee_absence_proof import (
    Token2022NoTransferFeeProof,
    build_no_transfer_fee_proof,
)
from smart_money_radar.data_sources.transaction_parser import PARSER_VERSION


@dataclass(frozen=True, slots=True)
class Token2022FeeProofResolution:
    proofs: tuple[Token2022NoTransferFeeProof, ...]
    unresolved_mints: tuple[str, ...]
    reasons: tuple[str, ...]


def _fetch_current_mint(endpoint: str, mint: str) -> tuple[str, bytes, int]:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "smr-token2022-mint-proof",
        "method": "getAccountInfo",
        "params": [mint, {"commitment": "finalized", "encoding": "base64"}],
    }, separators=(",", ":")).encode("utf-8")
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
        raise RuntimeError(f"falha ao consultar mint ({type(exc).__name__})") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("jsonrpc") != "2.0"
        or payload.get("id") != "smr-token2022-mint-proof"
    ):
        raise RuntimeError("envelope getAccountInfo inválido")
    if payload.get("error") is not None:
        raise RuntimeError("getAccountInfo rejeitado pelo RPC")
    result = payload.get("result")
    value = result.get("value") if isinstance(result, dict) else None
    context = result.get("context") if isinstance(result, dict) else None
    if not isinstance(value, dict) or not isinstance(context, dict):
        raise RuntimeError("mint atual ausente ou sem context")
    owner = value.get("owner")
    data = value.get("data")
    slot = context.get("slot")
    if (
        not isinstance(owner, str)
        or not isinstance(data, list)
        or len(data) != 2
        or data[1] != "base64"
        or isinstance(slot, bool)
        or not isinstance(slot, int)
        or slot < 0
    ):
        raise RuntimeError("formato de mint atual inválido")
    try:
        raw_data = base64.b64decode(data[0], validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("dados base64 do mint inválidos") from exc
    return owner, raw_data, slot


def resolve_token2022_no_fee_proofs(
    raw_transaction: dict,
    *,
    monitored_wallet: str,
    signature: str,
    rpc_endpoint: str,
) -> Token2022FeeProofResolution:
    """Cria proofs somente para referrals Token-2022 sem TransferFeeConfig.

    Qualquer falha de RPC/configuração deixa o mint em unresolved; o chamador
    continua fail-closed e não deve avançar checkpoint sem reconciliação.
    """
    if not isinstance(rpc_endpoint, str) or not rpc_endpoint.startswith("https://"):
        raise ValueError("rpc_endpoint deve usar HTTPS")
    payload = raw_transaction.get("result", raw_transaction) if isinstance(raw_transaction, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    preflight = process_damm_v2_transaction(
        raw_transaction,
        monitored_wallet=monitored_wallet,
        signature=signature,
        observed_at=datetime.now(timezone.utc),
        parser_version=PARSER_VERSION,
    )
    referral_mints = sorted({
        item.referral_transfer.mint
        for item in preflight.transfer_evidence
        if (
            item.status == "ATTRIBUTED"
            and item.referral_transfer is not None
            and item.referral_transfer.program_id == TOKEN_2022_PROGRAM_ID
            and item.referral_transfer.instruction_type != "TRANSFER_CHECKED_WITH_FEE"
            and isinstance(item.referral_transfer.mint, str)
        )
    })
    if not referral_mints:
        return Token2022FeeProofResolution((), (), ())
    slot = payload.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError("slot da transação inválido")

    transaction = payload.get("transaction")
    signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
    if not isinstance(signatures, list) or not signatures or signatures[0] != signature:
        raise ValueError("assinatura primária não confere para prova de taxa")
    tx_index = get_transaction_index(rpc_endpoint, slot, signature)

    proofs = []
    unresolved = []
    reasons = []
    for mint in referral_mints:
        try:
            owner, mint_data, snapshot_slot = _fetch_current_mint(rpc_endpoint, mint)
            proof = build_no_transfer_fee_proof(
                mint=mint,
                signature=signature,
                transaction_slot=slot,
                transaction_index=tx_index,
                current_snapshot_slot=snapshot_slot,
                owner=owner,
                mint_data=mint_data,
                transaction_successful=payload.get("meta", {}).get("err") is None,
                mint_transfer_observed=any(
                    transfer.execution_status == "EXECUTED"
                    and transfer.program_id == TOKEN_2022_PROGRAM_ID
                    and transfer.mint == mint
                    for transfer in preflight.transfers
                ),
            )
        except Exception as exc:
            unresolved.append(mint)
            reasons.append(f"{mint}: {type(exc).__name__}: {exc}")
            continue
        proofs.append(proof)
    return Token2022FeeProofResolution(
        tuple(proofs), tuple(unresolved), tuple(reasons)
    )
