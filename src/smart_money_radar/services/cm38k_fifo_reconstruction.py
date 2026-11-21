"""CM38K: deterministic, audit-only FIFO economic lot reconstruction.

Projection consumes reconciled operation receipts supplied by an existing collector.
It never authenticates a provider, estimates FX, writes a store, or submits orders.
Unknown cost/fee/history remains NOT_COMPUTABLE rather than zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json

VERSION = "CM38K-FIFO-1"
KINDS = ("BUY", "SELL", "TRANSFER_IN", "TRANSFER_OUT")
ZERO = Decimal("0")


def _time(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamps required")
    return value.astimezone(timezone.utc)


def _positive(value, *, allow_zero=False):
    if not isinstance(value, Decimal) or not value.is_finite() or (value < ZERO if allow_zero else value <= ZERO):
        raise ValueError("finite Decimal quantity required")
    return value


def _hash(payload):
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class EconomicOperation:
    operation_id: str
    wallet: str
    token: str
    kind: str
    quantity: Decimal
    occurred_at: datetime
    available_at: datetime
    source_id: str
    evidence_id: str
    raw_sha256: str
    quote_mint: str | None = None
    quote_amount: Decimal | None = None
    fee_mint: str | None = None
    fee_amount: Decimal | None = None
    fee_quote_value: Decimal | None = None
    independently_attested: bool = False
    history_complete: bool = False
    step_complete: bool = True

    def __post_init__(self):
        if self.kind not in KINDS or any(not isinstance(x, str) or not x.strip()
                                         for x in (self.operation_id, self.wallet, self.token, self.source_id)):
            raise ValueError("invalid economic operation identity")
        _positive(self.quantity)
        if _time(self.occurred_at) > _time(self.available_at):
            raise ValueError("future availability inversion")
        if any(not isinstance(x, str) or len(x) != 64 or
               any(c not in "0123456789abcdef" for c in x)
               for x in (self.evidence_id, self.raw_sha256)):
            raise ValueError("original RPC identity/hash required")
        if self.quote_amount is not None:
            _positive(self.quote_amount, allow_zero=True)
            if not self.quote_mint or self.quote_mint == self.token:
                raise ValueError("quote mint mismatch")
        if self.kind in ("TRANSFER_IN", "TRANSFER_OUT") and self.quote_amount is not None:
            raise ValueError("transfers cannot be priced as swaps")
        if self.fee_amount is not None:
            _positive(self.fee_amount, allow_zero=True)
            if not self.fee_mint:
                raise ValueError("fee mint required")
        if self.fee_quote_value is not None:
            _positive(self.fee_quote_value, allow_zero=True)
            if self.fee_amount is None or not self.quote_mint:
                raise ValueError("fee conversion provenance missing")


def reconstruct_fifo(operations, *, wallet: str, token: str,
                     quote_mint: str, as_of: datetime, quotes=()):
    """FIFO lots; no cross-mint netting or invented conversion.

    Values of PnL are labeled ATTESTED only if the caller has supplied
    independently attested, complete, uniform-currency evidence. The local
    receipt itself cannot establish independent provenance.
    """
    cutoff = _time(as_of)
    if cutoff > datetime.now(timezone.utc):
        raise ValueError("future cutoff")
    if any(not isinstance(x, str) or not x.strip() for x in (wallet, token, quote_mint)) or token == quote_mint:
        raise ValueError("invalid token/quote scope")
    items = tuple(operations)
    if any(not isinstance(x, EconomicOperation) for x in items):
        raise TypeError("economic operation receipt required")
    seen = {}
    for op in items:
        if (op.wallet, op.token) != (wallet, token):
            raise ValueError("cross-wallet or cross-token operation")
        if op.available_at > cutoff or op.occurred_at > cutoff:
            raise ValueError("future operation in historical projection")
        if op.operation_id in seen:
            raise ValueError("duplicate economic operation")
        seen[op.operation_id] = op
        if op.quote_mint is not None and op.quote_mint != quote_mint:
            raise ValueError("cross-currency conversion without evidence")
    ordered = sorted(items, key=lambda op:(op.occurred_at,op.available_at,op.operation_id))
    lots = []
    pnl = ZERO
    realized_count = 0
    wins = 0
    reasons = set()
    used = []
    lineage = []
    complete = bool(ordered)
    for op in ordered:
        if not op.independently_attested:
            reasons.add("independent_rpc_evidence_unverified")
            complete = False
        if not op.history_complete:
            reasons.add("historical_coverage_incomplete")
            complete = False
        if not op.step_complete:
            reasons.add("multi_step_swap_reconciliation_incomplete")
            complete = False
        if op.fee_amount is not None and op.fee_amount != ZERO and op.fee_mint not in (token,quote_mint):
            if op.fee_quote_value is None:
                reasons.add("cross_mint_fee_unconverted")
                complete = False
        if op.kind == "BUY":
            cost = op.quote_amount
            if cost is None:
                reasons.add("acquisition_cost_unknown");complete=False
            if op.fee_amount is not None and op.fee_amount != ZERO:
                if op.fee_mint == quote_mint:
                    cost = cost + op.fee_amount if cost is not None else None
                elif op.fee_quote_value is not None:
                    cost = cost + op.fee_quote_value if cost is not None else None
                else:
                    reasons.add("purchase_fee_conversion_unknown");complete=False
                    cost = None
            lots.append({"id":op.operation_id,"remaining":op.quantity,"cost_remaining":cost,
                         "evidence_id":op.evidence_id,"source_id":op.source_id})
        elif op.kind == "TRANSFER_IN":
            # Transfers cannot inherit a zero cost; original donor lot basis must be proven.
            lots.append({"id":op.operation_id,"remaining":op.quantity,
                         "cost_remaining":None,"evidence_id":op.evidence_id,
                         "source_id":op.source_id})
            reasons.add("incoming_transfer_basis_unknown");complete=False
        else:
            remaining = op.quantity
            matched = ZERO
            matched_cost = ZERO
            known_cost = True
            while remaining > ZERO and lots:
                lot = lots[0]
                quantity = min(remaining,lot["remaining"])
                if lot["cost_remaining"] is None:
                    known_cost = False
                else:
                    allocated = lot["cost_remaining"] * quantity / lot["remaining"]
                    matched_cost += allocated
                    lot["cost_remaining"] -= allocated
                lot["remaining"] -= quantity
                matched += quantity
                remaining -= quantity
                if lot["remaining"] == ZERO:
                    lots.pop(0)
            if remaining > ZERO:
                reasons.add("insufficient_known_inventory");complete=False
                # Unknown opening balance is not fabricated into a new lot.
            if not known_cost:
                reasons.add("fifo_cost_basis_unknown");complete=False
            if op.kind == "SELL":
                if (op.quote_amount is None or matched != op.quantity
                        or not known_cost or not op.step_complete):
                    reasons.add("sale_economics_not_computable")
                    complete=False
                elif op.fee_amount is not None and op.fee_amount != ZERO and op.fee_mint not in (quote_mint,token) and op.fee_quote_value is None:
                    reasons.add("sale_fee_conversion_unknown");complete=False
                else:
                    fee_quote = ZERO
                    if op.fee_amount is not None:
                        if op.fee_mint == quote_mint:
                            fee_quote = op.fee_amount
                        elif op.fee_quote_value is not None:
                            fee_quote = op.fee_quote_value
                        elif op.fee_mint == token and op.fee_amount != ZERO:
                            reasons.add("token_fee_valuation_unknown");complete=False
                            continue
                    gain = op.quote_amount - matched_cost - fee_quote
                    pnl += gain
                    realized_count += 1
                    wins += gain > ZERO
            else:
                reasons.add("outgoing_transfer_cost_leaves_known_inventory")
        used.append(op.evidence_id)
        lineage.append({"operation_id":op.operation_id,"source_id":op.source_id,
                        "evidence_id":op.evidence_id,"raw_sha256":op.raw_sha256,
                        "kind":op.kind,"available_at":op.available_at.isoformat()})
    unrealized = None
    qlist = tuple(quotes)
    if qlist:
        if len(qlist) != 1:
            raise ValueError("ambiguous valuation quotes")
        quote = qlist[0]
        if not isinstance(quote,dict) or quote.get("token") != token or quote.get("quote_mint") != quote_mint:
            raise ValueError("quote token or currency mismatch")
        at = _time(quote.get("available_at"))
        market = _time(quote.get("market_at"))
        if market > at or at > cutoff:
            raise ValueError("future valuation quote")
        price = _positive(quote.get("price"))
        if not quote.get("independently_attested",False):
            reasons.add("valuation_quote_unattested")
        elif any(l["cost_remaining"] is None for l in lots):
            reasons.add("open_lot_cost_unknown")
        else:
            unrealized = sum((l["remaining"] * price - l["cost_remaining"] for l in lots),ZERO)
    else:
        reasons.add("valuation_quote_missing")
    # Local fields cannot make independent claims actionable; expose calculations
    # as provisional until external attestation/reconciliation exists.
    if not complete:
        realized = None
        win_rate = None
    else:
        realized = pnl if realized_count else None
        win_rate = Decimal(wins) / Decimal(realized_count) if realized_count else None
    if not complete or "valuation_quote_unattested" in reasons:
        unrealized = None
    if unrealized is None:
        reasons.add("unrealized_pnl_not_computable")
    if realized is None:
        reasons.add("realized_pnl_not_computable")
    payload = {
        "schema":"smr.cm38k.fifo.v1","method":VERSION,
        "radar":"smart_money","wallet":wallet,"token":token,"quote_mint":quote_mint,
        "as_of":cutoff.isoformat(),"lineage":lineage,
        "lots":[{"lot_id":l["id"],"remaining":str(l["remaining"]),
                 "cost_remaining":str(l["cost_remaining"]) if l["cost_remaining"] is not None else None,
                 "cost_status":"KNOWN" if l["cost_remaining"] is not None else "UNKNOWN"}
                for l in lots],
        "realized_pnl":str(realized) if realized is not None else None,
        "unrealized_pnl":str(unrealized) if unrealized is not None else None,
        "win_rate":str(win_rate) if win_rate is not None else None,
        "realized_sales":realized_count if complete else None,
        "status":"INFORMATION_ONLY" if complete else "NOT_COMPUTABLE",
        "confidence":"LOCAL_CALCULATION_NOT_INDEPENDENT_ATTESTATION",
        "reasons":sorted(reasons),
        "prospective_authorized":False,"operational_authorized":False,
    }
    payload["sha256"]=_hash(payload)
    return payload


def verify_fifo_receipt(payload):
    if not isinstance(payload,dict) or payload.get("schema")!="smr.cm38k.fifo.v1":
        raise ValueError("invalid FIFO receipt")
    copy=dict(payload)
    expected=copy.pop("sha256",None)
    if not isinstance(expected,str) or _hash(copy)!=expected:
        raise ValueError("FIFO integrity conflict")
    if payload.get("radar")!="smart_money" or payload.get("prospective_authorized") is not False or payload.get("operational_authorized") is not False:
        raise ValueError("unauthorized FIFO scope")
    return payload
