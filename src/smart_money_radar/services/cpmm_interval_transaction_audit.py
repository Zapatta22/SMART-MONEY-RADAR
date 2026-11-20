"""Strict offline reconciliation of observed CPMM interval transaction attempts.

Reuses first-party Raydium structural instruction decoder. A pool signature
listing is a *discovery hint*; fetched transactions independently must link
their own instruction to the correct pool. Account updates, fee accounting,
sequence completeness, provider identity and transaction indices are UNKNOWN
unless proven by the evidence; no financial execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from hashlib import sha256
import json
from typing import Literal

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.services.prospective_cpmm_history import CpmmCapture,CpmmHistoryDelta


@dataclass(frozen=True)
class IntervalTransaction:
    signature:str
    listed_slot:int
    observed_slot:int|None
    status:Literal["OBSERVED","UNKNOWN","CONFLICT"]
    reasons:tuple[str,...]
    raw_sha256:str|None
    observed_at:datetime|None
    available_at:datetime|None
    pool_instruction_verified:bool
    transaction_index:int|None=None
    stream_ordering_verified:bool=False
    economic_delta_attributable:bool=False


@dataclass(frozen=True)
class IntervalReconciliation:
    coverage:Literal["PARTIAL","UNKNOWN","CONFLICT"]
    listed_count:int
    verified_transactions:int
    unresolved_transactions:int
    pool_instruction_verified:int
    slot_range:tuple[int,int]
    reasons:tuple[str,...]
    economic_residual_high_raw:int|None=None
    economic_residual_wsol_lamports:int|None=None
    transaction_order_proven:bool=False
    account_write_stream_complete:bool=False
    executable_quote_proven:bool=False
    operation_authorized:bool=False


def _stamp(value:str|None)->datetime|None:
    if value is None:return None
    dt=datetime.fromisoformat(value)
    if dt.utcoffset() is None:raise ValueError("timestamp sem fuso")
    return dt.astimezone(timezone.utc)


def reconcile_interval_transactions(
    *,first:CpmmCapture,second:CpmmCapture,delta:CpmmHistoryDelta,
    listing_manifest:dict,listing_raw:bytes,tx_manifest:dict,
    tx_responses:dict[str,bytes],cutoff:datetime
)->tuple[IntervalReconciliation,tuple[IntervalTransaction,...]]:
    if not isinstance(cutoff,datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff inválido")
    if not isinstance(first,CpmmCapture) or not isinstance(second,CpmmCapture):
        raise TypeError("snapshots inválidos")
    if delta.first_capture_id!=first.capture_id or delta.second_capture_id!=second.capture_id:
        raise ValueError("delta de snapshots de outra origem")
    if not isinstance(listing_manifest,dict) or not isinstance(tx_manifest,dict):
        raise TypeError("manifestos inválidos")
    if not isinstance(listing_raw,bytes) or not listing_raw:
        raise ValueError("RAW da lista ausente")
    if sha256(listing_raw).hexdigest()!=listing_manifest.get("response_sha256"):
        raise ValueError("SHA lista de assinaturas divergente")
    if (listing_manifest.get("start_slot")!=first.observation.slot
        or listing_manifest.get("end_slot")!=second.observation.slot
        or listing_manifest.get("pool")!=first.observation.pool
        or listing_manifest.get("pool")!=second.observation.pool):
        raise ValueError("lista não pertence a este intervalo")
    if tx_manifest.get("listing_sha256")!=listing_manifest["response_sha256"]:
        raise ValueError("manifesto de transações aponta para outra lista")
    rows=json.loads(listing_raw).get("result")
    if not isinstance(rows,list):
        raise ValueError("RPC não retornou lista")
    low,high=first.observation.slot,second.observation.slot
    candidates={x["signature"]:x["slot"] for x in rows if (
        isinstance(x,dict) and type(x.get("slot")) is int
        and low<x["slot"]<=high and isinstance(x.get("signature"),str))}
    if len(candidates)!=len(listing_manifest.get("candidate_preview",[])):
        raise ValueError("lista duplicada ou preview incompleto")
    for row in listing_manifest["candidate_preview"]:
        if candidates.get(row["signature"])!=row["slot"]:
            raise ValueError("preview e lista de assinaturas divergentes")
    reports=tx_manifest.get("results")
    if not isinstance(reports,list) or len(reports)!=len(candidates):
        raise ValueError("resultados não correspondem às assinaturas candidatas")
    by_sig={x["signature"]:x for x in reports if isinstance(x,dict) and isinstance(x.get("signature"),str)}
    if len(by_sig)!=len(candidates) or set(by_sig)!=set(candidates):
        raise ValueError("assinatura duplicada, ausente ou extra")
    issues={"listing_not_proven_complete","account_writes_not_recorded",
            "same_slot_transaction_order_not_attested",
            "not_independently_finalized"}
    if listing_manifest.get("pagination_exhausted") is not True:
        issues.add("pagination_not_proven_exhausted")
    if listing_manifest.get("page_full"):
        issues.add("listing_reached_page_limit")
    if delta.coverage!="PARTIAL":
        issues.add("snapshot_comparison_not_valid")
    if tx_manifest.get("independently_finalized") is not False:
        issues.add("source_attestation_unproven")
    item_results=[]
    for signature,listed_slot in sorted(candidates.items(),key=lambda x:(x[1],x[0])):
        report=by_sig[signature]
        reasons=[]
        got_slot=None
        verified_pool=False
        status="UNKNOWN"
        observed=_stamp(report.get("observed_at"))
        available=_stamp(report.get("available_at"))
        raw=tx_responses.get(signature)
        digest=None
        if available is not None and available>cutoff.astimezone(timezone.utc):
            reasons.append("transaction_after_cutoff")
            status="CONFLICT"
        if (report.get("listed_slot")!=listed_slot
            or report.get("pool")!=listing_manifest["pool"]):
            reasons.append("manifest_slot_or_pool_conflict")
            status="CONFLICT"
        if raw is None:
            reasons.append("transaction_raw_missing")
        elif not isinstance(raw,bytes):
            reasons.append("transaction_raw_invalid")
            status="CONFLICT"
        else:
            digest=sha256(raw).hexdigest()
            if digest!=report.get("response_sha256"):
                reasons.append("transaction_raw_sha_conflict")
                status="CONFLICT"
            else:
                try:
                    payload=json.loads(raw)
                    transaction=payload.get("result")
                    if not isinstance(transaction,dict):
                        reasons.append("transaction_not_returned_by_rpc")
                    else:
                        got_slot=transaction["slot"]
                        got_sig=transaction["transaction"]["signatures"][0]
                        err=transaction["meta"]["err"]
                        if (got_slot!=listed_slot or got_sig!=signature
                            or err is not None or type(got_slot) is not int):
                            reasons.append("transaction_identity_or_success_conflict")
                            status="CONFLICT"
                        else:
                            # Pool in keys alone is insufficient; a CPMM swap
                            # instruction must actually bind to this pool.
                            swaps=decode_raydium_cpmm_swaps(payload)
                            verified_pool=any(s.accounts.pool_state==listing_manifest["pool"]
                                              for s in swaps)
                            if not verified_pool:
                                reasons.append("cpmm_pool_instruction_not_proven")
                            else:
                                if status!="CONFLICT":
                                    status="OBSERVED"
                except (ValueError,TypeError,KeyError,IndexError) as exc:
                    reasons.append("transaction_decode_failed:"+type(exc).__name__)
                    status="CONFLICT"
        if not reasons and status!="OBSERVED":
            reasons.append("insufficient_transaction_provenance")
        item_results.append(IntervalTransaction(
            signature=signature,listed_slot=listed_slot,observed_slot=got_slot,
            status=status,reasons=tuple(sorted(set(reasons))),raw_sha256=digest,
            observed_at=observed,available_at=available,
            pool_instruction_verified=verified_pool))
    unresolved=sum(x.status!="OBSERVED" for x in item_results)
    verified=sum(x.status=="OBSERVED" for x in item_results)
    if unresolved:issues.add("unresolved_pool_transactions")
    if any(x.status=="CONFLICT" for x in item_results):issues.add("transaction_conflict")
    coverage=("CONFLICT" if "transaction_conflict" in issues
              else "PARTIAL" if delta.coverage=="PARTIAL" else "UNKNOWN")
    # Even if all candidate transactions were observed, a bounded signature
    # page is no substitute for a complete write stream or ordering proof.
    return IntervalReconciliation(
        coverage=coverage,listed_count=len(candidates),
        verified_transactions=verified,unresolved_transactions=unresolved,
        pool_instruction_verified=sum(x.pool_instruction_verified for x in item_results),
        slot_range=(low,high),reasons=tuple(sorted(issues)),
    ),tuple(item_results)
