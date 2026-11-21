"""Launch receipts for historical CPMM swaps with local transaction evidence."""

from datetime import datetime
from decimal import Decimal, localcontext
import json

from smart_money_radar.data_sources.raydium_cpmm_analyzer import RaydiumCpmmDecodedSwap
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID, SolanaTokenTransfer, decode_solana_token_transfers,
)
from smart_money_radar.services.cpmm_swap_event_evidence import reconcile_observed_swap_event
from smart_money_radar.services.historical_cpmm_state import HistoricalVaultBalance


def reconcile_launch_historical_swap(
    *,
    transaction_raw: bytes,
    manifest: dict,
    cutoff: datetime,
    swap: RaydiumCpmmDecodedSwap,
    quote_mint: str,
    pool_decimals: dict[str, int],
) -> dict:
    """Reconcile recorded event amounts with direct SPL transfers and vault deltas."""
    receipt = {
        "status": "UNAVAILABLE",
        "historical_poolstate_snapshot_verified": False,
        "historical_ammconfig_snapshot_verified": False,
        "historical_fee_rates_verified": False,
        "quote_available_before_swap": False,
        "executable_quote_proven": False,
        "replay_eligible": False,
        "independently_authenticated": False,
        "operational_authorized": False,
    }
    accounts = swap.accounts
    try:
        proof = reconcile_observed_swap_event(
            transaction_raw=transaction_raw, manifest=manifest, cutoff=cutoff,
        )
        transfers = decode_solana_token_transfers(json.loads(transaction_raw))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
        return dict(receipt, reason="historical_event_or_vault_proof_unavailable")

    if (swap.inner_instruction_index is not None
            or accounts.input_token_program != SPL_TOKEN_PROGRAM_ID
            or accounts.output_token_program != SPL_TOKEN_PROGRAM_ID
            or manifest.get("requested_commitment") != "finalized"):
        return dict(receipt, reason="historical_swap_evidence_form_unsupported")
    state = proof.transaction_state
    if state is None:
        return dict(receipt, reason="historical_transaction_state_unavailable")
    if (proof.pool != accounts.pool_state
            or proof.instruction_index != swap.instruction_index
            or state.amm_config != accounts.amm_config
            or not isinstance(state.source_id, str) or state.source_id.strip() in ("", "UNKNOWN")
            or quote_mint not in (proof.event.input_mint, proof.event.output_mint)):
        return dict(receipt, status="CONFLICTED", reason="historical_swap_identity_mismatch")
    input_vault = state.input_vault
    output_vault = state.output_vault
    vault_addresses = {accounts.input_vault, accounts.output_vault}
    vault_transfers = [
        transfer for transfer in transfers
        if {transfer.source_account, transfer.destination_account} & vault_addresses
    ]
    if not vault_transfers:
        return dict(receipt, reason="historical_vault_transfers_unavailable")
    if len(vault_transfers) != 2:
        return dict(receipt, reason="historical_vault_transfers_incomplete_or_ambiguous")

    event = proof.event
    transfer_in, transfer_out = vault_transfers
    if (
        not _matches_transfer(
            transfer_in, swap.instruction_index, input_vault,
            source=accounts.input_token_account, destination=accounts.input_vault,
            authority=accounts.payer, vault_owner=accounts.authority,
            amount_raw=event.input_amount_raw,
        )
        or not _matches_transfer(
            transfer_out, swap.instruction_index, output_vault,
            source=accounts.output_vault, destination=accounts.output_token_account,
            authority=accounts.authority, vault_owner=accounts.authority,
            amount_raw=event.output_amount_raw,
        )
        or transfer_in.inner_instruction_index >= transfer_out.inner_instruction_index
    ):
        return dict(receipt, status="CONFLICTED", reason="historical_event_transfer_mismatch")
    if any(pool_decimals.get(vault.mint) != vault.decimals for vault in (input_vault, output_vault)):
        return dict(receipt, status="CONFLICTED", reason="historical_and_prospective_mint_decimals_disagree")

    input_is_quote = input_vault.mint == quote_mint
    quote_raw, token_raw = (
        (transfer_in.amount_raw, transfer_out.amount_raw) if input_is_quote
        else (transfer_out.amount_raw, transfer_in.amount_raw)
    )
    quote_decimals, token_decimals = (
        (input_vault.decimals, output_vault.decimals) if input_is_quote
        else (output_vault.decimals, input_vault.decimals)
    )
    with localcontext() as ctx:
        ctx.prec = 50
        quote_amount = Decimal(quote_raw).scaleb(-quote_decimals)
        token_amount = Decimal(token_raw).scaleb(-token_decimals)
        average_price = quote_amount / token_amount

    return dict(
        receipt, status="OBSERVED_EVENT_AND_TRANSFERS_RECONCILED_UNATTESTED",
        signature=proof.signature, slot=proof.slot, pool=proof.pool,
        amm_config=state.amm_config,
        source_id=state.source_id, observed_at=state.observed_at.isoformat(),
        available_at=proof.observation_available_at.isoformat(),
        transaction_raw_sha256=proof.transaction_raw_sha256,
        event_raw_sha256=proof.event_raw_sha256,
        instruction_index=proof.instruction_index,
        side="BUY" if input_is_quote else "SELL",
        transfer_scope="INSTRUCTION_TRANSFERS_AND_TRANSACTION_VAULT_DELTAS",
        input_transfer=_transfer_receipt(transfer_in),
        output_transfer=_transfer_receipt(transfer_out),
        input_vault_pre_raw=str(input_vault.pre_raw),
        input_vault_post_raw=str(input_vault.post_raw),
        output_vault_pre_raw=str(output_vault.pre_raw),
        output_vault_post_raw=str(output_vault.post_raw),
        vault_balance_scope=state.balance_scope,
        event_effective_input_reserve_before_raw=str(event.input_vault_before_raw),
        event_effective_output_reserve_before_raw=str(event.output_vault_before_raw),
        event_reserve_provenance="EMITTED_SWAP_EVENT",
        decimals_provenance="HISTORICAL_VAULT_BALANCES_AND_SPL_TRANSFER_CHECKED",
        quote_amount_raw=str(quote_raw), token_amount_raw=str(token_raw),
        quote_amount_normalized=str(quote_amount), token_amount_normalized=str(token_amount),
        observed_average_execution_quote_per_token=str(average_price),
        calculated_gross_output_raw=str(proof.calculated_gross_output_raw),
        reconciled_output_difference_raw=str(proof.difference_raw),
        trade_fee_raw=str(event.trade_fee_raw), trade_fee_mint=input_vault.mint,
        creator_fee_raw=str(event.creator_fee_raw), creator_fee_mint=output_vault.mint,
        input_transfer_fee_raw=str(event.input_transfer_fee_raw),
        output_transfer_fee_raw=str(event.output_transfer_fee_raw),
        solana_network_fee_lamports=str(state.solana_network_fee_lamports),
    )


