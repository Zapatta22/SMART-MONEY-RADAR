"""CM38K immutable association: FIFO economic receipt -> existing blocked CM38I.

Sidecar is append-only and never grants trading/paper entry. It does not
rewrite old risk decisions, opportunities, ledger snapshots or RPC evidence.
"""
from __future__ import annotations
from hashlib import sha256
import json
import sqlite3

from smart_money_radar.services.cm38i_decision_audit import audit_blocked_entry
from smart_money_radar.services.cm38k_fifo_reconstruction import verify_fifo_receipt
from smart_money_radar.storage.event_store import SQLiteEventStore


def _hash(payload):
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS cm38k_economic_decision_links(
        link_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        decision_id TEXT NOT NULL UNIQUE,
        attempt_id TEXT NOT NULL UNIQUE,
        economic_sha256 TEXT NOT NULL,
        economic_payload TEXT NOT NULL,
        receipt_sha256 TEXT NOT NULL,
        FOREIGN KEY(decision_id) REFERENCES cm38i_risk_decisions(decision_id),
        FOREIGN KEY(attempt_id) REFERENCES cm38i_virtual_entry_attempts(attempt_id)
    )""")
    for action in ("UPDATE","DELETE"):
        conn.execute("CREATE TRIGGER IF NOT EXISTS cm38k_link_immutable_"+action.lower()+
                     " BEFORE "+action+" ON cm38k_economic_decision_links "+
                     " BEGIN SELECT RAISE(ABORT,'CM38K economic link immutable'); END")


def link_fifo_to_blocked_decision(store, *, request_id, receipt):
    if not isinstance(store,SQLiteEventStore) or store.read_only:
        raise PermissionError("writable existing evaluation store required")
    verify_fifo_receipt(receipt)
    if receipt.get("wallet") is None or not isinstance(receipt["wallet"],str) or not receipt["wallet"]:
        raise ValueError("wallet identity required")
    if receipt["status"] not in ("INFORMATION_ONLY","NOT_COMPUTABLE"):
        raise ValueError("unapproved economic receipt status")
    if not isinstance(request_id,str) or not request_id:
        raise ValueError("request ID required")
    # Read and authenticate original CM38I receipt before attempting a write.
    audited=audit_blocked_entry(store,request_id)
    if audited is None or audited["radar"]!="smart_money":
        raise ValueError("Smart Money blocked decision required")
    if audited["status"]!="BLOCKED" or audited["prospective_authorized"]:
        raise ValueError("live or prospective decision forbidden")
    payload=json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False)
    link_id=_hash(["CM38K-DECISION-LINK-1",audited["attempt_id"],receipt["sha256"]])
    row=[link_id,request_id,audited["decision_id"],audited["attempt_id"],
         receipt["sha256"],payload]
    receipt_sha=_hash(row)
    with store._connection_scope() as conn,conn:
        conn.execute("BEGIN IMMEDIATE")
        # Revalidate all persisted CM38I rows and original immutable evidence
        # via shared integrity helper in the same writer snapshot.
        from smart_money_radar.services.cm38i_decision_audit import _integrity
        _integrity(conn,audited["attempt_id"])
        op=conn.execute("SELECT radar,available_at,decision_at FROM cm38i_opportunities WHERE opportunity_id=?",
                         (audited["opportunity_id"],)).fetchone()
        if op is None or op[0]!="smart_money":
            raise ValueError("economic decision scope conflict")
        if not conn.execute("SELECT 1 FROM cm38_rpc_observations WHERE evidence_id=? AND radar='smart_money'",
                            (audited["evidence_id"],)).fetchone():
            raise ValueError("original RPC evidence missing")
        if receipt["as_of"]>op[2]:
            raise ValueError("future economic receipt")
        if any(line["available_at"]>op[2] for line in receipt["lineage"]):
            raise ValueError("future FIFO operation")
        # The economic lineage may be incomplete: never infer economic truth
        # from a locally matching hash or permit a known divergent original.
        _schema(conn)
        old=conn.execute("SELECT link_id,request_id,decision_id,attempt_id,economic_sha256,economic_payload,receipt_sha256 FROM cm38k_economic_decision_links WHERE request_id=?",
                         (request_id,)).fetchone()
        target=tuple(row+[receipt_sha])
        if old is not None:
            if old!=target:
                raise ValueError("divergent economic replay rejected")
            return {"link_id":link_id,"idempotent_replay":True,"status":"BLOCKED"}
        conn.execute("INSERT INTO cm38k_economic_decision_links VALUES(?,?,?,?,?,?,?)",target)
    return {"link_id":link_id,"idempotent_replay":False,"status":"BLOCKED"}


def audit_fifo_decision_link(store,request_id):
    if not isinstance(store,SQLiteEventStore): raise TypeError("SQLiteEventStore required")
    audited=audit_blocked_entry(store,request_id)
    if audited is None: return None
    with store._connection_scope() as conn:
        exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38k_economic_decision_links'").fetchone()
        if not exists: return None
        row=conn.execute("SELECT link_id,request_id,decision_id,attempt_id,economic_sha256,economic_payload,receipt_sha256 FROM cm38k_economic_decision_links WHERE request_id=?",
                         (request_id,)).fetchone()
        if row is None: return None
        receipt=json.loads(row[5])
        verify_fifo_receipt(receipt)
        if row[6]!=_hash(list(row[:6])) or row[4]!=receipt["sha256"]:
            raise ValueError("economic link integrity conflict")
        if row[2]!=audited["decision_id"] or row[3]!=audited["attempt_id"] or receipt["radar"]!="smart_money":
            raise ValueError("economic decision lineage mismatch")
        return {"link_id":row[0],"economic_sha256":row[4],
                "status":"BLOCKED","prospective_authorized":False,
                "economic_status":receipt["status"]}
