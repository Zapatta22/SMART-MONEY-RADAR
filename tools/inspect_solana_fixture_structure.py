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


def _invalid(index: int, reason: str) -> dict[str, Any]:
    return {
        "index": index,
        "integrity_valid": False,
        "audit_errors": [reason],
        "structure_valid": False,
    }


def inspect_manifest(
    manifest_path: Path, index: int, root: Path | None = None
) -> dict[str, Any]:
    """Retorna metadados estruturais; rejeita symlinks e caminhos fora da raiz."""
    try:
        authorized_root = (root or manifest_path.parent).resolve(strict=True)
        if manifest_path.is_symlink():
            return _invalid(index, "manifesto simbólico não permitido")
        resolved_manifest = manifest_path.resolve(strict=True)
        if resolved_manifest.parent != authorized_root:
            return _invalid(index, "manifesto fora do diretório autorizado")

        manifest_data = json.loads(resolved_manifest.read_bytes())
        if not isinstance(manifest_data, dict):
            return _invalid(index, "manifesto inválido")
        raw_name = manifest_data.get("raw_file")
        if (
            not isinstance(raw_name, str)
            or Path(raw_name).name != raw_name
            or raw_name in ("", ".", "..")
        ):
            return _invalid(index, "nome do payload bruto inválido")
        raw_path = authorized_root / raw_name
        if raw_path.is_symlink():
            return _invalid(index, "payload bruto simbólico não permitido")
        if not raw_path.is_file():
            audit = audit_fixture(resolved_manifest)
            return {
                "index": index,
                "integrity_valid": audit.valid,
                "audit_errors": list(audit.errors),
                "structure_valid": False,
                "structure_error": "payload bruto ausente",
            }
        if raw_path.resolve(strict=True).parent != authorized_root:
            return _invalid(index, "payload bruto fora do diretório autorizado")
        audit = audit_fixture(resolved_manifest)
    except OSError:
        return _invalid(index, "manifesto ou payload inacessível")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _invalid(index, "manifesto ou payload JSON inválido")
    except ValueError as exc:
        # audit_fixture emits static validation messages and never includes file contents.
        return _invalid(index, str(exc))
    except RuntimeError:
        return _invalid(index, "caminho local inválido")

    report: dict[str, Any] = {
        "index": index,
        "integrity_valid": audit.valid,
        "audit_errors": list(audit.errors),
        "structure_valid": False,
    }
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
    wallet_fields = {"wallet_address", "monitored_wallet_address"}
    manifest_declares_wallet_address = bool(wallet_fields.intersection(manifest_data))

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


def build_report(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("diretório de fixtures inacessível")
    root = directory.resolve(strict=True)
    manifests = sorted(root.glob("*.manifest.json"), key=lambda path: path.name)
    reports = [
        inspect_manifest(path, index, root)
        for index, path in enumerate(manifests, 1)
    ]
    valid_count = sum(
        report["integrity_valid"] and report["structure_valid"]
        for report in reports
    )
    return {
        "manifest_count": len(manifests),
        "valid_count": valid_count,
        "invalid_count": len(manifests) - valid_count,
        "network_access": False,
        "database_access": False,
        "writes_files": False,
        "reports": reports,
    }


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
    try:
        output = build_report(args.directory)
    except ValueError as exc:
        print(json.dumps({
            "manifest_count": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "error": str(exc),
            "network_access": False,
            "database_access": False,
            "writes_files": False,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if output["manifest_count"] == 0:
        return 2
    return 0 if output["valid_count"] == output["manifest_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
