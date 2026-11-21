"""CM35 offline discovery from first-publication swap archives.

Local observations can identify candidates, not establish ownership, complete
wallet history, profitability, authenticity or finalized source provenance.
No network scanning, transactions, instructions for trading or credentials.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict,dataclass
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from hashlib import sha256
import json

from smart_money_radar.services.wallet_signals import WalletSignalService
from smart_money_radar.services.wallet_consensus import WalletConsensusReport,WalletConsensusService
from smart_money_radar.services.synthetic_paper_ledger import _encode,_hash,_verify_record
from smart_money_radar.storage.event_store import SQLiteEventStore

@dataclass(frozen=True)
class WalletDiscoveryPolicy:
    window_seconds:int=86400*30
    min_transactions:int=3
    min_confidence:Decimal=Decimal(".8")
    max_receipts:int=5000
    quote_mints:tuple[str,...]=()
    manual_wallets:tuple[str,...]=()
    excluded_accounts:tuple[str,...]=()
    def __post_init__(self):
        if (type(self.window_seconds) is not int or not 1<=self.window_seconds<=86400*365
            or type(self.min_transactions) is not int or not 2<=self.min_transactions<=1000
            or type(self.max_receipts) is not int or not 1<=self.max_receipts<=10000
            or not isinstance(self.min_confidence,Decimal) or not self.min_confidence.is_finite()
            or not 0<=self.min_confidence<=1):
            raise ValueError("invalid discovery policy")
        for group in (self.quote_mints,self.manual_wallets,self.excluded_accounts):
            if (not isinstance(group,tuple) or len(group)>256 or len(set(group))!=len(group)
                or any(not isinstance(v,str) or not v.strip() for v in group)):
                raise ValueError("invalid discovery scope")

def _time(v):
    t=datetime.fromisoformat(v) if isinstance(v,str) else v
    if not isinstance(t,datetime) or t.utcoffset() is None: raise ValueError("timezone required")
    return t.astimezone(timezone.utc)

def _raw(row,cutoff):
    """Inspect locally archived RAW, without granting provider attestation."""
    payload=row.get("payload_json")
    if not isinstance(payload,str): return None,("raw_missing",)
    try:
        raw=json.loads(payload)
        tx=raw.get("result",raw)
        meta=tx["meta"]
        sigs=tx["transaction"]["signatures"]
        observed=_time(row["observed_at"])
        if observed>cutoff or observed>_time(row["available_at"]):
            return None,("raw_not_available_at_receipt",)
        if (not isinstance(sigs,list) or not sigs or sigs[0]!=row["signature"]
            or type(tx["slot"]) is not int or tx["slot"]<0 or tx["slot"]!=row["slot"]
            or not isinstance(meta,dict) or "err" not in meta or meta["err"] is not None
            or row["observation_wallet"]!=row["wallet"] or row["chain"]!="solana"):
            return None,("raw_identity_or_execution_conflict",)
        if row.get("parse_status")=="parse_error": return None,("parser_error",)
        message=tx["transaction"].get("message")
        if not isinstance(message,dict):
            return None,("wallet_signer_unproven",)
        keys=message.get("accountKeys")
        if not isinstance(keys,list) or not keys:
            return None,("wallet_signer_unproven",)
        if all(isinstance(k,str) for k in keys):
            n=message.get("header",{}).get("numRequiredSignatures")
            if type(n) is not int or not 1<=n<=len(keys) or row["wallet"] not in keys[:n]:
                return None,("wallet_signer_unproven",)
        elif not any(isinstance(k,dict) and k.get("pubkey")==row["wallet"] and k.get("signer") is True for k in keys):
            return None,("wallet_signer_unproven",)
        return sha256(payload.encode()).hexdigest(),()
    except (ValueError,TypeError,KeyError,AttributeError,IndexError):
        return None,("raw_unparseable",)

def discover_wallets(store,*,as_of,policy:WalletDiscoveryPolicy=WalletDiscoveryPolicy()):
    """Recompute from bounded archived inputs; manual wallets supplement discovery."""
    if not isinstance(store,SQLiteEventStore) or not isinstance(policy,WalletDiscoveryPolicy):
        raise TypeError("discovery needs SQLiteEventStore and policy")
    point=_time(as_of)
    rows=store.list_wallet_discovery_receipts(limit=policy.max_receipts+1)
    truncated=len(rows)>policy.max_receipts
    candidates={}
    signatures=defaultdict(set)
    operations={}
    global_reasons=set()
    if truncated: global_reasons.add("bounded_archive_truncated")
    def profile(wallet):
        return candidates.setdefault(wallet,{"wallet":wallet,"origins":set(),"observations":[],
            "reasons":set(),"indicators":set(),"evidence":[],"receipts":[]})
    for w in policy.manual_wallets: profile(w)["origins"].add("MANUAL_COMPLEMENT")
    for row in rows[:policy.max_receipts]:
        try:
            available=_time(row["available_at"])
            if available>point: continue
            occurred=_time(row["occurred_at"])
            if occurred<point-timedelta(seconds=policy.window_seconds): continue
        except (ValueError,TypeError,KeyError):
            global_reasons.add("invalid_receipt_timestamp")
            continue
        w=row.get("wallet")
        if not isinstance(w,str) or not w.strip():
            global_reasons.add("wallet_identity_missing");continue
        p=profile(w)
        p["origins"].add("ARCHIVED_SWAP_RECEIPT")
        p["observations"].append(available)
        op=row.get("operation_id");sig=row.get("signature")
        if not all(isinstance(v,str) and v.strip() for v in (op,sig,row.get("program"),row.get("pool"),
                row.get("input_mint"),row.get("output_mint"))):
            p["reasons"].add("missing_receipt_identity");continue
        fingerprint=_hash(_encode(row))
        if op in operations:
            prior,priorwallet=operations[op]
            if prior!=fingerprint:
                p["reasons"].add("duplicate_operation_conflict")
                profile(priorwallet)["reasons"].add("duplicate_operation_conflict")
            continue
        operations[op]=(fingerprint,w)
        signatures[sig].add(w)
        try:
            conf=Decimal(row["confidence"])
            quantities=[Decimal(row[k]) for k in ("input_amount","output_amount")]
            if not conf.is_finite() or not 0<=conf<=1 or any(not v.is_finite() or v<=0 for v in quantities):
                raise ValueError("invalid numeric receipt")
        except (ValueError,TypeError,ArithmeticError,KeyError):
            p["reasons"].add("invalid_receipt_amount_or_confidence");continue
        if occurred>available:
            p["reasons"].add("receipt_time_conflict");continue
        if row["input_mint"]==row["output_mint"] or row["side"] not in ("BUY","SELL"):
            p["indicators"].add("non_directional_or_same_mint");continue
        if row["program"]==w or w in policy.excluded_accounts:
            p["indicators"].add("program_or_excluded_account");continue
        if conf<policy.min_confidence:
            p["indicators"].add("low_classification_confidence");continue
        quotes=set(policy.quote_mints)
        im,om=row["input_mint"],row["output_mint"]
        if not quotes or (im in quotes)==(om in quotes):
            p["reasons"].add("quote_scope_unknown");continue
        side="BUY" if im in quotes else "SELL"
        if side!=row["side"]:
            p["reasons"].add("direction_conflict");continue
        digest,issues=_raw(row,point)
        if issues:
            p["reasons"].update(issues);continue
        p["evidence"].append({"operation_id":op,"signature":sig,"local_raw_sha256":digest,
            "available_at":available.isoformat(),"program":row["program"],"pool":row["pool"],
            "side":side,"token":om if side=="BUY" else im,"quote_mint":im if side=="BUY" else om})
        p["receipts"].append((sig,side))
    shared={s for s,ws in signatures.items() if len(ws)>1}
    related=defaultdict(set)
    for sig in shared:
        for wallet in signatures[sig]:
            related[wallet].update(signatures[sig]-{wallet})
            candidates[wallet]["indicators"].add("shared_transaction_possible_relation")
    result=[]
    for wallet,p in candidates.items():
        indicators=p["indicators"]
        reasons=p["reasons"]|global_reasons
        per_sig=defaultdict(set)
        for sig,side in p["receipts"]:per_sig[sig].add(side)
        for sig,sides in per_sig.items():
            if len(sides)>1: indicators.add("opposing_sides_same_signature")
        clean={sig:next(iter(sides)) for sig,sides in per_sig.items() if len(sides)==1 and sig not in shared}
        buy=sum(v=="BUY" for v in clean.values());sell=sum(v=="SELL" for v in clean.values())
        if wallet in policy.excluded_accounts:indicators.add("explicitly_excluded_account")
        conflict=bool(reasons&{"raw_identity_or_execution_conflict","duplicate_operation_conflict",
            "receipt_time_conflict","direction_conflict","invalid_receipt_amount_or_confidence"})
        excluded=bool(indicators&{"program_or_excluded_account","explicitly_excluded_account"})
        potentially_related=bool(indicators&{"shared_transaction_possible_relation","opposing_sides_same_signature"})
        status="BLOCKED" if conflict else "DISQUALIFIED" if excluded or potentially_related else (
            "OBSERVED" if clean else "CANDIDATE")
        if len(clean)<policy.min_transactions:reasons.add("insufficient_distinct_local_transactions")
        reasons.update(("historical_coverage_unknown","external_raw_attestation_missing",
            "economic_performance_unverified","wallet_independence_unverified","liquidity_costs_unverified"))
        score=None if truncated or conflict or excluded or potentially_related else min(100,len(clean)*5)
        observed=sorted(p["observations"])
        result.append({"wallet":wallet,"radar":"smart_money","origins":sorted(p["origins"]),
            "first_observed_at":observed[0].isoformat() if observed else None,
            "last_observed_at":observed[-1].isoformat() if observed else None,
            "as_of":point.isoformat(),"local_distinct_transactions":len(clean),
            "verified_operations":None,"buy_count":buy,"sell_count":sell,
            "realized_pnl":None,"win_rate":None,"realized_return":None,"drawdown":None,
            "average_holding_seconds":None,"exposure":None,"early_entries":None,
            "fees":None,"liquidity":None,"consistency":None,
            "score":score,"score_type":"LOCAL_OBSERVATION_COUNT_ONLY","confidence":"UNKNOWN",
            "evidence_quality":"CONFLICTED" if conflict else "UNKNOWN","coverage":"UNKNOWN",
            "status":status,"eligible_for_consensus":False,"qualified":False,
            "related_wallet_candidates":sorted(related[wallet]),"indicators":sorted(indicators),
            "reasons":sorted(reasons),"evidence":sorted(p["evidence"],key=lambda x:x["operation_id"]),
            "operational_authorized":False})
    result.sort(key=lambda p:(p["score"] is None,-(p["score"] or 0),p["wallet"]))
    report={"as_of":point.isoformat(),"origin":"LOCAL_SWAP_ARCHIVE","scope":"BOUNDED_ARCHIVE",
        "coverage":"UNKNOWN","truncated":truncated,"policy":json.loads(_encode(asdict(policy))),
        "profiles":result,"qualified_count":0,"operational_authorized":False,
        "global_reasons":sorted(global_reasons)}
    report["snapshot_id"]="wallets:"+_hash(_encode(report))
    return report

def persist_wallet_snapshot(store,*,as_of,policy=WalletDiscoveryPolicy()):
    """Append immutable point-in-time snapshot; no network/operational writes."""
    if store.read_only: raise ValueError("read-only")
    report=discover_wallets(store,as_of=as_of,policy=policy)
    payload=_encode(report);digest=_hash(payload);policy_sha=_hash(_encode(report["policy"]))
    with store._connection_scope() as conn,conn:
        conn.execute("BEGIN IMMEDIATE")
        old=conn.execute("SELECT payload,payload_sha FROM cm35_wallet_profiles WHERE snapshot_id=?",
            (report["snapshot_id"],)).fetchone()
        if old is not None and old!=(payload,digest):raise ValueError("wallet snapshot conflict")
        conn.execute("INSERT OR IGNORE INTO cm35_wallet_profiles VALUES(?,?,?,?,?)",
            (report["snapshot_id"],report["as_of"],policy_sha,payload,digest))
    return report

def read_wallet_snapshots(store,*,limit=10):
    if not isinstance(store,SQLiteEventStore):return []
    if type(limit) is not int or not 1<=limit<=100:raise ValueError("snapshot limit")
    with store._connection_scope() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='cm35_wallet_profiles'").fetchone():return []
        rows=conn.execute("SELECT snapshot_id,cutoff,policy_sha,payload,payload_sha FROM cm35_wallet_profiles ORDER BY cutoff DESC,snapshot_id LIMIT ?",(limit,)).fetchall()
    result=[]
    for sid,cutoff,policy_sha,payload,digest in rows:
        try:
            report=_verify_record((payload,digest))
            identity=dict(report);identity.pop("snapshot_id")
            if (report["snapshot_id"]!=sid or "wallets:"+_hash(_encode(identity))!=sid
                or report["as_of"]!=cutoff or _hash(_encode(report["policy"]))!=policy_sha
                or report["operational_authorized"] is not False or report["qualified_count"]!=0
                or any(p["eligible_for_consensus"] or p["qualified"] for p in report["profiles"])):
                raise ValueError("profile evidence conflict")
            result.append(report)
        except (ValueError,TypeError,KeyError):
            result.append({"snapshot_id":sid,"status":"CONFLICTED","profiles":[],"operational_authorized":False})
    return result

def qualified_consensus_at(store,*,as_of,policy,program,pool,base_mint,quote_mint,
                           window,max_publication_delay,min_confidence):
    """Automatic qualification gate before the existing consensus algorithm."""
    report=discover_wallets(store,as_of=as_of,policy=policy)
    eligible=tuple(p["wallet"] for p in report["profiles"] if p["eligible_for_consensus"]
        and p["status"]=="QUALIFIED" and p["confidence"]!="UNKNOWN")
    if not eligible:
        consensus=WalletConsensusReport("INSUFFICIENT",0,0,
            tuple(p["wallet"] for p in report["profiles"]),(),False,False,
            ("no_economically_qualified_wallets","independence_unverified"))
    else:
        consensus=WalletConsensusService(WalletSignalService(store)).get_report(
            wallets=eligible,program=program,pool=pool,base_mint=base_mint,quote_mint=quote_mint,
            as_of=_time(as_of),window=window,max_publication_delay=max_publication_delay,
            min_confidence=min_confidence)
    return {"snapshot_id":report["snapshot_id"],"qualified_wallets":list(eligible),
        "consensus":asdict(consensus),"operational_authorized":False}
