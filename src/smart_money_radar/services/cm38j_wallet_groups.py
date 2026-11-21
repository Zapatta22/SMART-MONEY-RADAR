"""Offline, immutable snapshots of shared RPC evidence; not ownership proof."""
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

def build_groups(conn,*,wallets,cutoff):
    end=_time(cutoff)
    if end>datetime.now(timezone.utc) or not wallets or len(wallets)>256 or len(set(wallets))!=len(wallets):
        raise ValueError("invalid group scope")
    members=[]; evidence=[]
    exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm38_economic_evidence_links'").fetchone()
    for wallet in sorted(wallets):
        signatures=set()
        if exists:
            rows=conn.execute("""SELECT l.signature,l.evidence_id,l.linked_at,r.metadata,r.metadata_sha,r.raw
                FROM cm38_economic_evidence_links l JOIN cm38_rpc_observations r USING(evidence_id)
                WHERE l.radar='smart_money' AND l.wallet_address=? AND l.entity_type='wallet_transaction'""",(wallet,)).fetchall()
            for sig,eid,linked,*raw in rows:
                if _time(linked)>end:continue
                m=RpcObservationJournal._read(eid,raw)["metadata"]
                if _time(m["available_at"])>end:continue
                if m["radar"]!="smart_money" or m["signature"]!=sig or m["status"]=="CONFLICTED":
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
