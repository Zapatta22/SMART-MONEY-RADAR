"""Decodifica operações roteadas PumpSwap multi-hop e Meteora DLMM swap2."""
from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
    decode_solana_token_transfers,
)
from smart_money_radar.domain.models import (
    SwapClassification,
    SwapEvidence,
    SwapObservation,
    build_swap_operation_id,
)
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle


PUMP_SWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
METEORA_DLMM_PROGRAM_ID = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"

PUMP_MULTI_HOP_SWAP_DISCRIMINATOR = bytes([43, 100, 73, 19, 233, 246, 111, 148])
PUMP_TRADE_EVENT_DISCRIMINATOR = bytes([189, 219, 127, 211, 78, 230, 97, 238])
PUMP_AMM_SELL_EVENT_DISCRIMINATOR = bytes([62, 47, 55, 10, 165, 3, 220, 42])
DLMM_SWAP2_INSTRUCTION_DISCRIMINATOR = bytes([65, 75, 63, 76, 235, 91, 91, 136])
DLMM_SWAP2_EVENT_DISCRIMINATOR = bytes([46, 116, 82, 215, 148, 27, 84, 77])

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
PARSER_VERSION = "smr-routed-venues-v1"


class _BorshReader:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0

    @property
    def remaining(self) -> bytes:
        return self.data[self.position:]

    def read(self, size: int) -> bytes:
        if size < 0 or self.position + size > len(self.data):
            raise ValueError("payload Borsh truncado")
        value = self.data[self.position:self.position + size]
        self.position += size
        return value

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def u128(self) -> int:
        return int.from_bytes(self.read(16), "little", signed=False)

    def i128(self) -> int:
        return int.from_bytes(self.read(16), "little", signed=True)

    def boolean(self) -> bool:
        value = self.u8()
        if value not in (0, 1):
            raise ValueError("boolean Borsh inválido")
        return bool(value)

    def pubkey(self) -> str:
        return _b58encode(self.read(32))

    def string(self) -> str:
        size = self.u32()
        try:
            return self.read(size).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("string Borsh inválida") from exc


def _b58decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("data base58 ausente")
    number = 0
    for char in value:
        try:
            digit = ALPHABET.index(char)
        except ValueError as exc:
            raise ValueError("caractere base58 inválido") from exc
        number = number * 58 + digit
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + body


