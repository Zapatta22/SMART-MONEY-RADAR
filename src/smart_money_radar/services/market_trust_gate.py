"""CM38C / CM39 trust boundary. Observations are not independent attestations.

No caller-supplied boolean can upgrade a transport observation. A future
trusted verifier must publish its own evidence-backed contract before the
prospective execution gate can ever open.
"""
from smart_money_radar.services.solana_rpc_verification import RpcTransactionEvidence
from hashlib import sha256

def evaluate_market_trust(evidence,*,assessment):
    items=tuple(evidence)
    if any(not isinstance(x,RpcTransactionEvidence) for x in items): raise TypeError("RPC evidence required")
    intact=bool(items) and all(sha256(x.raw_payload).hexdigest()==x.raw_sha256 for x in items)
    same_identity=bool(items) and len({(x.signature,x.slot) for x in items})==1 and items[0].slot is not None
    distinct_hosts=len({x.endpoint_host.casefold() for x in items})
    finalized_requested=bool(items) and all(x.commitment_requested=="finalized" for x in items)
    return {"declared_sources":sorted({x.source_id for x in items}),
            "distinct_endpoint_hosts":distinct_hosts,
            "payload_integrity":"LOCAL_SHA256_MATCH" if intact else "UNKNOWN_OR_CONFLICTED",
            "identity_consistency":"LOCALLY_CONSISTENT" if same_identity and intact else "UNKNOWN_OR_CONFLICTED",
            "provider_agreement":assessment if intact else "UNKNOWN",
            "provider_identity":"UNKNOWN","independence":"UNKNOWN",
            "cryptographic_chain_inclusion":"UNKNOWN",
            "requested_commitment":"finalized" if finalized_requested else "MIXED_OR_UNVERIFIED",
            "finalization":"UNKNOWN","economic_reconciliation":"UNKNOWN",
            "historical_coverage":"UNKNOWN","operational_coverage":"UNKNOWN"}

def prospective_preflight(*,radar,assessment):
    if radar not in ("launch","smart_money"):raise ValueError("radar required")
    if not isinstance(assessment,dict) or assessment.get("radar")!=radar: raise ValueError("radar scope conflict")
    # CM38 transport observations do not contain an independent attestation.
    # Never accept fabricated affirmative flags or an alleged verified quote.
    return {"radar":radar,"status":"BLOCKED","capital_kind":"VIRTUAL_ONLY",
            "eligible_ticks":0,"prospective_authorized":False,"real_execution_authorized":False,
            "reasons":["independent_market_attestation_missing","economic_execution_evidence_missing",
                       "live_validation_and_human_gate_pending"]}
