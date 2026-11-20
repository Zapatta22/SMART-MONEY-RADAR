"""Single opt-in second-source RPC read for the first real Solana CPMM proof.

Never sends transactions, buys, uses credentials, or conflates agreeing
endpoints with infrastructure independence. Only one getTransaction request.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from smart_money_radar.services.solana_public_rpc_read import fetch_public_finalized_transaction
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps

FIRST = Path("data/evidence/mainnet/2026-11-20")
MANIFEST = json.loads((FIRST / "first-proof.manifest.json").read_bytes())
SIG = MANIFEST["signature_requested"]
SLOT = MANIFEST["slot_observed"]
POOL = MANIFEST["decoded_cpmm_swaps"][0]["pool"]
ENDPOINT = "https://solana-rpc.publicnode.com"
OUTPUT = Path("/tmp/smr-second-source-proof")


def capture() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "smr.rpc-second-source-proof.v1",
        "source_id": "solana-publicnode-rpc",
        "endpoint": ENDPOINT,
        "first_source_endpoint": MANIFEST["rpc_endpoint"],
        "first_source_raw_sha256": MANIFEST["raw_sha256"],
        "signature_requested": SIG,
        "expected_slot": SLOT,
        "expected_pool": POOL,
        "requested_commitment": "finalized",
        "independent_provider_proven": False,
        "independent_finality_proven": False,
        "historical_poolstate_verified": False,
        "historical_ammconfig_verified": False,
        "historical_reserves_verified": False,
        "economic_execution_authorized": False,
        "requests_sent": 0,
        "status": "UNKNOWN",
        "reasons": ["not_observed"],
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    result = fetch_public_finalized_transaction(
        endpoint=ENDPOINT, signature=SIG, enabled=True,
        source_id="solana-publicnode-rpc", timeout_seconds=12,
    )
    report["requests_sent"] = result.requests_sent
    report["status"] = result.status
    report["reasons"] = list(result.reasons)
    if result.evidence is not None:
        evidence = result.evidence
        raw = evidence.raw_payload
        out = OUTPUT / (SIG + ".second-source.raw.json")
        out.write_bytes(raw)
        report.update({
            "raw_file": out.name,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "slot": evidence.slot,
            "signature": evidence.signature,
            "observed_at": evidence.observed_at.isoformat(),
            "available_at": evidence.available_at.isoformat(),
            "source_agreement_on_slot": evidence.slot == SLOT,
            "source_agreement_on_signature": evidence.signature == SIG,
            "source_independence": "NOT_ATTESTED",
        })
        try:
            data = json.loads(raw)
            if data.get("result") and evidence.slot == SLOT:
                swaps = decode_raydium_cpmm_swaps(data)
                candidates = [
                    x for x in swaps if x.accounts.pool_state == POOL
                ]
                report["decoded_cpmm_swap_count"] = len(swaps)
                report["pool_instruction_match"] = bool(candidates)
                report["source_agreement_on_pool"] = bool(candidates)
                if candidates:
                    s = candidates[0]
                    reference = MANIFEST["decoded_cpmm_swaps"][0]
                    report["source_agreement_on_vaults"] = (
                        s.accounts.input_vault == reference["input_vault"]
                        and s.accounts.output_vault == reference["output_vault"]
                    )
                    report["source_agreement_on_mints"] = (
                        s.accounts.input_token_mint == reference["input_mint"]
                        and s.accounts.output_token_mint == reference["output_mint"]
                    )
                report["solana_network_fee_lamports"] = data["result"]["meta"].get("fee")
                original = json.loads((FIRST / MANIFEST["raw_file"]).read_bytes())
                primary = original["result"]
                secondary = data["result"]
                # Compare economically meaningful fields instead of expecting
                # byte-identical JSON responses from different nodes.
                subset = lambda tx: {
                    "slot": tx.get("slot"), "blockTime": tx.get("blockTime"),
                    "transaction": tx.get("transaction"),
                    "meta": tx.get("meta"),
                }
                canonical = lambda obj: hashlib.sha256(
                    json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                report["canonical_core_sha256_first"] = canonical(subset(primary))
                report["canonical_core_sha256_second"] = canonical(subset(secondary))
                report["canonical_core_exact_match"] = (
                    report["canonical_core_sha256_first"]
                    == report["canonical_core_sha256_second"]
                )
                report["solana_network_fee_matches"] = (
                    primary["meta"].get("fee") == secondary["meta"].get("fee")
                )
            else:
                report["pool_instruction_match"] = False
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            report["decode_error"] = type(exc).__name__
            report["status"] = "UNKNOWN"
            report["reasons"].append("decode_or_comparison_incomplete")
    (OUTPUT / "second-source.manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    for field in (
        "endpoint", "requests_sent", "status", "slot", "raw_sha256",
        "source_agreement_on_slot", "source_agreement_on_pool",
        "source_agreement_on_vaults", "canonical_core_exact_match",
        "independent_provider_proven", "historical_reserves_verified",
    ):
        print(f"SMR_SECOND {field}={report.get(field, 'UNKNOWN')}")
    print("SMR_SECOND no_financial_execution=True")


if __name__ == "__main__":
    capture()
