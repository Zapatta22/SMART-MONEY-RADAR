"""Deltas SPL por token account, preservando accountIndex e unidades brutas."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenAccountBalanceDelta:
    account_index: int
    token_account: str
    mint: str
    owner: str | None
    pre_amount_raw: int
    post_amount_raw: int
    delta_raw: int
    decimals: int


def _account_keys(message: Mapping[str, Any], meta: Mapping[str, Any]) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("message.accountKeys ausente ou inválido")
    parsed_keys = any(isinstance(item, dict) for item in raw)
    keys = []
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


def _parse_side(entries: Any, side: str) -> dict[int, tuple[str, str | None, int, int]]:
    if not isinstance(entries, list):
        raise ValueError(f"meta.{side}TokenBalances ausente ou inválido")
    parsed: dict[int, tuple[str, str | None, int, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"meta.{side}TokenBalances contém item inválido")
        index = entry.get("accountIndex")
        mint = entry.get("mint")
        owner = entry.get("owner")
        amount_info = entry.get("uiTokenAmount")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError(f"accountIndex inválido em {side}TokenBalances")
        if not isinstance(mint, str) or not mint:
            raise ValueError(f"mint inválido em {side}TokenBalances")
        if owner is not None and (not isinstance(owner, str) or not owner):
            raise ValueError(f"owner inválido em {side}TokenBalances")
        if not isinstance(amount_info, dict):
            raise ValueError(f"uiTokenAmount inválido em {side}TokenBalances")
        raw_amount = amount_info.get("amount")
        decimals = amount_info.get("decimals")
        if not isinstance(raw_amount, str) or not raw_amount.isdigit():
            raise ValueError(f"amount bruto inválido em {side}TokenBalances")
        if (
            isinstance(decimals, bool)
            or not isinstance(decimals, int)
            or not 0 <= decimals <= 255
        ):
            raise ValueError(f"decimals inválido em {side}TokenBalances")
        if index in parsed:
            raise ValueError(f"accountIndex duplicado em {side}TokenBalances")
        parsed[index] = (mint, owner, int(raw_amount), decimals)
    return parsed


def decode_token_account_balance_deltas(
    raw_transaction: dict[str, Any],
) -> list[TokenAccountBalanceDelta]:
    """Calcula deltas exatos por token account em transação bem-sucedida.

    Ambos os arrays pre/post precisam estar presentes. Se um accountIndex aparece
    somente em um lado, o outro saldo é zero (conta criada/fechada na transação).
    """
    if not isinstance(raw_transaction, dict):
        raise TypeError("transação precisa ser um objeto")
    payload = raw_transaction.get("result", raw_transaction)
    if not isinstance(payload, dict):
        raise ValueError("payload RPC inválido")
    tx = payload.get("transaction")
    meta = payload.get("meta")
    if not isinstance(tx, dict) or not isinstance(meta, dict):
        raise ValueError("transaction/meta ausente ou inválido")
    if meta.get("err") is not None:
        return []
    message = tx.get("message")
    if not isinstance(message, dict):
        raise ValueError("transaction.message ausente ou inválido")

    keys = _account_keys(message, meta)
    before = _parse_side(meta.get("preTokenBalances"), "pre")
    after = _parse_side(meta.get("postTokenBalances"), "post")

    results = []
    for index in sorted(before.keys() | after.keys()):
        pre = before.get(index)
        post = after.get(index)
        reference = pre or post
        assert reference is not None
        mint, owner, pre_amount, decimals = pre if pre is not None else (
            reference[0], reference[1], 0, reference[3]
        )
        post_mint, post_owner, post_amount, post_decimals = post if post is not None else (
            reference[0], reference[1], 0, reference[3]
        )
        if mint != post_mint or decimals != post_decimals:
            raise ValueError("mint/decimals divergentes no mesmo accountIndex")
        if owner is not None and post_owner is not None and owner != post_owner:
            raise ValueError("owner divergente no mesmo accountIndex")
        resolved_owner = owner if owner is not None else post_owner
        if index >= len(keys):
            raise ValueError("accountIndex fora da lista de accountKeys")
        delta = post_amount - pre_amount
        if delta == 0:
            continue
        results.append(TokenAccountBalanceDelta(
            account_index=index,
            token_account=keys[index],
            mint=mint,
            owner=resolved_owner,
            pre_amount_raw=pre_amount,
            post_amount_raw=post_amount,
            delta_raw=delta,
            decimals=decimals,
        ))
    return results
