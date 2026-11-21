"""CM38A: immutable radar-scoped RPC observations, not finality attestations.

Reuse the existing Solana response verifier. Persist original response bytes and
first local availability in a fenced transaction. All imported evidence remains
UNATTESTED; neither a hash nor caller flags can authorize trading.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json
from smart_money_radar.services.solana_rpc_verification import (
    verify_transaction_rpc_response, reconcile_rpc_sources,
)
from smart_money_radar.storage.collector_authority import collector_write
from smart_money_radar.storage.event_store import SQLiteEventStore

RADARS=("launch","smart_money")

def _utc(value):
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError("timezone required")
    return value.astimezone(timezone.utc)

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def _strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError("duplicate RPC field")
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite RPC field")))

class RpcObservationJournal:
    """Existing SQLite storage and managed collector authority, no new DB path."""
    def __init__(self,store):
        if not isinstance(store,SQLiteEventStore): raise TypeError("SQLiteEventStore required")
        self.store=store

    def append(self,*,radar,signature,source_id,endpoint_host,raw_payload,
               observed_at,available_at,expected_slot=None):
        if self.store.read_only: raise PermissionError("read-only")
        if radar not in RADARS: raise ValueError("invalid radar")
        if not isinstance(raw_payload,bytes) or not 0<len(raw_payload)<=2_000_000:
            raise ValueError("invalid RPC payload size")
        observed=_utc(observed_at);available=_utc(available_at)
        # Caller timestamps describe reception, never independently authenticated.
        if available>datetime.now(timezone.utc): raise ValueError("future reception")
        _strict_json(raw_payload)
        ev=verify_transaction_rpc_response(raw_payload=raw_payload,signature=signature,
            source_id=source_id,endpoint_host=endpoint_host,observed_at=observed,
            available_at=available,expected_slot=expected_slot,requested_commitment="finalized")
        # Stable identity excludes a later retry timestamp; the original
        # observation record is immutable. A different RAW digest is retained.
        identity=sha256(_canonical([radar,signature,source_id,endpoint_host,ev.raw_sha256]).encode()).hexdigest()
        meta={"radar":radar,"signature":signature,"source_id":source_id,"endpoint_host":endpoint_host,
              "raw_sha256":ev.raw_sha256,"expected_slot":expected_slot,
              "observed_at":observed.isoformat(),"available_at":available.isoformat(),
              "status":ev.status,"slot":ev.slot,"commitment_requested":"finalized"}
        payload=_canonical(meta)
        # Use the same transaction/generation fence as the existing collectors.
        with self.store._connection_scope() as conn,collector_write(conn,getattr(self.store,"_collector_authority",None),radar):
            conn.execute("""CREATE TABLE IF NOT EXISTS cm38_rpc_observations(
                evidence_id TEXT PRIMARY KEY,radar TEXT NOT NULL,signature TEXT NOT NULL,
                available_at TEXT NOT NULL,metadata TEXT NOT NULL,metadata_sha TEXT NOT NULL,
                raw BLOB NOT NULL)""")
            row=conn.execute("SELECT metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?",(identity,)).fetchone()
            if row:
                prior=self._read(identity,row)
                if prior["metadata"]["expected_slot"]!=expected_slot:
                    raise ValueError("observation expected slot conflict")
                return identity
            conn.execute("INSERT INTO cm38_rpc_observations VALUES(?,?,?,?,?,?,?)",
                (identity,radar,signature,available.isoformat(),payload,sha256(payload.encode()).hexdigest(),raw_payload))
        return identity

    @staticmethod
    def _read(eid,row):
        payload,digest,raw=row
        if sha256(payload.encode()).hexdigest()!=digest: raise ValueError("metadata integrity conflict")
        meta=json.loads(payload)
        if sha256(raw).hexdigest()!=meta["raw_sha256"]: raise ValueError("RAW integrity conflict")
        identity=sha256(_canonical([meta["radar"],meta["signature"],meta["source_id"],meta["endpoint_host"],meta["raw_sha256"]]).encode()).hexdigest()
        if eid!=identity: raise ValueError("evidence identity conflict")
        _strict_json(raw)
        ev=verify_transaction_rpc_response(raw_payload=raw,signature=meta["signature"],
            source_id=meta["source_id"],endpoint_host=meta["endpoint_host"],
            observed_at=datetime.fromisoformat(meta["observed_at"]),available_at=datetime.fromisoformat(meta["available_at"]),
            expected_slot=meta["expected_slot"],requested_commitment=meta["commitment_requested"])
        if ev.slot!=meta["slot"] or ev.status!=meta["status"]: raise ValueError("verification conflict")
        return {"id":eid,"metadata":meta,"evidence":ev}

    def assess(self,*,radar,signature,cutoff):
        if radar not in RADARS: raise ValueError("invalid radar")
        point=_utc(cutoff)
        if point>datetime.now(timezone.utc): raise ValueError("future cutoff")
        evidence=[];ids=[];reasons=set()
        with self.store._connection_scope() as conn:
            conn.execute("BEGIN")
            exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38_rpc_observations'").fetchone()
            if exists:
                # Read all scoped rows, including later rows, so a corrupt index
                # coordinate cannot masquerade as safe historic availability.
                rows=conn.execute("SELECT evidence_id,radar,signature,available_at,metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE radar=? AND signature=? ORDER BY available_at,evidence_id",(radar,signature)).fetchall()
                for eid,r,s,available,payload,digest,raw in rows:
                    try:
                        item=self._read(eid,(payload,digest,raw))
                        meta=item["metadata"]
                        if (meta["radar"],meta["signature"],meta["available_at"])!=(r,s,available):
                            raise ValueError("scope integrity conflict")
                        if item["evidence"].available_at>point: continue
                        ids.append(eid);evidence.append(item["evidence"])
                    except (ValueError,TypeError,KeyError,AttributeError):
                        reasons.add("persisted_evidence_integrity_conflict")
        status,why=reconcile_rpc_sources(tuple(evidence))
        reasons.update(why)
        if "persisted_evidence_integrity_conflict" in reasons: status="CONFLICTED"
        if len({x.endpoint_host.casefold() for x in evidence})<2:
            reasons.add("distinct_endpoint_missing")
            if status!="CONFLICTED": status="UNKNOWN"
        return {"radar":radar,"signature":signature,"cutoff":point.isoformat(),
                "status":status,"evidence_ids":ids,"reasons":sorted(reasons),
                "historical_coverage":"UNKNOWN","operational_coverage":"UNKNOWN",
                "provider_authenticated":False,"independently_finalized":False,
                "economic_qualification":"UNKNOWN","prospective_paper_authorized":False,
                "live_authorized":False,"real_execution_authorized":False}
