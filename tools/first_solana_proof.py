"""One-shot, non-financial Solana mainnet proof collection for GitHub Actions.

Invoked ONLY by an explicit feature-branch workflow. Calls the existing
one-request read-only client. Publishes raw bytes and an audit manifest.
RPC agreement with this one endpoint is not independent finality proof.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from smart_money_radar.services.solana_public_rpc_read import fetch_public_finalized_transaction
from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID

ENDPOINT = "https://api.mainnet-beta.solana.com"
SOURCE = "solana-public-mainnet-triton"
# Recently indexed on a public explorer as finalized Raydium CPMM at slot 471039497.
# The explorer is a *lead*, not an RPC verification or reserve snapshot.
SIGNATURE = "23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
EXPECTED_SLOT = 471039497
OUTPUT = Path("/tmp/smr-first-proof")


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = fetch_public_finalized_transaction(
        endpoint=ENDPOINT, signature=SIGNATURE, enabled=True,
        source_id=SOURCE, timeout_seconds=12.0,
    )
    manifest = {
        "signature_requested": SIGNATURE,
        "slot_expected_from_explorer": EXPECTED_SLOT,
        "rpc_endpoint": ENDPOINT,
        "rpc_source": SOURCE,
        "requested_commitment": "finalized",
        "requests_sent": result.requests_sent,
        "rpc_status": result.status,
        "rpc_reasons": list(result.reasons),
        "collection_report_generated_at": datetime.now(timezone.utc).isoformat(),
        "independently_finalized": False,
        "provider_authenticated": False,
        "historical_reserves_verified": False,
        "executable_quote_verified": False,
        "financial_execution_authorized": False,
        "raw_preserved": False,
        "pool_identity_status": "UNKNOWN",
        "pool_state_verified": False,
        "vault_ownership_verified": False,
    }
    if result.evidence is not None:
        evidence = result.evidence
        raw = evidence.raw_payload
        file = OUTPUT / (SIGNATURE + ".raw.json")
        file.write_bytes(raw)
        manifest.update({
            "raw_preserved": True,
            "raw_file": file.name,
            "raw_sha256": sha256(raw).hexdigest(),
            "signature_in_rpc": evidence.signature,
            "slot_observed": evidence.slot,
            "observed_at": evidence.observed_at.isoformat(),
            "available_at": evidence.available_at.isoformat(),
            "rpc_status": evidence.status,
            "rpc_reasons": list(evidence.reasons),
            "source_independence": "UNVERIFIED",
        })
        try:
            payload = json.loads(raw)
            if evidence.slot != EXPECTED_SLOT:
                manifest["slot_mismatch"] = True
                manifest["pool_identity_status"] = "CONFLICTED"
            else:
                swaps = decode_raydium_cpmm_swaps(payload)
                if swaps:
                    identity = []
                    for swap in swaps:
                        identity.append({
                            "program_id": RAYDIUM_CPMM_PROGRAM_ID,
                            "instruction_index": swap.instruction_index,
                            "inner_instruction_index": swap.inner_instruction_index,
                            "pool": swap.accounts.pool_state,
                            "input_vault": swap.accounts.input_vault,
                            "output_vault": swap.accounts.output_vault,
                            "input_mint": swap.accounts.input_token_mint,
                            "output_mint": swap.accounts.output_token_mint,
                            "amm_config": swap.accounts.amm_config,
                        })
                    manifest["decoded_cpmm_swaps"] = identity
                    manifest["pool_identity_status"] = "INSTRUCTION_ACCOUNTS_DECODED_NOT_INDEPENDENTLY_VERIFIED"
                else:
                    manifest["pool_identity_status"] = "CPMM_SWAP_NOT_DECODED"
        except (ValueError, TypeError, KeyError) as exc:
            manifest["pool_identity_status"] = "DECODE_ERROR"
            manifest["decode_error_type"] = type(exc).__name__
    write_json(OUTPUT / "first-proof.manifest.json", manifest)
    # Concise, auditable Action logs. No raw JSON dumped into logs.
    for key in ("signature_requested", "slot_observed", "rpc_status",
                "raw_preserved", "raw_sha256", "pool_identity_status",
                "independently_finalized", "historical_reserves_verified"):
        print(f"SMR_PROOF {key}={manifest.get(key, 'UNKNOWN')}")
    print("SMR_PROOF manifest=first-proof.manifest.json")
    print("SMR_PROOF simulated_data=False")
    print("SMR_PROOF financial_execution_authorized=False")


if __name__ == "__main__":
    main()
