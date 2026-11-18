"""Associação conservadora entre swaps DAMM v2 e seus Event CPI EvtSwap2.

O módulo identifica a relação estrutural dentro do mesmo grupo externo de
innerInstructions. Não reconstrói quantidades econômicas, não reconcilia SPL/
Token-2022 e não cria SwapObservation.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from smart_money_radar.data_sources.damm_v2_decoder import (
    METEORA_DAMM_V2_PROGRAM_ID,
    DammV2EvtSwap2,
    DammV2SwapInstruction,
    decode_damm_v2_evt_swap2,
    decode_damm_v2_instruction,
)


ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
AssociationStatus = Literal["MATCHED", "EVENT_MISSING", "AMBIGUOUS", "UNMATCHED_EVENT"]


@dataclass(frozen=True)
class DammV2SwapEventAssociation:
    status: AssociationStatus
    instruction_index: int | None
    inner_instruction_index: int | None
    cpi_path: tuple[int, ...] | None
    stack_height: int | None
    instruction: DammV2SwapInstruction | None
    event_inner_instruction_index: int | None
    event_cpi_path: tuple[int, ...] | None
    event_stack_height: int | None
    event: DammV2EvtSwap2 | None


@dataclass(frozen=True)
class _InstructionRef:
    instruction_index: int
    inner_instruction_index: int | None
    cpi_path: tuple[int, ...] | None
    stack_height: int | None
    instruction: DammV2SwapInstruction | None = None
    event: DammV2EvtSwap2 | None = None


def _decode_base58(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("instruction data deve ser Base58 não vazio")
    number = 0
    try:
        for char in value:
            number = number * 58 + ALPHABET.index(char)
    except ValueError as exc:
        raise ValueError("instruction data contém Base58 inválido") from exc
    body = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + body


def _account_keys(message: Mapping[str, Any], meta: Mapping[str, Any]) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("message.accountKeys ausente ou inválido")
    parsed = any(isinstance(item, dict) for item in raw)
    if parsed and not all(isinstance(item, dict) for item in raw):
        raise ValueError("message.accountKeys mistura formatos jsonParsed e compiled")
    keys: list[str] = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("accountKeys contém chave inválida")
        keys.append(key)
    if not parsed:
        loaded = meta.get("loadedAddresses") or {}
        if not isinstance(loaded, dict):
            raise ValueError("meta.loadedAddresses inválido")
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ValueError(f"loadedAddresses.{field} inválido")
            keys.extend(values)
    return keys


def _program_id(item: Mapping[str, Any], keys: list[str]) -> str | None:
    value = item.get("programId")
    if isinstance(value, str) and value:
        return value
    index = item.get("programIdIndex")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(keys):
        return None
    return keys[index]


def _inner_paths(instructions: list[Any]) -> list[tuple[tuple[int, ...] | None, int | None]]:
    """Deriva hierarquia apenas enquanto todos os pais imediatos são demonstráveis.

    Um stackHeight ausente/inválido invalida a hierarquia restante do grupo;
    não se tenta adivinhar se uma chamada posterior pertence ao root ou a um
    CPI anterior.
    """
    stack_paths: dict[int, tuple[int, ...]] = {1: ()}
    sibling_counts: dict[tuple[tuple[int, ...], int], int] = {}
    result = []
    hierarchy_valid = True
    for item in instructions:
        height = item.get("stackHeight") if isinstance(item, dict) else None
        if (
            not hierarchy_valid
            or isinstance(height, bool)
            or not isinstance(height, int)
            or height < 2
        ):
            hierarchy_valid = False
            stack_paths.clear()
            result.append((None, height if isinstance(height, int) and not isinstance(height, bool) else None))
            continue
        parent = stack_paths.get(height - 1)
        if parent is None:
            hierarchy_valid = False
            stack_paths.clear()
            result.append((None, height))
            continue
        for known in tuple(stack_paths):
            if known >= height:
                del stack_paths[known]
        key = (parent, height)
        sibling = sibling_counts.get(key, 0)
        sibling_counts[key] = sibling + 1
        path = parent + (sibling,)
        stack_paths[height] = path
        result.append((path, height))
    return result


def _decode_ref(
    item: Mapping[str, Any],
    keys: list[str],
    outer_index: int,
    inner_index: int | None,
    cpi_path: tuple[int, ...] | None,
    stack_height: int | None,
) -> tuple[_InstructionRef | None, _InstructionRef | None]:
    if _program_id(item, keys) != METEORA_DAMM_V2_PROGRAM_ID:
        return None, None
    encoded = item.get("data")
    if not isinstance(encoded, str) or not encoded:
        return None, None
    data = _decode_base58(encoded)
    swap = decode_damm_v2_instruction(METEORA_DAMM_V2_PROGRAM_ID, data)
    event = decode_damm_v2_evt_swap2(METEORA_DAMM_V2_PROGRAM_ID, data)
    common = dict(
        instruction_index=outer_index,
        inner_instruction_index=inner_index,
        cpi_path=cpi_path,
        stack_height=stack_height,
    )
    swap_ref = _InstructionRef(**common, instruction=swap) if swap is not None else None
    event_ref = _InstructionRef(**common, event=event) if event is not None else None
    return swap_ref, event_ref


def analyze_damm_v2_swap_events(
    raw_transaction: dict[str, Any],
) -> list[DammV2SwapEventAssociation]:
    """Associa cada swap DAMM v2 a no máximo um EvtSwap2 comprovadamente descendente.

    A correspondência exige mesmo outer instruction group, evento posterior,
    stackHeight exatamente um nível acima e caminho CPI do evento cujo pai é
    exatamente o caminho da instrução swap. Sem hierarquia comprovável, não
    associa. Eventos não são emitidos como swaps independentes.
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação precisa ser um objeto")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    tx = payload.get("transaction")
    meta = payload.get("meta")
    if not isinstance(tx, dict) or not isinstance(meta, dict):
        return []
    if meta.get("err") is not None:
        return []
    message = tx.get("message")
    if not isinstance(message, dict):
        return []
    outer = message.get("instructions", [])
    if not isinstance(outer, list):
        raise ValueError("message.instructions inválido")
    keys = _account_keys(message, meta)

    groups = meta.get("innerInstructions") or []
    if not isinstance(groups, list):
        raise ValueError("meta.innerInstructions inválido")
    by_index: dict[int, list[Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("grupo innerInstructions inválido")
        index = group.get("index")
        nested = group.get("instructions")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(outer)
            or not isinstance(nested, list)
            or index in by_index
        ):
            raise ValueError("grupo innerInstructions inconsistente")
        by_index[index] = nested

    swaps: list[_InstructionRef] = []
    events: list[_InstructionRef] = []
    for outer_index, outer_item in enumerate(outer):
        if isinstance(outer_item, dict):
            swap_ref, event_ref = _decode_ref(
                outer_item, keys, outer_index, None, (), 1
            )
            if swap_ref is not None:
                swaps.append(swap_ref)
            if event_ref is not None:
                events.append(event_ref)

        nested = by_index.get(outer_index, [])
        paths = _inner_paths(nested)
        for inner_index, (item, path_info) in enumerate(zip(nested, paths)):
            if not isinstance(item, dict):
                continue
            path, height = path_info
            swap_ref, event_ref = _decode_ref(
                item, keys, outer_index, inner_index, path, height
            )
            if swap_ref is not None:
                swaps.append(swap_ref)
            if event_ref is not None:
                events.append(event_ref)

    candidates_by_event: dict[int, list[int]] = {}
    events_by_swap: dict[int, list[int]] = {i: [] for i in range(len(swaps))}
    for event_index, event_ref in enumerate(events):
        candidates = []
        if event_ref.cpi_path is not None and event_ref.stack_height is not None:
            for swap_index, swap_ref in enumerate(swaps):
                if swap_ref.instruction_index != event_ref.instruction_index:
                    continue
                if swap_ref.cpi_path is None or swap_ref.stack_height is None:
                    continue
                if event_ref.stack_height != swap_ref.stack_height + 1:
                    continue
                if event_ref.cpi_path[:-1] != swap_ref.cpi_path:
                    continue
                if (
                    swap_ref.inner_instruction_index is not None
                    and event_ref.inner_instruction_index is not None
                    and event_ref.inner_instruction_index <= swap_ref.inner_instruction_index
                ):
                    continue
                candidates.append(swap_index)
        candidates_by_event[event_index] = candidates
        if len(candidates) == 1:
            events_by_swap[candidates[0]].append(event_index)

    output: list[DammV2SwapEventAssociation] = []
    matched_event_indexes: set[int] = set()
    for swap_index, swap_ref in enumerate(swaps):
        event_indexes = events_by_swap[swap_index]
        possible_event_indexes = [
            event_index
            for event_index, candidates in candidates_by_event.items()
            if swap_index in candidates
        ]
        if len(event_indexes) == 1 and len(possible_event_indexes) == 1:
            event_index = event_indexes[0]
            event_ref = events[event_index]
            if len(candidates_by_event[event_index]) == 1:
                matched_event_indexes.add(event_index)
                output.append(DammV2SwapEventAssociation(
                    "MATCHED", swap_ref.instruction_index,
                    swap_ref.inner_instruction_index, swap_ref.cpi_path,
                    swap_ref.stack_height, swap_ref.instruction,
                    event_ref.inner_instruction_index, event_ref.cpi_path,
                    event_ref.stack_height, event_ref.event,
                ))
                continue
        if possible_event_indexes:
            output.append(DammV2SwapEventAssociation(
                "AMBIGUOUS", swap_ref.instruction_index,
                swap_ref.inner_instruction_index, swap_ref.cpi_path,
                swap_ref.stack_height, swap_ref.instruction,
                None, None, None, None,
            ))
        else:
            output.append(DammV2SwapEventAssociation(
                "EVENT_MISSING", swap_ref.instruction_index,
                swap_ref.inner_instruction_index, swap_ref.cpi_path,
                swap_ref.stack_height, swap_ref.instruction,
                None, None, None, None,
            ))

    for event_index, event_ref in enumerate(events):
        if event_index in matched_event_indexes:
            continue
        candidates = candidates_by_event[event_index]
        status: AssociationStatus = "AMBIGUOUS" if candidates else "UNMATCHED_EVENT"
        output.append(DammV2SwapEventAssociation(
            status, None, None, None, None, None,
            event_ref.inner_instruction_index, event_ref.cpi_path,
            event_ref.stack_height, event_ref.event,
        ))
    return output
