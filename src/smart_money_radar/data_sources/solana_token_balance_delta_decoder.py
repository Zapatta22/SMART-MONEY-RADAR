"""Decodificação conservadora de deltas pre/post de token accounts Solana.

Não atribui deltas a swaps individuais. Um delta é agregado à transação e
precisa de análise adicional antes de ser associado a uma operação.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal


DeltaIssueCode = Literal[
    "META_MISSING",
    "TRANSACTION_FAILED",
    "EXECUTION_STATUS_UNKNOWN",
    "ACCOUNT_KEYS_INVALID",
    "SNAPSHOTS_MISSING",
    "SNAPSHOT_ENTRY_INVALID",
    "DUPLICATE_ACCOUNT_INDEX",
    "ACCOUNT_INDEX_UNRESOLVED",
    "SNAPSHOT_SIDE_MISSING",
    "MINT_MISMATCH",
    "DECIMALS_MISMATCH",
    "OWNER_MISMATCH",
    "AMOUNT_INVALID",
]


@dataclass(frozen=True)
class SolanaTokenAccountBalanceDelta:
    account_index: int
    token_account: str
    mint: str
    owner: str | None
    pre_amount_raw: int
    post_amount_raw: int
    delta_raw: int
    decimals: int


@dataclass(frozen=True)
class SolanaTokenBalanceDeltaIssue:
    account_index: int | None
    code: DeltaIssueCode


@dataclass(frozen=True)
class SolanaTokenBalanceDeltaResult:
    deltas: tuple[SolanaTokenAccountBalanceDelta, ...]
    issues: tuple[SolanaTokenBalanceDeltaIssue, ...]

    @property
    def complete(self) -> bool:
        return not self.issues


def _account_keys(message: Mapping[str, Any], meta: Mapping[str, Any]) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("message.accountKeys ausente ou inválido")
    parsed_keys = any(isinstance(item, dict) for item in raw)
    keys: list[str] = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("accountKeys contém chave inválida")
        keys.append(key)
    if not parsed_keys:
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


def _amount(entry: Mapping[str, Any]) -> tuple[int, int] | None:
    token_amount = entry.get("uiTokenAmount")
    if not isinstance(token_amount, dict):
        return None
    raw = token_amount.get("amount")
    decimals = token_amount.get("decimals")
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (str, int))
        or isinstance(decimals, bool)
        or not isinstance(decimals, int)
        or not 0 <= decimals <= 255
    ):
        return None
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        return None
    if amount < 0 or str(amount) != str(raw).strip():
        return None
    return amount, decimals


def _snapshot_map(
    entries: Any,
) -> tuple[dict[int, Mapping[str, Any]], list[SolanaTokenBalanceDeltaIssue]]:
    if not isinstance(entries, list):
        return {}, [SolanaTokenBalanceDeltaIssue(None, "SNAPSHOTS_MISSING")]
    result: dict[int, Mapping[str, Any]] = {}
    duplicates: set[int] = set()
    issues: list[SolanaTokenBalanceDeltaIssue] = []
    for entry in entries:
        if not isinstance(entry, dict):
            issues.append(SolanaTokenBalanceDeltaIssue(None, "SNAPSHOT_ENTRY_INVALID"))
            continue
        index = entry.get("accountIndex")
        mint = entry.get("mint")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or not isinstance(mint, str)
            or not mint
            or _amount(entry) is None
        ):
            issues.append(SolanaTokenBalanceDeltaIssue(
                index if isinstance(index, int) and not isinstance(index, bool) and index >= 0 else None,
                "AMOUNT_INVALID" if isinstance(index, int) and not isinstance(index, bool) and index >= 0
                else "SNAPSHOT_ENTRY_INVALID",
            ))
            continue
        if index in result:
            duplicates.add(index)
            result.pop(index, None)
            issues.append(SolanaTokenBalanceDeltaIssue(index, "DUPLICATE_ACCOUNT_INDEX"))
            continue
        if index not in duplicates:
            result[index] = entry
    return result, issues


def decode_solana_token_account_balance_deltas(
    raw_transaction: dict[str, Any],
) -> SolanaTokenBalanceDeltaResult:
    """Calcula somente deltas com snapshots pareados e metadados consistentes.

    Ausência de um lado nunca é tratada como saldo zero. O resultado não
    atribui o delta a swap, carteira ou instrução específica.
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação precisa ser um objeto")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    meta = payload.get("meta")
    tx = payload.get("transaction")
    message = tx.get("message") if isinstance(tx, dict) else None
    if not isinstance(meta, dict) or not isinstance(message, dict):
        return SolanaTokenBalanceDeltaResult(
            (), (SolanaTokenBalanceDeltaIssue(None, "META_MISSING"),)
        )
    if "err" not in meta:
        return SolanaTokenBalanceDeltaResult(
            (), (SolanaTokenBalanceDeltaIssue(None, "EXECUTION_STATUS_UNKNOWN"),)
        )
    if meta.get("err") is not None:
        return SolanaTokenBalanceDeltaResult(
            (), (SolanaTokenBalanceDeltaIssue(None, "TRANSACTION_FAILED"),)
        )
    try:
        keys = _account_keys(message, meta)
    except ValueError:
        return SolanaTokenBalanceDeltaResult(
            (), (SolanaTokenBalanceDeltaIssue(None, "ACCOUNT_KEYS_INVALID"),)
        )

    before, before_issues = _snapshot_map(meta.get("preTokenBalances"))
    after, after_issues = _snapshot_map(meta.get("postTokenBalances"))
    issues = list(before_issues) + list(after_issues)
    deltas: list[SolanaTokenAccountBalanceDelta] = []

    for index in sorted(before.keys() | after.keys()):
        pre = before.get(index)
        post = after.get(index)
        if pre is None or post is None:
            issues.append(SolanaTokenBalanceDeltaIssue(index, "SNAPSHOT_SIDE_MISSING"))
            continue
        if index >= len(keys):
            issues.append(SolanaTokenBalanceDeltaIssue(index, "ACCOUNT_INDEX_UNRESOLVED"))
            continue
        if pre.get("mint") != post.get("mint"):
            issues.append(SolanaTokenBalanceDeltaIssue(index, "MINT_MISMATCH"))
            continue
        pre_amount = _amount(pre)
        post_amount = _amount(post)
        if pre_amount is None or post_amount is None:
            issues.append(SolanaTokenBalanceDeltaIssue(index, "AMOUNT_INVALID"))
            continue
        if pre_amount[1] != post_amount[1]:
            issues.append(SolanaTokenBalanceDeltaIssue(index, "DECIMALS_MISMATCH"))
            continue
        pre_owner = pre.get("owner")
        post_owner = post.get("owner")
        if pre_owner is not None and not isinstance(pre_owner, str):
            issues.append(SolanaTokenBalanceDeltaIssue(index, "OWNER_MISMATCH"))
            continue
        if post_owner is not None and not isinstance(post_owner, str):
            issues.append(SolanaTokenBalanceDeltaIssue(index, "OWNER_MISMATCH"))
            continue
        if pre_owner and post_owner and pre_owner != post_owner:
            issues.append(SolanaTokenBalanceDeltaIssue(index, "OWNER_MISMATCH"))
            continue
        deltas.append(SolanaTokenAccountBalanceDelta(
            account_index=index,
            token_account=keys[index],
            mint=pre["mint"],
            owner=pre_owner or post_owner,
            pre_amount_raw=pre_amount[0],
            post_amount_raw=post_amount[0],
            delta_raw=post_amount[0] - pre_amount[0],
            decimals=pre_amount[1],
        ))
    return SolanaTokenBalanceDeltaResult(tuple(deltas), tuple(issues))
