"""CM38D/Geyser: contextual linkage of immutable account frames and RPC RAW.

Account notifications lack a transaction signature. Linking by time/session
therefore cannot prove inclusion, order, finalization or economic causality.
The immutable context joins must NEVER qualify an operation or open CM39.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path

from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.collector_authority import collector_write
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

def link_geyser_rpc_context(events:SQLiteEventStore,geyser:SQLiteGeyserRawStore,*,
                            frame_id:int,evidence_id:str,cutoff:datetime):
    if not isinstance(events,SQLiteEventStore) or not isinstance(geyser,SQLiteGeyserRawStore):
        raise TypeError("existing raw stores required")
    if events.read_only or not Path(events.database_path).samefile(geyser.database_path):
        raise ValueError("both archives must be in the same writable SQLite database")
    if type(frame_id) is not int or frame_id<1 or not isinstance(evidence_id,str) or len(evidence_id)!=64:
        raise ValueError("invalid evidence identity")
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff with timezone required")
    cutoff=cutoff.astimezone(timezone.utc)
    if cutoff>datetime.now(timezone.utc): raise ValueError("future cutoff")
    with events._connection_scope() as conn,collector_write(conn,getattr(events,"_collector_authority",None),"launch"):
        frame=conn.execute(
            """SELECT source_id,stream_id,stream_sequence,frame_kind,payload_bytes,
                      payload_sha256,status,received_at FROM geyser_wire_frames WHERE frame_id=?""",
            (frame_id,)
        ).fetchone()
        if frame is None: raise ValueError("unknown Geyser frame")
        source,stream,seq,kind,raw,digest,status,received_at=frame
        if status!="accepted" or kind!="account" or not isinstance(raw,bytes):
            raise ValueError("only accepted account frames can be contextual evidence")
        if sha256(raw).hexdigest()!=digest:
            raise ValueError("Geyser RAW hash conflict")
        frame_at=datetime.fromisoformat(received_at)
        if frame_at.utcoffset() is None or frame_at>cutoff:
            raise ValueError("future or untimezoned account frame")
        row=conn.execute(
            "SELECT metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?",
            (evidence_id,)
        ).fetchone()
        if row is None: raise ValueError("RPC RAW not found")
        verified=RpcObservationJournal._read(evidence_id,row)
        meta=verified["metadata"]
        if meta["radar"]!="launch":raise ValueError("radar mismatch")
        available=datetime.fromisoformat(meta["available_at"])
        if available>cutoff: raise ValueError("RPC not yet available at cutoff")
        conn.execute("""CREATE TABLE IF NOT EXISTS cm38_geyser_rpc_context (
            frame_id INTEGER NOT NULL, evidence_id TEXT NOT NULL,
            frame_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
            link_quality TEXT NOT NULL CHECK(link_quality='UNKNOWN'),
            PRIMARY KEY(frame_id,evidence_id),
            FOREIGN KEY(frame_id) REFERENCES geyser_wire_frames(frame_id),
            FOREIGN KEY(evidence_id) REFERENCES cm38_rpc_observations(evidence_id))""")
        previous=conn.execute(
            "SELECT frame_sha256,link_quality FROM cm38_geyser_rpc_context WHERE frame_id=? AND evidence_id=?",
            (frame_id,evidence_id)
        ).fetchone()
        if previous is not None and previous!=(digest,"UNKNOWN"):
            raise ValueError("context link integrity conflict")
        if previous is None:
            conn.execute("INSERT INTO cm38_geyser_rpc_context VALUES (?,?,?,?,?)",
                (frame_id,evidence_id,digest,datetime.now(timezone.utc).isoformat(),"UNKNOWN"))
    return {"frame_id":frame_id,"evidence_id":evidence_id,"frame_sha256":digest,
            "rpc_signature":meta["signature"],"frame_source":source,"stream_id":stream,
            "sequence":seq,"relation":"TEMPORAL_CONTEXT_ONLY",
            "economic_causality":"UNKNOWN","transaction_inclusion":"UNKNOWN",
            "historical_coverage":"UNKNOWN","operational_authorized":False,
            "prospective_paper_authorized":False,
            "reasons":("account_frame_has_no_transaction_signature",
                       "independent_provider_authentication_unknown")}
