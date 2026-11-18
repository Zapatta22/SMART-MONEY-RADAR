#!/usr/bin/env python3
"""Auditoria redigida de cobertura de deltas nas operações DAMM v2.

Lê fixtures RAW localmente. Não exibe identificadores, valores ou caminhos;
não acessa rede/SQLite e não grava arquivos.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from smart_money_radar.data_sources.damm_v2_accounts import decode_damm_v2_swap_accounts
from smart_money_radar.data_sources.damm_v2_analyzer import analyze_damm_v2_swap_events
from smart_money_radar.data_sources.damm_v2_transfer_analyzer import (
    DammV2SwapTransferContext,
    analyze_damm_v2_transfer_evidence,
)
from smart_money_radar.data_sources.fixture_audit import audit_fixture
from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    decode_solana_token_account_balance_deltas,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    decode_solana_token_transfers,
)


def _resolved_keys(message: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("account keys ausentes")
    parsed = any(isinstance(item, dict) for item in raw)
    keys = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("account key inválida")
        keys.append(key)
    if not parsed:
        loaded = meta.get("loadedAddresses") or {}
        if not isinstance(loaded, dict):
            raise ValueError("loaded addresses inválidos")
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError("loaded addresses inválidos")
            keys.extend(values)
    return keys


def summarize_four_account_delta_coverage(accounts: Any, delta_result: Any) -> str:
    """Classifica somente cobertura/sinais; nunca promove a reconciliação econômica."""
    required = (
        accounts.input_token_account,
        accounts.input_vault,
        accounts.output_vault,
        accounts.output_token_account,
    )
    if len(set(required)) != 4:
        return "ACCOUNT_ROLE_COLLISION"
    if not delta_result.complete:
        return "SNAPSHOT_SET_INCOMPLETE"
    by_account = {item.token_account: item for item in delta_result.deltas}
    if any(key not in by_account for key in required):
        return "FOUR_ACCOUNT_DELTA_MISSING"
    input_user = by_account[accounts.input_token_account]
    input_vault = by_account[accounts.input_vault]
    output_vault = by_account[accounts.output_vault]
    output_user = by_account[accounts.output_token_account]
    if (
        input_user.mint != accounts.input_mint
        or input_vault.mint != accounts.input_mint
        or output_vault.mint != accounts.output_mint
        or output_user.mint != accounts.output_mint
    ):
        return "MINT_ROLE_MISMATCH"
    if (
        input_user.delta_raw >= 0
        or input_vault.delta_raw <= 0
        or output_vault.delta_raw >= 0
        or output_user.delta_raw <= 0
    ):
        return "DELTA_SIGN_MISMATCH"
    return "FOUR_ACCOUNT_DELTAS_PRESENT"


def inspect_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tx = payload.get("result", payload)
    if not isinstance(tx, dict):
        return {"status": "STRUCTURE_INVALID", "swap_count": 0, "rows": []}
    transaction = tx.get("transaction")
    meta = tx.get("meta")
    message = transaction.get("message") if isinstance(transaction, dict) else None
    if not isinstance(meta, dict) or not isinstance(message, dict):
        return {"status": "STRUCTURE_INVALID", "swap_count": 0, "rows": []}
    try:
        keys = _resolved_keys(message, meta)
        associations = analyze_damm_v2_swap_events(payload)
        transfers = decode_solana_token_transfers(payload)
        deltas = decode_solana_token_account_balance_deltas(payload)
    except (TypeError, ValueError, KeyError):
        return {"status": "STRUCTURE_INVALID", "swap_count": 0, "rows": []}

    outer = message.get("instructions")
    groups = meta.get("innerInstructions") or []
    if not isinstance(outer, list) or not isinstance(groups, list):
        return {"status": "STRUCTURE_INVALID", "swap_count": 0, "rows": []}
    group_map = {
        item.get("index"): item.get("instructions")
        for item in groups
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    }
    contexts = []
    mapped = []
    for association in associations:
        if association.instruction is None:
            continue
        if association.status != "MATCHED" or association.event is None:
            mapped.append((association, None, "ASSOCIATION_UNRESOLVED"))
            continue
        try:
            if association.inner_instruction_index is None:
                instruction = outer[association.instruction_index]
            else:
                instruction = group_map[association.instruction_index][association.inner_instruction_index]
            accounts = decode_damm_v2_swap_accounts(instruction, keys, association.event)
        except (IndexError, KeyError, TypeError, ValueError):
            mapped.append((association, None, "ACCOUNT_MAPPING_INVALID"))
            continue
        contexts.append(DammV2SwapTransferContext(association, accounts))
        mapped.append((association, accounts, None))

    transfer_results = analyze_damm_v2_transfer_evidence(contexts, transfers)
    transfer_iter = iter(transfer_results)
    rows = []
    for association, accounts, error in mapped:
        if error:
            rows.append({"status": error, "delta_coverage": "NOT_EVALUATED"})
            continue
        evidence = next(transfer_iter)
        coverage = summarize_four_account_delta_coverage(accounts, deltas)
        if evidence.status != "ATTRIBUTED":
            coverage = "TRANSFER_ATTRIBUTION_NOT_CONFIRMED"
        rows.append({
            "status": evidence.status,
            "delta_coverage": coverage,
            "transfer_fee_review_required": evidence.transfer_fee_review_required,
        })
    return {
        "status": "AUDITED",
        "swap_count": len(rows),
        "rows": rows,
        "delta_issue_count": len(deltas.issues),
    }


def _inspect_manifest(manifest_path: Path, root: Path, index: int) -> dict[str, Any]:
    if manifest_path.is_symlink():
        return {"index": index, "status": "MANIFEST_INVALID"}
    try:
        resolved_root = root.resolve(strict=True)
        if manifest_path.resolve(strict=True).parent != resolved_root:
            return {"index": index, "status": "MANIFEST_INVALID"}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_name = manifest.get("raw_file") if isinstance(manifest, dict) else None
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
            return {"index": index, "status": "FIXTURE_INVALID"}
        raw_path = resolved_root / raw_name
        if raw_path.is_symlink() or raw_path.resolve(strict=True).parent != resolved_root:
            return {"index": index, "status": "FIXTURE_INVALID"}
        audit = audit_fixture(manifest_path)
        if not audit.valid:
            return {"index": index, "status": "FIXTURE_INVALID"}
        payload = json.loads(audit.raw_path.read_text(encoding="utf-8"))
        report = inspect_payload(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RuntimeError):
        return {"index": index, "status": "STRUCTURE_INVALID"}
    if report["status"] != "AUDITED":
        return {"index": index, "status": report["status"]}
    transfer_counts = Counter(row["status"] for row in report["rows"])
    delta_counts = Counter(row["delta_coverage"] for row in report["rows"])
    fee_review_count = sum(bool(row.get("transfer_fee_review_required")) for row in report["rows"])
    return {
        "index": index,
        "status": "AUDITED",
        "swap_count": report["swap_count"],
        "transfer_status_counts": dict(sorted(transfer_counts.items())),
        "delta_coverage_counts": dict(sorted(delta_counts.items())),
        "delta_issue_count": report["delta_issue_count"],
        "transfer_fee_review_count": fee_review_count,
    }


def build_report(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("diretório de fixtures inacessível")
    root = directory.resolve(strict=True)
    manifests = sorted(root.glob("*.manifest.json"), key=lambda p: p.name)
    reports = [_inspect_manifest(path, root, index) for index, path in enumerate(manifests, 1)]
    statuses = sorted({row["status"] for row in reports})
    return {
        "manifest_count": len(manifests),
        "audited_count": sum(row["status"] == "AUDITED" for row in reports),
        "status_counts": {status: sum(row["status"] == status for row in reports) for status in statuses},
        "reports": reports,
        "network_access": False,
        "database_access": False,
        "writes_files": False,
        "checkpoint_changes": False,
        "economic_reconciliation": False,
        "execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.directory)
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "network_access": False, "database_access": False,
                          "writes_files": False, "checkpoint_changes": False,
                          "economic_reconciliation": False, "execution_authorized": False},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["manifest_count"] == 0:
        return 2
    return 0 if report["audited_count"] == report["manifest_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