def _b58encode(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    leading = len(value) - len(value.lstrip(b"\x00"))
    return "1" * leading + (encoded or "")


@dataclass(frozen=True, slots=True)
class PumpTradeEvent:
    mint: str
    sol_amount: int
    token_amount: int
    is_buy: bool
    user: str
    timestamp: int
    fee: int
    creator: str
    creator_fee: int
    ix_name: str
    cashback: int
    buyback: int
    quote_mint: str
    quote_amount: int
    trailing_bytes: bytes


@dataclass(frozen=True, slots=True)
class PumpAmmSellEvent:
    timestamp: int
    base_amount_in: int
    quote_amount_out: int
    user_quote_amount_out: int
    pool: str
    user: str
    user_base_token_account: str
    user_quote_token_account: str
    lp_fee: int
    protocol_fee: int
    coin_creator_fee: int
    cashback: int
    buyback: int
    trailing_bytes: bytes


@dataclass(frozen=True, slots=True)
class MeteoraDlmmSwap2Event:
    lb_pair: str
    from_address: str
    start_bin_id: int
    end_bin_id: int
    swap_for_y: bool
    fee_bps: int
    amount_in: int
    amount_left: int
    amount_out: int
    mm_fee: int
    protocol_fee: int
    limit_order_fee: int
    host_fee: int
    fees_on_input: bool
    fees_on_token_x: bool
    trailing_bytes: bytes


@dataclass(frozen=True, slots=True)
class DecodedAnchorEvent:
    program_id: str
    name: str
    value: PumpTradeEvent | PumpAmmSellEvent | MeteoraDlmmSwap2Event


@dataclass(frozen=True, slots=True)
class PumpMultiHopSwapInstruction:
    outer_index: int
    inner_index: int
    cpi_path: tuple[int, ...]
    accounts: tuple[str, ...]
    amount_in: int
    min_amount_out: int


@dataclass(frozen=True, slots=True)
class MeteoraDlmmSwap2Instruction:
    outer_index: int
    inner_index: int
    cpi_path: tuple[int, ...]
    accounts: tuple[str, ...]
    amount_in: int
    min_amount_out: int
    remaining_accounts_info: bytes


@dataclass(frozen=True, slots=True)
class RoutedVenueDecodeResult:
    bundles: tuple[SwapDomainBundle, ...]
    unresolved: tuple[str, ...]


def decode_pump_trade_event(data: bytes) -> PumpTradeEvent:
    if data[:8] != PUMP_TRADE_EVENT_DISCRIMINATOR:
        raise ValueError("discriminator não é Pump TradeEvent")
    reader = _BorshReader(data[8:])
    mint = reader.pubkey()
    sol_amount = reader.u64()
    token_amount = reader.u64()
    is_buy = reader.boolean()
    user = reader.pubkey()
    timestamp = reader.i64()
    reader.u64()  # virtual_sol_reserves
    reader.u64()  # virtual_token_reserves
    reader.u64()  # real_sol_reserves
    reader.u64()  # real_token_reserves
    reader.pubkey()  # fee_recipient
    reader.u64()  # fee_basis_points
    fee = reader.u64()
    creator = reader.pubkey()
    reader.u64()  # creator_fee_basis_points
    creator_fee = reader.u64()
    reader.boolean()  # track_volume
    reader.u64()  # total_unclaimed_tokens
    reader.u64()  # total_claimed_tokens
    reader.u64()  # current_sol_volume
    reader.i64()  # last_update_timestamp
    ix_name = reader.string()
    reader.boolean()  # mayhem_mode
    reader.u64()  # cashback_fee_basis_points
    cashback = reader.u64()
    reader.u64()  # buyback_fee_basis_points
    buyback = reader.u64()
    shareholder_count = reader.u32()
    if shareholder_count > 1024:
        raise ValueError("vetor shareholders acima do limite")
    for _ in range(shareholder_count):
        reader.pubkey()
        reader.u16()
    quote_mint = reader.pubkey()
    quote_amount = reader.u64()
    reader.u64()  # virtual_quote_reserves
    reader.u64()  # real_quote_reserves
    reader.u64()  # holder_rewards_bps
    reader.u64()  # holder_rewards
    reader.u64()  # creator_fee_unclaimed
    if len(reader.remaining) > 16:
        raise ValueError("extensão desconhecida excessiva em Pump TradeEvent")
    return PumpTradeEvent(
        mint, sol_amount, token_amount, is_buy, user, timestamp, fee,
        creator, creator_fee, ix_name, cashback, buyback, quote_mint,
        quote_amount, reader.remaining,
    )


def decode_pump_amm_sell_event(data: bytes) -> PumpAmmSellEvent:
    if data[:8] != PUMP_AMM_SELL_EVENT_DISCRIMINATOR:
        raise ValueError("discriminator não é Pump AMM SellEvent")
    reader = _BorshReader(data[8:])
    timestamp = reader.i64()
    base_amount_in = reader.u64()
    reader.u64()  # min_quote_amount_out
    reader.u64()  # user_base_token_reserves
    reader.u64()  # user_quote_token_reserves
    reader.u64()  # pool_base_token_reserves
    reader.u64()  # pool_quote_token_reserves
    quote_amount_out = reader.u64()
    reader.u64()  # lp_fee_basis_points
    lp_fee = reader.u64()
    reader.u64()  # protocol_fee_basis_points
    protocol_fee = reader.u64()
    reader.u64()  # quote_amount_out_without_lp_fee
    user_quote_amount_out = reader.u64()
    pool = reader.pubkey()
    user = reader.pubkey()
    user_base_token_account = reader.pubkey()
    user_quote_token_account = reader.pubkey()
    reader.pubkey()  # protocol_fee_recipient
    reader.pubkey()  # protocol_fee_recipient_token_account
    reader.pubkey()  # coin_creator
    reader.u64()  # coin_creator_fee_basis_points
    coin_creator_fee = reader.u64()
    reader.u64()  # cashback_fee_basis_points
    cashback = reader.u64()
    reader.u64()  # buyback_fee_basis_points
    buyback = reader.u64()
    reader.i128()  # virtual_quote_reserves
    reader.boolean()  # can_boost
    reader.u64()  # base_supply
    reader.u64()  # holder_rewards_bps
    reader.u64()  # holder_rewards
    reader.u64()  # creator_fee_unclaimed
    if len(reader.remaining) > 16:
        raise ValueError("extensão desconhecida excessiva em Pump AMM SellEvent")
    return PumpAmmSellEvent(
        timestamp, base_amount_in, quote_amount_out, user_quote_amount_out,
        pool, user, user_base_token_account, user_quote_token_account,
        lp_fee, protocol_fee, coin_creator_fee, cashback, buyback,
        reader.remaining,
    )


def decode_meteora_dlmm_swap2_event(data: bytes) -> MeteoraDlmmSwap2Event:
    if data[:8] != DLMM_SWAP2_EVENT_DISCRIMINATOR:
        raise ValueError("discriminator não é Meteora DLMM Swap2Evt")
    reader = _BorshReader(data[8:])
    lb_pair = reader.pubkey()
    from_address = reader.pubkey()
    start_bin_id = reader.i32()
    end_bin_id = reader.i32()
    swap_for_y = reader.boolean()
    fee_bps = reader.u128()
    amount_in = reader.u64()
    amount_left = reader.u64()
    amount_out = reader.u64()
    mm_fee = reader.u64()
    protocol_fee = reader.u64()
    limit_order_fee = reader.u64()
    host_fee = reader.u64()
    fees_on_input = reader.boolean()
    fees_on_token_x = reader.boolean()
    return MeteoraDlmmSwap2Event(
        lb_pair, from_address, start_bin_id, end_bin_id, swap_for_y,
        fee_bps, amount_in, amount_left, amount_out, mm_fee, protocol_fee,
        limit_order_fee, host_fee, fees_on_input, fees_on_token_x,
        reader.remaining,
    )


def decode_anchor_events(raw_transaction: dict[str, Any]) -> tuple[DecodedAnchorEvent, ...]:
    payload = raw_transaction.get("result", raw_transaction)
    meta = payload.get("meta") if isinstance(payload, dict) else None
    logs = meta.get("logMessages") if isinstance(meta, dict) else None
    if not isinstance(logs, list):
        return ()
    decoded = []
    for line in logs:
        if not isinstance(line, str) or not line.startswith("Program data: "):
            continue
        encoded = line[len("Program data: "):].strip()
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            continue
        discriminator = data[:8]
        try:
            if discriminator == PUMP_TRADE_EVENT_DISCRIMINATOR:
                decoded.append(DecodedAnchorEvent(
                    PUMP_PROGRAM_ID, "TradeEvent", decode_pump_trade_event(data)
                ))
            elif discriminator == PUMP_AMM_SELL_EVENT_DISCRIMINATOR:
                decoded.append(DecodedAnchorEvent(
                    PUMP_SWAP_PROGRAM_ID, "SellEvent", decode_pump_amm_sell_event(data)
                ))
            elif discriminator == DLMM_SWAP2_EVENT_DISCRIMINATOR:
                decoded.append(DecodedAnchorEvent(
                    METEORA_DLMM_PROGRAM_ID, "Swap2Evt",
                    decode_meteora_dlmm_swap2_event(data),
                ))
        except (ValueError, struct.error):
            continue
    return tuple(decoded)


def _account_keys(payload: Mapping[str, Any]) -> list[str]:
    transaction = payload.get("transaction")
    message = transaction.get("message") if isinstance(transaction, dict) else None
    raw_keys = message.get("accountKeys") if isinstance(message, dict) else None
    if not isinstance(raw_keys, list):
        raise ValueError("message.accountKeys ausente")
    keys = [
        item.get("pubkey") if isinstance(item, dict) else item
        for item in raw_keys
    ]
    if not all(isinstance(item, str) and item for item in keys):
        raise ValueError("accountKeys inválido")
    meta = payload.get("meta")
    loaded = meta.get("loadedAddresses") if isinstance(meta, dict) else None
    if isinstance(loaded, dict):
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if isinstance(values, list):
                keys.extend(value for value in values if isinstance(value, str))
    return keys


def _resolve_program_id(instruction: Mapping[str, Any], keys: list[str]) -> str | None:
    direct = instruction.get("programId")
    if isinstance(direct, str):
        return direct
    index = instruction.get("programIdIndex")
    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(keys):
        return keys[index]
    return None


def _resolve_accounts(instruction: Mapping[str, Any], keys: list[str]) -> tuple[str, ...]:
    accounts = instruction.get("accounts", [])
    if not isinstance(accounts, list):
        return ()
    resolved = []
    for account in accounts:
        if isinstance(account, int) and not isinstance(account, bool):
            if not 0 <= account < len(keys):
                return ()
            resolved.append(keys[account])
        elif isinstance(account, str):
            resolved.append(account)
        else:
            return ()
    return tuple(resolved)


def _token_account_metadata(payload: Mapping[str, Any], keys: list[str]) -> dict[str, tuple[str, str, int]]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return {}
    result: dict[str, tuple[str, str, int]] = {}
    for field in ("preTokenBalances", "postTokenBalances"):
        entries = meta.get(field, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            index = entry.get("accountIndex")
            owner = entry.get("owner")
            mint = entry.get("mint")
            amount = entry.get("uiTokenAmount")
            decimals = amount.get("decimals") if isinstance(amount, dict) else None
            if (
                isinstance(index, bool) or not isinstance(index, int)
                or not 0 <= index < len(keys)
                or not isinstance(owner, str) or not owner
                or not isinstance(mint, str) or not mint
                or isinstance(decimals, bool) or not isinstance(decimals, int)
            ):
                continue
            account = keys[index]
            value = (owner, mint, decimals)
            previous = result.get(account)
            if previous is not None and previous != value:
                result.pop(account, None)
                continue
            result[account] = value
    return result


def _net_transfer_amount(
    transfer: SolanaTokenTransfer,
    fee_proof_mints: set[str],
) -> int:
    if transfer.program_id == SPL_TOKEN_PROGRAM_ID:
        return transfer.amount_raw
    if transfer.program_id != TOKEN_2022_PROGRAM_ID:
        raise ValueError("programa de token não suportado")
    if transfer.instruction_type == "TRANSFER_CHECKED_WITH_FEE":
        if (
            isinstance(transfer.fee_amount_raw, bool)
            or not isinstance(transfer.fee_amount_raw, int)
            or not 0 <= transfer.fee_amount_raw <= transfer.amount_raw
        ):
            raise ValueError("fee Token-2022 explícita inválida")
        return transfer.amount_raw - transfer.fee_amount_raw
    if transfer.mint not in fee_proof_mints:
        raise ValueError("transferência Token-2022 sem prova de taxa")
    return transfer.amount_raw


def _classify(
    operation_id: str,
    input_mint: str,
    output_mint: str,
    reference_mints: set[str],
) -> SwapClassification:
    input_reference = input_mint in reference_mints
    output_reference = output_mint in reference_mints
    if input_reference and not output_reference:
        return SwapClassification(
            operation_id, "BUY", Decimal("1"),
            "Entrada em ativo de referência e saída no ativo adquirido.",
        )
    if output_reference and not input_reference:
        return SwapClassification(
            operation_id, "SELL", Decimal("1"),
            "Entrada no ativo vendido e saída em ativo de referência.",
        )
    return SwapClassification(
        operation_id, "UNKNOWN", Decimal("0"),
        "Não há exatamente um ativo de referência configurado para determinar BUY/SELL.",
    )


def _make_bundle(
    *,
    signature: str,
    wallet: str,
    observed_at: datetime,
    reference_mints: set[str],
    venue: str,
    program_id: str,
    instruction_index: int,
    cpi_path: tuple[int, ...],
    input_mint: str,
    output_mint: str,
    input_amount_raw: int,
    output_amount_raw: int,
    input_decimals: int,
    output_decimals: int,
    evidence: Iterable[str],
) -> SwapDomainBundle:
    operation_id = build_swap_operation_id(
        "solana", signature, instruction_index, cpi_path
    )
    observation = SwapObservation(
        operation_id=operation_id,
        chain="solana",
        wallet_address=wallet,
        signature=signature,
        input_mint=input_mint,
        output_mint=output_mint,
        input_amount=Decimal(input_amount_raw).scaleb(-input_decimals),
        output_amount=Decimal(output_amount_raw).scaleb(-output_decimals),
        observed_at=observed_at,
        parser_version=PARSER_VERSION,
    )
    classification = _classify(
        operation_id, input_mint, output_mint, reference_mints
    )
    swap_evidence = SwapEvidence(
        operation_id=operation_id,
        program_id=program_id,
        venue=venue,
        instruction_index=instruction_index,
        cpi_path=cpi_path,
        evidence=tuple(evidence),
    )
    return SwapDomainBundle(observation, classification, swap_evidence)


def _find_program_cpi_instructions(
    payload: Mapping[str, Any],
    keys: list[str],
) -> tuple[tuple[int, int, str, tuple[str, ...], str], ...]:
    meta = payload.get("meta")
    groups = meta.get("innerInstructions", []) if isinstance(meta, dict) else []
    if not isinstance(groups, list):
        return ()
    found = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        outer_index = group.get("index")
        instructions = group.get("instructions")
        if isinstance(outer_index, bool) or not isinstance(outer_index, int) or not isinstance(instructions, list):
            continue
        for inner_index, instruction in enumerate(instructions):
            if not isinstance(instruction, dict):
                continue
            program_id = _resolve_program_id(instruction, keys)
            data = instruction.get("data")
            if not isinstance(program_id, str) or not isinstance(data, str):
                continue
            try:
                decoded = _b58decode(data)
            except ValueError:
                continue
            accounts = _resolve_accounts(instruction, keys)
            if program_id == PUMP_SWAP_PROGRAM_ID and decoded[:8] == PUMP_MULTI_HOP_SWAP_DISCRIMINATOR:
                if len(decoded) != 24 or len(accounts) < 3:
                    continue
                amount_in, min_amount_out = struct.unpack("<QQ", decoded[8:24])
                found.append((
                    outer_index, inner_index, program_id, accounts,
                    f"pump_multi_hop:{amount_in}:{min_amount_out}",
                ))
            elif program_id == METEORA_DLMM_PROGRAM_ID and decoded[:8] == DLMM_SWAP2_INSTRUCTION_DISCRIMINATOR:
                if len(decoded) < 25 or len(accounts) < 16:
                    continue
                amount_in, min_amount_out = struct.unpack("<QQ", decoded[8:24])
                found.append((
                    outer_index, inner_index, program_id, accounts,
                    f"dlmm_swap2:{amount_in}:{min_amount_out}:{decoded[24:].hex()}",
                ))
    return tuple(found)


def decode_routed_venue_swaps(
    raw_transaction: dict[str, Any],
    *,
    signature: str,
    monitored_wallet: str,
    observed_at: datetime,
    reference_mints: Iterable[str] = (),
    transfer_fee_absence_proofs: Iterable[Any] = (),
) -> RoutedVenueDecodeResult:
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload de transação inválido")
    if payload.get("meta", {}).get("err") is not None:
        return RoutedVenueDecodeResult((), ("transação falhou on-chain",))
    keys = _account_keys(payload)
    metadata = _token_account_metadata(payload, keys)
    transfers = decode_solana_token_transfers({"result": payload})
    instructions = _find_program_cpi_instructions(payload, keys)
    events = decode_anchor_events({"result": payload})
    transaction_slot = payload.get("slot")
    proof_mints = {
        proof.mint for proof in transfer_fee_absence_proofs
        if (
            isinstance(getattr(proof, "mint", None), str)
            and getattr(proof, "signature", None) == signature
            and getattr(proof, "transaction_slot", None) == transaction_slot
            and isinstance(getattr(proof, "current_snapshot_slot", None), int)
            and proof.current_snapshot_slot >= transaction_slot
        )
    }
    references = set(reference_mints)
    bundles = []
    unresolved = []

    pump_instructions = [
        item for item in instructions if item[2] == PUMP_SWAP_PROGRAM_ID
        and item[4].startswith("pump_multi_hop:")
    ]
    pump_trade_events = [
        item.value for item in events
        if item.name == "TradeEvent" and isinstance(item.value, PumpTradeEvent)
    ]
    pump_sell_events = [
        item.value for item in events
        if item.name == "SellEvent" and isinstance(item.value, PumpAmmSellEvent)
    ]

    for outer_index, inner_index, program_id, accounts, encoded in pump_instructions:
        _, amount_text, min_text = encoded.split(":")
        amount_in = int(amount_text)
        min_amount_out = int(min_text)
        user, user_in_account, user_out_account = accounts[:3]
        if user != monitored_wallet:
            continue
        trade_matches = [
            event for event in pump_trade_events
            if event.user == user
            and event.ix_name == "multi_hop_swap"
            and event.token_amount == amount_in
            and event.mint in accounts
            and event.quote_mint in accounts
        ]
        sell_matches = [
            event for event in pump_sell_events
            if event.user == user
            and event.user_quote_token_account == user_out_account
            and event.pool in accounts
        ]
        if len(trade_matches) != 1 or len(sell_matches) != 1:
            unresolved.append(
                f"PumpSwap outer={outer_index}: TradeEvent/SellEvent sem associação única"
            )
            continue
        trade = trade_matches[0]
        sell = sell_matches[0]
        if trade.quote_mint not in accounts or sell.base_amount_in <= 0:
            unresolved.append(f"PumpSwap outer={outer_index}: mints/quantidades intermediárias inválidas")
            continue
        input_candidates = [
            transfer for transfer in transfers
            if transfer.instruction_index == outer_index
            and transfer.source_account == user_in_account
            and transfer.mint == trade.mint
            and transfer.amount_raw == amount_in
            and transfer.execution_status == "EXECUTED"
            and PUMP_SWAP_PROGRAM_ID in transfer.cpi_program_path
        ]
        # Resolve output mint from the final user token account metadata.
        output_info = metadata.get(user_out_account)
        if output_info is not None:
            output_mint = output_info[1]
            output_candidates = [
                transfer for transfer in transfers
                if transfer.instruction_index == outer_index
                and transfer.destination_account == user_out_account
                and transfer.mint == output_mint
                and transfer.execution_status == "EXECUTED"
                and PUMP_SWAP_PROGRAM_ID in transfer.cpi_program_path
            ]
        else:
            output_mint = ""
        intermediate_expected = (
            trade.quote_amount - trade.creator_fee - trade.fee
            - trade.cashback - trade.buyback
        )
        intermediate_candidates = [
            transfer for transfer in transfers
            if transfer.instruction_index == outer_index
            and transfer.mint == trade.quote_mint
            and transfer.amount_raw == sell.base_amount_in
            and transfer.execution_status == "EXECUTED"
            and PUMP_SWAP_PROGRAM_ID in transfer.cpi_program_path
        ]
        if output_mint == trade.mint:
            unresolved.append(f"PumpSwap outer={outer_index}: input e output mint iguais")
            continue
        if (
            len(input_candidates) != 1
            or len(output_candidates) != 1
            or len(intermediate_candidates) != 1
            or intermediate_expected != sell.base_amount_in
            or sell.user_quote_token_account != user_out_account
        ):
            unresolved.append(
                f"PumpSwap outer={outer_index}: input/output/intermediate transfer não confere com eventos"
            )
            continue
        input_transfer = input_candidates[0]
        output_transfer = output_candidates[0]
        intermediate_transfer = intermediate_candidates[0]
        _net_transfer_amount(input_transfer, proof_mints)
        output_net = _net_transfer_amount(output_transfer, proof_mints)
        intermediate_net = _net_transfer_amount(intermediate_transfer, proof_mints)
        if input_transfer.amount_raw != amount_in or output_net != sell.user_quote_amount_out or intermediate_net != sell.base_amount_in:
            unresolved.append(f"PumpSwap outer={outer_index}: net transfer diverge do evento")
            continue
        input_info = metadata.get(user_in_account)
        if (
            input_info is None or input_info[0] != monitored_wallet
            or output_info is None or output_info[0] != monitored_wallet
            or input_info[1] != trade.mint
            or output_info[1] != output_mint
        ):
            unresolved.append(f"PumpSwap outer={outer_index}: ownership/mint dos token accounts não confere")
            continue
        cpi_path = (inner_index,)
        operation_id = build_swap_operation_id(
            "solana", signature, outer_index, cpi_path
        )
        bundles.append(_make_bundle(
            signature=signature,
            wallet=monitored_wallet,
            observed_at=observed_at,
            reference_mints=references,
            venue="PumpSwap",
            program_id=PUMP_SWAP_PROGRAM_ID,
            instruction_index=outer_index,
            cpi_path=cpi_path,
            input_mint=trade.mint,
            output_mint=output_mint,
            input_amount_raw=input_transfer.amount_raw,
            output_amount_raw=output_net,
            input_decimals=input_info[2],
            output_decimals=output_info[2],
            evidence=(
                f"multi_hop_swap amount_in={amount_in} min_amount_out={min_amount_out}",
                f"Pump TradeEvent mint={trade.mint} quote_mint={trade.quote_mint} "
                f"token_amount={trade.token_amount} quote_amount={trade.quote_amount} "
                f"creator_fee={trade.creator_fee} ix_name={trade.ix_name}",
                f"Pump AMM SellEvent pool={sell.pool} base_amount_in={sell.base_amount_in} "
                f"user_quote_amount_out={sell.user_quote_amount_out} "
                f"protocol_fee={sell.protocol_fee} buyback={sell.buyback}",
                f"intermediate transfer {intermediate_transfer.source_account}->"
                f"{intermediate_transfer.destination_account} mint={trade.quote_mint} "
                f"net={intermediate_net}",
                f"input transfer {input_transfer.source_account}->{input_transfer.destination_account} "
                f"mint={trade.mint} gross={input_transfer.amount_raw}",
                f"output transfer {output_transfer.source_account}->{output_transfer.destination_account} "
                f"mint={output_mint} net={output_net}",
                f"event trailing bytes trade={len(trade.trailing_bytes)} sell={len(sell.trailing_bytes)}",
            ),
        ))

    dlmm_instructions = [
        item for item in instructions if item[2] == METEORA_DLMM_PROGRAM_ID
        and item[4].startswith("dlmm_swap2:")
    ]
    dlmm_events = [
        item.value for item in events
        if item.name == "Swap2Evt" and isinstance(item.value, MeteoraDlmmSwap2Event)
    ]
    for outer_index, inner_index, program_id, accounts, encoded in dlmm_instructions:
        _, amount_text, min_text, tail_hex = encoded.split(":")
        amount_in = int(amount_text)
        min_amount_out = int(min_text)
        lb_pair = accounts[0]
        user_in_account = accounts[4]
        user_out_account = accounts[5]
        token_x_mint = accounts[6]
        token_y_mint = accounts[7]
        user = accounts[10]
        if user != monitored_wallet:
            continue
        input_candidates = [
            transfer for transfer in transfers
            if transfer.instruction_index == outer_index
            and transfer.source_account == user_in_account
            and transfer.mint in {token_x_mint, token_y_mint}
            and transfer.amount_raw == amount_in
            and transfer.execution_status == "EXECUTED"
            and METEORA_DLMM_PROGRAM_ID in transfer.cpi_program_path
        ]
        if len(input_candidates) != 1:
            unresolved.append(f"Meteora DLMM outer={outer_index}: input transfer não identificado")
            continue
        input_transfer = input_candidates[0]
        output_mint = (
            token_y_mint if input_transfer.mint == token_x_mint else token_x_mint
        )
        output_candidates = [
            transfer for transfer in transfers
            if transfer.instruction_index == outer_index
            and transfer.destination_account == user_out_account
            and transfer.mint == output_mint
            and transfer.execution_status == "EXECUTED"
            and METEORA_DLMM_PROGRAM_ID in transfer.cpi_program_path
        ]
        if len(output_candidates) != 1:
            unresolved.append(f"Meteora DLMM outer={outer_index}: output transfer não identificado")
            continue
        output_transfer = output_candidates[0]
        _net_transfer_amount(input_transfer, proof_mints)
        output_net = _net_transfer_amount(output_transfer, proof_mints)
        input_info = metadata.get(user_in_account)
        output_info = metadata.get(user_out_account)
        if (
            input_info is None or input_info[0] != monitored_wallet
            or output_info is None or output_info[0] != monitored_wallet
            or input_info[1] != input_transfer.mint
            or output_info[1] != output_mint
            or input_transfer.amount_raw != amount_in
            or output_net < min_amount_out
        ):
            unresolved.append(f"Meteora DLMM outer={outer_index}: ownership/mint/amount não confere")
            continue
        cpi_path = (inner_index,)
        matching_events = [
            event for event in dlmm_events
            if event.lb_pair == lb_pair
            and event.from_address == user
            and event.amount_in == amount_in
            and event.amount_out == output_net
        ]
        event_evidence = (
            "Swap2Evt confirmado"
            if len(matching_events) == 1
            else "Swap2Evt ausente/ambíguo; output confirmado por transferência executada"
        )
        bundles.append(_make_bundle(
            signature=signature,
            wallet=monitored_wallet,
            observed_at=observed_at,
            reference_mints=references,
            venue="Meteora DLMM",
            program_id=METEORA_DLMM_PROGRAM_ID,
            instruction_index=outer_index,
            cpi_path=cpi_path,
            input_mint=input_transfer.mint,
            output_mint=output_mint,
            input_amount_raw=input_transfer.amount_raw,
            output_amount_raw=output_net,
            input_decimals=input_info[2],
            output_decimals=output_info[2],
            evidence=(
                f"swap2 lb_pair={lb_pair} amount_in={amount_in} "
                f"min_amount_out={min_amount_out} remaining_accounts_info={tail_hex}",
                f"input transfer {input_transfer.source_account}->{input_transfer.destination_account} "
                f"mint={input_transfer.mint} gross={input_transfer.amount_raw}",
                f"output transfer {output_transfer.source_account}->{output_transfer.destination_account} "
                f"mint={output_mint} net={output_net}",
                event_evidence,
            ),
        ))
    return RoutedVenueDecodeResult(tuple(bundles), tuple(unresolved))
