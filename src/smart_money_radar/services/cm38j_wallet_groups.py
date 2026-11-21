"""Offline, immutable snapshots of shared RPC evidence; not ownership proof."""
from contextlib import nullcontext
from datetime import datetime,timezone
from hashlib import sha256
import json
from smart_money_radar.services.wallet_consensus import shared_evidence_groups
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.collector_authority import collector_write

def _time(t):
    t=datetime.fromisoformat(t) if isinstance(t,str) else t
    if not isinstance(t,datetime) or t.utcoffset() is None:raise ValueError("aware time required")
    return t.astimezone(timezone.utc)

def _encode(p):
    return json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False)

def _hash(p):
    return sha256(_encode(p).encode()).hexdigest()

class GroupEvidenceLimit(ValueError):
    """The wallet group cannot be reconstructed within the requested bound."""


def build_groups(conn,*,wallets,cutoff,max_links=None):
    end=_time(cutoff)
    if end>datetime.now(timezone.utc) or not wallets or len(wallets)>256 or len(set(wallets))!=len(wallets):
        raise ValueError("invalid group scope")
    if max_links is not None and (type(max_links) is not int or not 1 <= max_links <= 10_000):
        raise ValueError("invalid group evidence limit")
    members=[]; evidence=[]
    remaining = max_links
    tables = {name for name, in conn.execute(
        """SELECT name FROM sqlite_master WHERE type='table'
           AND name IN ('cm38_economic_evidence_links', 'cm38_rpc_observations')"""
    )}
    exists = "cm38_economic_evidence_links" in tables
    if exists and "cm38_rpc_observations" not in tables:
        raise ValueError("RPC archive missing from wallet evidence index")
    for wallet in sorted(wallets):
        signatures=set()
        if exists:
            query = """SELECT l.signature,l.entity_id,l.evidence_id,l.linked_at,r.radar,r.signature,
                             r.available_at,r.metadata,r.metadata_sha,r.raw
                FROM cm38_economic_evidence_links l LEFT JOIN cm38_rpc_observations r USING(evidence_id)
                WHERE l.radar='smart_money' AND l.wallet_address=?
                  AND l.entity_type='wallet_transaction' AND l.linked_at<=?"""
            args = (wallet, end.isoformat())
            if remaining is not None:
                query += " LIMIT ?"
                args += (remaining + 1,)
            for sig,entity_id,eid,linked,radar,index_signature,available,*raw in conn.execute(query,args):
                if remaining is not None:
                    if remaining == 0:
                        raise GroupEvidenceLimit("wallet group evidence limit reached")
                    remaining -= 1
                linked_at = _time(linked)
                if linked_at > end:
                    continue
                if raw[0] is None:
                    raise ValueError("missing RPC evidence for wallet link")
                observation = RpcObservationJournal._read(eid, raw)
                m = observation["metadata"]
                if (entity_id != sig
                        or (radar,index_signature,available) != ("smart_money",sig,m["available_at"])
                        or m["radar"]!="smart_money" or m["signature"]!=sig
                        or set(observation["evidence"].reasons) - {
                            "provider_independent_attestation_missing",
                            "finalization_independent_attestation_missing",
                            "finalized_not_requested",
                        }
                        or _time(m["available_at"]) > linked_at):
                    raise ValueError("group evidence conflict")
                tx=json.loads(raw[2])["result"]
                keys=tx["transaction"]["message"].get("accountKeys",[])
                addresses=[k if isinstance(k,str) else k.get("pubkey") for k in keys]
                if wallet not in addresses:raise ValueError("wallet absent from RPC")
                signatures.add(sig)
                evidence.append({"wallet":wallet,"signature":sig,"evidence_id":eid,"raw_sha256":m["raw_sha256"],"available_at":m["available_at"],"linked_at":linked})
        members.append((wallet,tuple(sorted(signatures))))
    groups=shared_evidence_groups(members)
    payload={"version":"CM64-1","radar":"smart_money","cutoff":end.isoformat(),"wallets":sorted(wallets),
        "groups":[list(g) for g in groups],"evidence":sorted(evidence,key=_encode),
        "reason":"shared_transaction_evidence_not_common_ownership","independent_wallets":0,
        "status":"NOT_COMPUTABLE","operational_authorized":False}
    return {**payload,"sha256":_hash(payload)}


def read_wallet_group_audit(store, *, wallets, cutoff, max_links):
    """Read a bounded local dependency audit without creating a snapshot."""
    unavailable = {
        "receipt": None,
        "independent_wallets": 0,
        "operational_authorized": False,
    }
    if not wallets:
        return {**unavailable, "status": "UNKNOWN", "reason": "wallet_group_scope_empty"}
    if len(wallets) > 256:
        return {**unavailable, "status": "UNKNOWN", "reason": "wallet_group_scope_limit"}
    if _time(cutoff) > datetime.now(timezone.utc):
        return {**unavailable, "status": "UNKNOWN", "reason": "wallet_group_future_cutoff"}
    try:
        with store._connection_scope() as conn, (nullcontext() if conn.in_transaction else conn):
            if not conn.in_transaction:
                conn.execute("BEGIN")
            receipt = build_groups(conn, wallets=wallets, cutoff=cutoff, max_links=max_links)
    except GroupEvidenceLimit:
        return {**unavailable, "status": "UNKNOWN", "reason": "wallet_group_evidence_limit"}
    except (ValueError, TypeError, KeyError, AttributeError):
        return {**unavailable, "status": "CONFLICTED", "reason": "wallet_group_evidence_conflict"}
    if not receipt["evidence"]:
        return {**unavailable, "status": "UNKNOWN", "reason": "wallet_group_evidence_missing"}
    return {
        **unavailable,
        "status": "LOCAL_EVIDENCE_LINKED",
        "reason": receipt["reason"],
        "receipt": receipt,
    }

def persist_groups(store,*,wallets,cutoff):
    with store._connection_scope() as c,collector_write(c,getattr(store,"_collector_authority",None),"smart_money"):
        receipt=build_groups(c,wallets=wallets,cutoff=cutoff)
        c.execute("""CREATE TABLE IF NOT EXISTS cm38j_wallet_groups(
            scope TEXT NOT NULL,cutoff TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,
            PRIMARY KEY(scope,cutoff))""")
        for action in ("UPDATE","DELETE"):
            c.execute("CREATE TRIGGER IF NOT EXISTS cm38j_groups_no_"+action.lower()+" BEFORE "+action+" ON cm38j_wallet_groups BEGIN SELECT RAISE(ABORT,'immutable group'); END")
        key=(_hash(receipt["wallets"]),receipt["cutoff"])
        target=(_encode(receipt),receipt["sha256"])
        old=c.execute("SELECT payload,digest FROM cm38j_wallet_groups WHERE scope=? AND cutoff=?",key).fetchone()
        if old is not None and tuple(old)!=target:raise ValueError("divergent group replay")
        if old is None:c.execute("INSERT INTO cm38j_wallet_groups VALUES(?,?,?,?)",(*key,*target))
        return receipt
