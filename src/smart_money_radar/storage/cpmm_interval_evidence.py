"""Append-only per-interval RPC evidence in the existing CPMM history SQLite.

No checkpoint can advance beyond the rows committed with the same transaction.
A restart can replay idempotently; conflicting RAW or proof claims fail closed.
This records gaps but never asserts complete historical coverage.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import sqlite3

from smart_money_radar.services.cpmm_interval_transaction_audit import IntervalReconciliation,IntervalTransaction

_DDL="""
CREATE TABLE IF NOT EXISTS cpmm_interval_evidence (
 first_capture_id TEXT NOT NULL,
 second_capture_id TEXT NOT NULL,
 evidence_kind TEXT NOT NULL CHECK(evidence_kind IN ('LISTING','TRANSACTION')),
 evidence_id TEXT NOT NULL,
 slot INTEGER,
 source_id TEXT NOT NULL,
 observed_at TEXT,
 available_at TEXT,
 raw_payload BLOB NOT NULL,
 raw_sha256 TEXT NOT NULL,
 classification TEXT NOT NULL CHECK(classification IN ('OBSERVED','PARTIAL','UNKNOWN','CONFLICT')),
 metadata_json TEXT NOT NULL,
 PRIMARY KEY(first_capture_id,second_capture_id,evidence_kind,evidence_id),
 FOREIGN KEY(first_capture_id) REFERENCES prospective_cpmm_captures(capture_id),
 FOREIGN KEY(second_capture_id) REFERENCES prospective_cpmm_captures(capture_id)
);
CREATE TABLE IF NOT EXISTS cpmm_interval_audit_checkpoints (
 first_capture_id TEXT NOT NULL,
 second_capture_id TEXT NOT NULL,
 generation INTEGER NOT NULL,
 coverage TEXT NOT NULL CHECK(coverage IN ('PARTIAL','UNKNOWN','CONFLICT')),
 body_json TEXT NOT NULL,
 evidence_count INTEGER NOT NULL,
 PRIMARY KEY(first_capture_id,second_capture_id),
 FOREIGN KEY(first_capture_id) REFERENCES prospective_cpmm_captures(capture_id),
 FOREIGN KEY(second_capture_id) REFERENCES prospective_cpmm_captures(capture_id)
);
"""


def _json(o):
    return json.dumps(o,sort_keys=True,separators=(",",":"),allow_nan=False)


def init_interval_schema(db:sqlite3.Connection)->None:
    db.executescript(_DDL)


def append_interval_audit(
    db:sqlite3.Connection,*,first_capture_id:str,second_capture_id:str,
    source_id:str,listing_raw:bytes,listing_manifest:dict,
    transaction_raws:dict[str,bytes],transactions:tuple[IntervalTransaction,...],
    summary:IntervalReconciliation,fail_before_commit:bool=False
)->bool:
    if not all(isinstance(s,str) and s for s in (first_capture_id,second_capture_id,source_id)):
        raise ValueError("IDs do intervalo e da fonte obrigatórios")
    if not isinstance(listing_raw,bytes) or not listing_raw:
        raise ValueError("RAW de lista ausente")
    if sha256(listing_raw).hexdigest()!=listing_manifest.get("response_sha256"):
        raise ValueError("SHA de lista divergente")
    if (summary.coverage not in {"PARTIAL","UNKNOWN","CONFLICT"}
        or summary.transaction_order_proven
        or summary.account_write_stream_complete
        or summary.operation_authorized):
        raise ValueError("checkpoint tenta promover cobertura/execução")
    if len(transactions)!=summary.listed_count:
        raise ValueError("eventos de intervalo incompletos")
    if len({t.signature for t in transactions})!=len(transactions):
        raise ValueError("assinatura duplicada")
    # Use a single BEGIN IMMEDIATE so interrupted processing cannot move a
    # checkpoint beyond the evidence it references.
    rows=[("LISTING","pool-signatures",None,
           listing_manifest.get("observed_at"),listing_manifest.get("available_at"),
           listing_raw,"PARTIAL",{"source":"getSignaturesForAddress"})]
    for t in transactions:
        raw=transaction_raws.get(t.signature)
        if raw is None:
            if t.status=="OBSERVED":
                raise ValueError("transação observada sem RAW")
            # Unknown result must have an actual evidence envelope to persist.
            raise ValueError("RAW da tentativa ausente")
        if not isinstance(raw,bytes) or not raw or sha256(raw).hexdigest()!=t.raw_sha256:
            raise ValueError("RAW de transação divergente")
        rows.append(("TRANSACTION",t.signature,t.listed_slot,
                     t.observed_at.isoformat() if t.observed_at else None,
                     t.available_at.isoformat() if t.available_at else None,
                     raw,t.status,asdict(t)))
    expected=len(rows)
    payload=_json(asdict(summary))
    init_interval_schema(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        for cap_id in (first_capture_id,second_capture_id):
            if db.execute("SELECT 1 FROM prospective_cpmm_captures WHERE capture_id=?",(cap_id,)).fetchone() is None:
                raise ValueError("snapshot referenced is missing")
        existing=db.execute(
            "SELECT generation,coverage,body_json,evidence_count FROM cpmm_interval_audit_checkpoints "
            "WHERE first_capture_id=? AND second_capture_id=?",
            (first_capture_id,second_capture_id)).fetchone()
        if existing:
            if existing!=(1,summary.coverage,payload,expected):
                raise ValueError("conflicting checkpoint cannot overwrite immutable audit")
            # Ensure existing rows are still byte-identical when replaying.
            for kind,id,slot,observed,available,raw,classification,meta in rows:
                stored=db.execute(
                    "SELECT raw_payload,raw_sha256,classification,metadata_json FROM cpmm_interval_evidence "
                    "WHERE first_capture_id=? AND second_capture_id=? AND evidence_kind=? AND evidence_id=?",
                    (first_capture_id,second_capture_id,kind,id)).fetchone()
                if stored!=(raw,sha256(raw).hexdigest(),classification,_json(meta)):
                    raise ValueError("previous RAW evidence changed")
            db.commit()
            return False
        for kind,id,slot,observed,available,raw,classification,meta in rows:
            db.execute(
                "INSERT INTO cpmm_interval_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (first_capture_id,second_capture_id,kind,id,slot,source_id,
                 observed,available,raw,sha256(raw).hexdigest(),classification,_json(meta)))
        if fail_before_commit:
            raise RuntimeError("simulated interruption before checkpoint commit")
        db.execute(
            "INSERT INTO cpmm_interval_audit_checkpoints VALUES(?,?,?,?,?,?)",
            (first_capture_id,second_capture_id,1,summary.coverage,payload,expected))
        db.commit()
        return True
    except BaseException:
        db.rollback()
        raise


def get_interval_audit(db:sqlite3.Connection,first_id:str,second_id:str)->dict|None:
    row=db.execute(
        "SELECT generation,coverage,body_json,evidence_count FROM cpmm_interval_audit_checkpoints "
        "WHERE first_capture_id=? AND second_capture_id=?",
        (first_id,second_id)).fetchone()
    if row is None:return None
    records=db.execute(
        "SELECT evidence_kind,evidence_id,raw_payload,raw_sha256 FROM cpmm_interval_evidence "
        "WHERE first_capture_id=? AND second_capture_id=? ORDER BY evidence_kind,evidence_id",
        (first_id,second_id)).fetchall()
    if len(records)!=row[3]:
        raise ValueError("checkpoint points to incomplete evidence")
    for _,_,raw,digest in records:
        if sha256(raw).hexdigest()!=digest:
            raise ValueError("checkpoint references corrupted RAW")
    return {"generation":row[0],"coverage":row[1],
            "summary":json.loads(row[2]),"evidence_count":row[3]}
