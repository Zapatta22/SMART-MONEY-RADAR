"""CM38G: bounded, read-only per-radar and per-source RPC coverage audit.

An RPC getTransaction receipt witnesses one signature at one publication time.
It does NOT prove a stream interval or the absence of missing transactions.
Explicit gaps are evidence of partial coverage, never proof of completeness.
No writes, RPC/network calls, orders, synthetic ticks or provider endorsements.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json
from smart_money_radar.services.rpc_observation_journal import (
    RADARS,RpcObservationJournal,_utc
)
from smart_money_radar.storage.event_store import SQLiteEventStore

def assess_rpc_coverage(store:SQLiteEventStore,*,radar:str,start:datetime,end:datetime,
                        source_id:str|None=None,limit:int=2000):
    if not isinstance(store,SQLiteEventStore): raise TypeError("SQLiteEventStore required")
    if radar not in RADARS: raise ValueError("radar required")
    left,right=_utc(start),_utc(end)
    if not left<right<=datetime.now(timezone.utc):
        raise ValueError("invalid coverage interval or future end")
    if source_id is not None and (not isinstance(source_id,str) or not source_id.strip()):
        raise ValueError("invalid source id")
    if type(limit) is not int or not 1<=limit<=10000: raise ValueError("invalid bounded limit")
    observations=[];bad=[];seen=set();truncated=False
    with store._connection_scope() as conn:
        conn.execute("BEGIN")
        exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm38_rpc_observations'").fetchone()
        if exists:
            # Bounded snapshot includes all requested coordinates, including
            # an inconsistent index; filter times ONLY after integrity check.
            filters="WHERE radar=?"+(" AND source_id=?" if False else "")
            rows=conn.execute(
                "SELECT evidence_id,radar,signature,available_at,metadata,metadata_sha,raw "
                "FROM cm38_rpc_observations WHERE radar=? ORDER BY available_at,evidence_id LIMIT ?",
                (radar,limit+1)).fetchall()
            truncated=len(rows)>limit
            for eid,index_radar,index_sig,index_at,meta_text,digest,raw in rows[:limit]:
                try:
                    item=RpcObservationJournal._read(eid,(meta_text,digest,raw))
                    meta=item["metadata"]
                    if (meta["radar"],meta["signature"],meta["available_at"])!=(index_radar,index_sig,index_at):
                        raise ValueError("index conflict")
                    available=_utc(datetime.fromisoformat(meta["available_at"]))
                    if not left<=available<right or (source_id is not None and meta["source_id"]!=source_id):
                        continue
                    seen.add(eid)
                    observations.append((meta,item["evidence"]))
                except (ValueError,TypeError,KeyError,AttributeError):
                    bad.append(eid)
    sources={}
    signatures={}
    for meta,evidence in observations:
        key=meta["source_id"]
        group=sources.setdefault(key,{"source_id":key,"declared_endpoints":set(),
           "raw_evidence_ids":[],"signature_ids":set(),
           "confirmed_count":0,"finalized_requested_count":0,"other_commitments":0,
           "first_available_at":None,"last_available_at":None,
           "unattested_independence":True})
        group["declared_endpoints"].add(meta["endpoint_host"])
        group["raw_evidence_ids"].append(meta["radar"]+":"+meta["signature"]+":"+meta["raw_sha256"])
        group["signature_ids"].add(meta["signature"])
        available=meta["available_at"]
        group["first_available_at"]=min(group["first_available_at"] or available,available)
        group["last_available_at"]=max(group["last_available_at"] or available,available)
        commitment=meta["commitment_requested"]
        if commitment=="confirmed":group["confirmed_count"]+=1
        elif commitment=="finalized":group["finalized_requested_count"]+=1
        else:group["other_commitments"]+=1
        signatures.setdefault(meta["signature"],set()).add((meta["source_id"],meta["slot"]))
    reasons={"historical_coverage_unknown","operational_coverage_unknown",
             "stream_continuity_not_proven","source_identity_not_independently_authenticated"}
    if not observations:reasons.add("no_observations_in_interval")
    if truncated:reasons.add("bounded_archive_truncated")
    if bad:reasons.add("persisted_rpc_integrity_conflict")
    if any(len({slot for _,slot in values})>1 for values in signatures.values()):
        reasons.add("cross_source_slot_conflict")
    records=[]
    for group in sorted(sources.values(),key=lambda v:v["source_id"]):
        records.append({"source_id":group["source_id"],
            "declared_endpoint_hosts":tuple(sorted(group["declared_endpoints"])),
            "distinct_signatures":len(group["signature_ids"]),
            "rpc_receipt_count":len(group["raw_evidence_ids"]),
            "requested_commitments":{"confirmed":group["confirmed_count"],
                "finalized":group["finalized_requested_count"],
                "other":group["other_commitments"]},
            "first_available_at":group["first_available_at"],
            "last_available_at":group["last_available_at"],
            "coverage":"UNKNOWN","provider_identity":"UNKNOWN"})
    return {"radar":radar,"source_filter":source_id,
        "interval":{"start_inclusive":left.isoformat(),"end_exclusive":right.isoformat()},
        "sources":records,"distinct_signatures":len(signatures),
        "verified_local_receipts":len(observations),
        "corrupt_evidence_ids":tuple(sorted(bad)),
        "bounded_archive_truncated":truncated,
        "historical_coverage":"UNKNOWN","operational_coverage":"UNKNOWN",
        "state":"CONFLICTED" if bad or "cross_source_slot_conflict" in reasons else "UNKNOWN",
        "reasons":tuple(sorted(reasons)),
        "prospective_paper_authorized":False,"operational_authorized":False}
