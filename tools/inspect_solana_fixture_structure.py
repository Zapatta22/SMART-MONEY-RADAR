#!/usr/bin/env python3
"""Inspeciona a estrutura de fixtures Solana sem revelar identificadores sensíveis.

Somente leitura: não acessa RPC, não grava arquivos e não inicializa SQLite.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smart_money_radar.data_sources.fixture_audit import audit_fixture


def _count(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def inspect_manifest(manifest_path: Path, index: int) -> dict[str, Any]:
    """Retorna apenas metadados estruturais; nunca imprime endereços/assinaturas."""
    try:
        audit = audit_fixture(manifest_path)
    except OSError:
        return {
            "index": index,
            "integrity_valid": False,
            "audit_errors": ["manifesto inacessível"],
            "structure_valid": False,
        }
    except ValueError as exc:
        # ValueError messages from audit_fixture are static validation messages.
        return {
            "index": index,
            "integrity_valid": False,
            "audit_errors": [str(exc)],
            "structure_valid": False,
        }

    report: dict[str, Any] = {
        "index": index,
        "integrity_valid": audit.valid,
        "audit_errors": list(audit.errors),
        "structure_valid": False,
    }
    if not audit.raw_path.is_file():
        report["structure_error"] = "payload bruto ausente"
        return report

    try:
        payload = json.loads(audit.raw_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        report["structure_error"] = "payload bruto ilegível ou JSON inválido"
        return report

    if not isinstance(payload, dict):
        report["structure_error"] = "envelope RPC não é objeto JSON"
        return report

    result = payload.get("result")
    if not isinstance(result, dict):
        report["structure_error"] = "result RPC ausente ou inválido"
        return report

    transaction = result.get("transaction")
    message = transaction.get("message") if isinstance(transaction, dict) else None
    meta = result.get("meta")
    if not isinstance(transaction, dict) or not isinstance(message, dict):
        report["structure_error"] = "transaction/message ausente ou inválido"
        return report
    if not isinstance(meta, dict):
        report["structure_error"] = "meta ausente ou inválido"
        return report

    account_keys = message.get("accountKeys")
    instructions = message.get("instructions")
    inner_groups = meta.get("innerInstructions")
    pre_balances = meta.get("preTokenBalances")
    post_balances = meta.get("postTokenBalances")
    signatures = transaction.get("signatures")

    # Emit only known RPC field names; never echo arbitrary keys from input JSON.
    safe_fields = {
        "result_fields": {"slot", "version", "transaction", "meta", "blockTime"},
        "transaction_fields": {"signatures", "message"},
        "message_fields": {"accountKeys", "instructions", "addressTableLookups", "recentBlockhash"},
        "meta_fields": {"err", "innerInstructions", "preTokenBalances", "postTokenBalances",
                        "loadedAddresses", "fee", "computeUnitsConsumed", "logMessages"},
    }
    try:
        manifest_data = json.loads(audit.manifest_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        manifest_data = {}
    wallet_fields = {"wallet_address", "monitored_wallet_address"}
    manifest_declares_wallet_address = (
        isinstance(manifest_data, dict)
        and bool(wallet_fields.intersection(manifest_data))
    )

    report.update({
        "structure_valid": True,
        "result_fields": sorted(result.keys() & safe_fields["result_fields"]),
        "transaction_fields": sorted(transaction.keys() & safe_fields["transaction_fields"]),
        "message_fields": sorted(message.keys() & safe_fields["message_fields"]),
        "meta_fields": sorted(meta.keys() & safe_fields["meta_fields"]),
        "account_key_count": _count(account_keys),
        "top_level_instruction_count": _count(instructions),
        "inner_instruction_group_count": _count(inner_groups),
        "inner_instruction_count": (
            sum(len(group.get("instructions", [])) for group in inner_groups
                if isinstance(group, dict) and isinstance(group.get("instructions"), list))
            if isinstance(inner_groups, list) else None
        ),
        "pre_token_balance_count": _count(pre_balances),
        "post_token_balance_count": _count(post_balances),
        "pre_balances_with_owner_count": (
            sum(isinstance(item, dict) and isinstance(item.get("owner"), str)
                and bool(item.get("owner")) for item in pre_balances)
            if isinstance(pre_balances, list) else None
        ),
        "post_balances_with_owner_count": (
            sum(isinstance(item, dict) and isinstance(item.get("owner"), str)
                and bool(item.get("owner")) for item in post_balances)
            if isinstance(post_balances, list) else None
        ),
        "signature_count": _count(signatures),
        "slot_present": isinstance(result.get("slot"), int)
            and not isinstance(result.get("slot"), bool),
        "version_type": type(result.get("version")).__name__,
        "on_chain_status": (
            "failed" if meta.get("err") is not None
            else "success" if "err" in meta
            else "unknown"
        ),
        "manifest_declares_wallet_address": manifest_declares_wallet_address,
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("data/fixtures/raw"),
        help="Diretório com pares *.raw.json/*.manifest.json",
    )
    args = parser.parse_args()
    manifests = sorted(args.directory.glob("*.manifest.json"))
    if not manifests:
        print(json.dumps({
            "manifest_count": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "error": "nenhum manifesto encontrado",
        }, ensure_ascii=False, indent=2))
        return 2

    reports = [inspect_manifest(path, index) for index, path in enumerate(manifests, 1)]
    valid_count = sum(
        report["integrity_valid"] and report["structure_valid"]
        for report in reports
    )
    output = {
        "manifest_count": len(manifests),
        "valid_count": valid_count,
        "invalid_count": len(manifests) - valid_count,
        "network_access": False,
        "database_access": False,
        "writes_files": False,
        "reports": reports,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if valid_count == len(manifests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
