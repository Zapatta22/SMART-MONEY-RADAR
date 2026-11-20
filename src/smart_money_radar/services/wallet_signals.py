"""Point-in-time directional wallet activity from first-publication swap evidence."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from smart_money_radar.storage.event_store import SQLiteEventStore


@dataclass(frozen=True)
class WalletSwapEvidence:
    signature: str
    side: Literal["BUY", "SELL"]
    operation_ids: tuple[str, ...]


@dataclass(frozen=True)
class WalletRejectedEvidence:
    signature: str
    reasons: tuple[str, ...]
    operation_ids: tuple[str, ...]


@dataclass(frozen=True)
class WalletSignalReport:
    direction: Literal["BUY", "SELL", "MIXED", "INSUFFICIENT"]
    evidence: tuple[WalletSwapEvidence, ...]
    excluded: tuple[WalletRejectedEvidence, ...]


class WalletSignalService:
    """Report archived swap evidence within one wallet, program, pool and pair."""

    def __init__(self, store: SQLiteEventStore) -> None:
        self._store = store

    def get_report(
        self, *, wallet: str, program: str, pool: str, base_mint: str, quote_mint: str,
        as_of: datetime, window: timedelta, max_publication_delay: timedelta,
        min_confidence: Decimal, min_transactions: int,
    ) -> WalletSignalReport:
        if not all(isinstance(value, str) and value.strip()
                   for value in (wallet, program, pool, base_mint, quote_mint)) or base_mint == quote_mint:
            raise ValueError("carteira, programa, pool e mints distintos são obrigatórios")
        if as_of.utcoffset() is None or min(window, max_publication_delay) <= timedelta(0):
            raise ValueError("janela, atraso máximo e data com fuso são obrigatórios")
        if not min_confidence.is_finite() or not 0 <= min_confidence <= 1:
            raise ValueError("confiança mínima inválida")
        if type(min_transactions) is not int or min_transactions < 2:
            raise ValueError("o sinal exige ao menos duas transações distintas")

        receipts = self._store.list_wallet_signal_receipts(
            wallet=wallet, program=program, pool=pool, base_mint=base_mint, quote_mint=quote_mint,
        )
        as_of = as_of.astimezone(timezone.utc)
        since = as_of - window
        transactions: dict[str, list[tuple[Literal["BUY", "SELL"], str, tuple[str, ...]]]] = defaultdict(list)
        for receipt in receipts:
            arrival = datetime.fromisoformat(receipt["available_at"])
            occurred = datetime.fromisoformat(receipt["occurred_at"])
            if arrival.utcoffset() is None or occurred.utcoffset() is None:
                raise ValueError("recibo sem proveniência temporal com fuso")
            if not since <= occurred <= arrival <= as_of:
                continue
            confidence = Decimal(receipt["confidence"])
            if not confidence.is_finite() or not 0 <= confidence <= 1:
                raise ValueError("confiança inválida no arquivo de swaps")
            expected: Literal["BUY", "SELL"] = "BUY" if receipt["input_mint"] == quote_mint else "SELL"
            reasons = []
            if arrival - occurred > max_publication_delay:
                reasons.append("late_publication")
            if receipt["side"] != expected:
                reasons.append("direction_unverified")
            if confidence < min_confidence:
                reasons.append("low_confidence")
            transactions[receipt["signature"]].append((expected, receipt["operation_id"], tuple(reasons)))

        evidence = []
        excluded = []
        for signature, operations in transactions.items():
            direction = operations[0][0]
            reasons = {reason for _, _, problems in operations for reason in problems}
            if any(side != direction for side, _, _ in operations):
                reasons.add("opposing_directions")
            operation_ids = tuple(operation_id for _, operation_id, _ in operations)
            if reasons:
                excluded.append(WalletRejectedEvidence(signature, tuple(sorted(reasons)), operation_ids))
            else:
                evidence.append(WalletSwapEvidence(signature, direction, operation_ids))

        sides = {item.side for item in evidence}
        if len(sides) > 1:
            return WalletSignalReport("MIXED", tuple(evidence), tuple(excluded))
        if len(evidence) < min_transactions:
            return WalletSignalReport("INSUFFICIENT", tuple(evidence), tuple(excluded))
        return WalletSignalReport(evidence[0].side, tuple(evidence), tuple(excluded))