def _matches_transfer(
    transfer: SolanaTokenTransfer,
    instruction_index: int,
    vault: HistoricalVaultBalance,
    *,
    source: str,
    destination: str,
    authority: str,
    vault_owner: str,
    amount_raw: int,
) -> bool:
    return (
        source != destination
        and vault.address in (source, destination)
        and vault.owner == vault_owner
        and transfer.source_account == source
        and transfer.destination_account == destination
        and transfer.authority == authority
        and transfer.program_id == vault.token_program == SPL_TOKEN_PROGRAM_ID
        and transfer.instruction_index == instruction_index
        and transfer.inner_instruction_index is not None
        and transfer.stack_height == 2
        and transfer.cpi_path_valid
        and transfer.execution_status == "EXECUTED"
        and transfer.instruction_type == "TRANSFER_CHECKED"
        and transfer.mint == vault.mint
        and transfer.decimals == vault.decimals
        and transfer.amount_raw == amount_raw
        and transfer.fee_amount_raw is None
    )


def _transfer_receipt(transfer: SolanaTokenTransfer) -> dict:
    return {
        "mint": transfer.mint,
        "amount_raw": str(transfer.amount_raw),
        "decimals": transfer.decimals,
        "source_account": transfer.source_account,
        "destination_account": transfer.destination_account,
        "program_id": transfer.program_id,
        "inner_instruction_index": transfer.inner_instruction_index,
    }
