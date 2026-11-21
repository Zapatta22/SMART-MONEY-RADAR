"""CM38K: persisted swap to conservative FIFO receipt, offline only."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json

from smart_money_radar.services.cm38k_fifo_reconstruction import (
    EconomicOperation, reconstruct_fifo, _hash,
)
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.services.wallet_discovery import _raw
from smart_money_radar.domain.models import build_swap_operation_id
from smart_money_radar.storage.collector_authority import collector_write


def _time(value):
    t = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(t, datetime) or t.utcoffset() is None:
        raise ValueError("timezone required")
    return t.astimezone(timezone.utc)


def _derive(conn, operation_id, cutoff):
    cur = conn.execute("""
      SELECT a.*, s.signature, s.chain, s.wallet_address AS swap_wallet,
        s.input_mint AS swap_input, s.output_mint AS swap_output,
        s.input_amount AS swap_debit, s.output_amount AS swap_credit,
        c.side AS classified_side, c.confidence AS classified_confidence,
        e.program_id AS evidence_program, e.instruction_index, e.cpi_path_json,
        e.evidence_json, o.payload_json, o.slot, o.observed_at,
        o.parse_status, o.wallet_address AS observation_wallet
      FROM swap_replay_archive a
      JOIN swap_observations s USING(operation_id)
      JOIN swap_classifications c USING(operation_id)
      JOIN swap_evidence e USING(operation_id)
      JOIN observed_transactions o ON o.wallet_address=s.wallet_address
                                  AND o.signature=s.signature
      WHERE a.operation_id=?
    """, (operation_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError("persisted swap missing")
    d = dict(zip((x[0] for x in cur.description), row))
    d["wallet"] = d["wallet_address"]
    d["program"] = d["program_id"]
    available = _time(d["available_at"])
    occurred = _time(d["occurred_at"])
    if not occurred <= available <= cutoff:
        raise ValueError("future or inverted swap timestamp")
    issues = _raw(d, cutoff)[1]
    if issues:
        raise ValueError("RAW identity conflict: " + ",".join(issues))
    if (d["wallet"] != d["swap_wallet"]
            or d["program"] != d["evidence_program"]
            or d["side"] != d["classified_side"]
            or d["side"] not in ("BUY", "SELL")
            or not d["pool_address"]
            or d["input_mint"] != d["swap_input"]
            or d["output_mint"] != d["swap_output"]
            or Decimal(d["confidence"]) != Decimal(d["classified_confidence"])
            or build_swap_operation_id("solana", d["signature"],
                d["instruction_index"], tuple(json.loads(d["cpi_path_json"]))) != operation_id):
        raise ValueError("swap identity conflict")
    debit, credit = Decimal(d["input_amount"]), Decimal(d["output_amount"])
    if (not all(x.is_finite() and x > 0 for x in (debit, credit))
            or debit != Decimal(d["swap_debit"])
            or credit != Decimal(d["swap_credit"])):
        raise ValueError("swap quantity conflict")
    attempts = conn.execute("""
        SELECT status FROM swap_reconciliation_attempts
        WHERE operation_id=? AND wallet_address=? AND signature=?
          AND instruction_index=? AND cpi_path_json=?
    """, (operation_id, d["wallet"], d["signature"],
          d["instruction_index"], d["cpi_path_json"])).fetchall()
    if not attempts or any(x[0] != "MATCHED" for x in attempts):
        raise ValueError("reconciliation incomplete or divergent")
    links = conn.execute("""
      SELECT entity_type, entity_id, evidence_id, linked_at
      FROM cm38_economic_evidence_links
      WHERE radar='smart_money' AND wallet_address=? AND signature=?
    """, (d["wallet"], d["signature"])).fetchall()
    required = {("wallet_transaction", d["signature"]),
                ("swap_and_classification", operation_id),
                ("economic_reconciliation", operation_id),
                ("replay_opportunity", operation_id)}
    selected = [x for x in links if (x[0], x[1]) in required]
    if ({(x[0], x[1]) for x in selected} != required
            or len({x[2] for x in selected}) != 1
            or any(_time(x[3]) > cutoff for x in selected)):
        raise ValueError("missing, future or divergent RPC links")
    eid = selected[0][2]
    raw = conn.execute("SELECT metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?", (eid,)).fetchone()
    if raw is None:
        raise ValueError("original RPC missing")
    meta = RpcObservationJournal._read(eid, raw)["metadata"]
    tx = json.loads(raw[2])["result"]
    stored = json.loads(d["payload_json"])
    if (meta["radar"] != "smart_money" or meta["signature"] != d["signature"]
            or meta["source_id"] != "helius-wallet-rpc"
            or meta["commitment_requested"] != "confirmed"
            or meta["slot"] != d["slot"] or meta["status"] == "CONFLICTED"
            or _time(meta["available_at"]) > available
            or tx != stored.get("result", stored)):
        raise ValueError("original RPC scope or payload conflict")
    for other_id, *other in conn.execute("""
        SELECT evidence_id,metadata,metadata_sha,raw FROM cm38_rpc_observations
        WHERE radar='smart_money' AND signature=? AND evidence_id<>?
    """, (d["signature"], eid)):
        om = RpcObservationJournal._read(other_id, other)["metadata"]
        if _time(om["available_at"]) <= cutoff and (
                om["status"] == "CONFLICTED" or json.loads(other[2]).get("result") != tx):
            raise ValueError("divergent RPC source")
    ev = json.loads(d["evidence_json"])
    if "pool_state:" + d["pool_address"] not in ev:
        raise ValueError("pool evidence conflict")
    # Reuse conservative wallet delta parser. Multi-swap or ambiguous net
    # movement is rejected rather than attributed to multiple operations.
    from smart_money_radar.data_sources.transaction_parser import parse_transaction
    deltas = {(x.token_mint, x.direction): x.amount
              for x in parse_transaction(tx, d["wallet"], d["signature"])}
    if (deltas.get((d["input_mint"], "out")) != debit
            or deltas.get((d["output_mint"], "in")) != credit):
        raise ValueError("RAW wallet delta conflict")
    if conn.execute("SELECT COUNT(*) FROM swap_observations WHERE wallet_address=? AND signature=?",
                    (d["wallet"], d["signature"])).fetchone()[0] != 1:
        raise ValueError("multi-swap allocation unproven")
    buy = d["side"] == "BUY"
    token, quote = (d["output_mint"], d["input_mint"]) if buy else (d["input_mint"], d["output_mint"])
    # Gross wallet debit and spendable net credit already contain DEX and
    # token transfer costs. Do not subtract them again. Network costs are
    # explicitly unknown in quote units; no zero-cost claim is made.
    op = EconomicOperation(operation_id, d["wallet"], token, d["side"],
        credit if buy else debit, occurred, available, meta["source_id"], eid,
        meta["raw_sha256"], quote_mint=quote, quote_amount=debit if buy else credit,
        independently_attested=False, history_complete=False)
    receipt = reconstruct_fifo((op,), wallet=d["wallet"], token=token,
                               quote_mint=quote, as_of=cutoff)
    receipt["reasons"] = sorted(set(receipt["reasons"]) | {"network_fee_quote_cost_unproven"})
    receipt["lots"] = [{**lot, "cost_remaining": None, "cost_status": "UNKNOWN"} for lot in receipt["lots"]]
    receipt["persisted_swap"] = {"operation_id": operation_id, "signature": d["signature"],
        "slot": d["slot"], "program": d["program"], "pool": d["pool_address"],
        "input_mint": d["input_mint"], "output_mint": d["output_mint"],
        "wallet_debit": str(debit), "wallet_credit_net": str(credit),
        "network_fee_lamports": tx["meta"].get("fee"),
        "fee_policy": "NET_DELTAS_NO_SECOND_DEDUCTION",
        "coverage": "UNKNOWN", "authenticity": "UNATTESTED"}
    receipt["sha256"] = _hash({k:v for k,v in receipt.items() if k!="sha256"})
    return receipt


def persist_fifo_swap(store, *, operation_id, as_of):
    """Immutable, idempotent projection of one persisted operation."""
    cutoff = _time(as_of)
    if cutoff > datetime.now(timezone.utc):
        raise ValueError("future cutoff")
    with localcontext() as ctx:
        ctx.prec = 100
        with store._connection_scope() as conn, collector_write(
                conn, getattr(store, "_collector_authority", None), "smart_money"):
            receipt = _derive(conn, operation_id, cutoff)
            conn.execute("""CREATE TABLE IF NOT EXISTS cm38k_persisted_fifo (
                operation_id TEXT NOT NULL REFERENCES swap_observations(operation_id),
                cutoff TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(operation_id, cutoff))""")
            for action in ("UPDATE", "DELETE"):
                conn.execute("CREATE TRIGGER IF NOT EXISTS cm38k_fifo_no_" + action.lower()
                    + " BEFORE " + action + " ON cm38k_persisted_fifo BEGIN "
                    "SELECT RAISE(ABORT,'immutable FIFO receipt'); END")
            payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
            prior = conn.execute("SELECT payload,digest FROM cm38k_persisted_fifo WHERE operation_id=? AND cutoff=?",
                                 (operation_id, cutoff.isoformat())).fetchone()
            target = (payload, receipt["sha256"])
            if prior is not None and tuple(prior) != target:
                raise ValueError("divergent FIFO replay")
            if prior is None:
                conn.execute("INSERT INTO cm38k_persisted_fifo VALUES (?,?,?,?)",
                             (operation_id, cutoff.isoformat(), *target))
            return receipt
