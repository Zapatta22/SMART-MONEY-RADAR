#!/usr/bin/env python3
"""Planeja importação histórica Solana em dry-run, sem rede, SQLite ou gravações."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smart_money_radar.data_sources.fixture_audit import audit_fixture


def _load_wallet_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("arquivo de mapeamento inacessível")
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("arquivo de mapeamento inválido") from exc
    if not isinstance(value, dict):
        raise ValueError("mapeamento deve ser objeto JSON")
    result: dict[str, str] = {}
    for signature, wallet in value.items():
        if (not isinstance(signature, str) or not signature
                or not isinstance(wallet, str) or not wallet.strip()):
            raise ValueError("mapeamento contém entrada inválida")
        result[signature] = wallet
    return result


def _safe_manifest(path: Path, root: Path) -> tuple[str, dict[str, Any] | None]:
    if path.is_symlink():
        return "MANIFEST_INVALID", None
    try:
        resolved = path.resolve(strict=True)
        if resolved.parent != root.resolve(strict=True):
            return "MANIFEST_INVALID", None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError):
        return "MANIFEST_INVALID", None
    if not isinstance(data, dict):
        return "MANIFEST_INVALID", None
    return "", data


def plan_manifest(manifest_path: Path, root: Path, wallet_map: dict[str, str], index: int) -> dict[str, Any]:
    """Retorna apenas índice e estado; não ecoa caminhos nem identificadores."""
    state, manifest = _safe_manifest(manifest_path, root)
    if state:
        return {"index": index, "status": state}
    try:
        audit = audit_fixture(manifest_path)
    except (OSError, ValueError):
        return {"index": index, "status": "MANIFEST_INVALID"}
    if not audit.valid:
        joined = " ".join(audit.errors).lower()
        if "sha-256" in joined:
            status = "HASH_MISMATCH"
        elif "assinatura" in joined:
            status = "SIGNATURE_MISMATCH"
        elif "slot" in joined:
            status = "SLOT_MISMATCH"
        else:
            status = "MANIFEST_INVALID"
        return {"index": index, "status": status}

    raw_path = audit.raw_path
    try:
        if raw_path.is_symlink() or raw_path.resolve(strict=True).parent != root.resolve(strict=True):
            return {"index": index, "status": "MANIFEST_INVALID"}
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError):
        return {"index": index, "status": "MANIFEST_INVALID"}
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        return {"index": index, "status": "MANIFEST_INVALID"}
    result = payload["result"]
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return {"index": index, "status": "MANIFEST_INVALID"}
    if meta.get("err") is not None:
        return {"index": index, "status": "ON_CHAIN_FAILED"}

    signature = audit.signature
    mapped_wallet = wallet_map.get(signature)
    manifest_wallet = manifest.get("wallet_address", manifest.get("monitored_wallet_address"))
    if mapped_wallet and manifest_wallet and mapped_wallet != manifest_wallet:
        return {"index": index, "status": "WALLET_MAPPING_CONFLICT"}
    if not mapped_wallet and not manifest_wallet:
        return {"index": index, "status": "WALLET_UNASSIGNED"}
    # Assignment is explicit but still requires operator review and protocol coverage analysis.
    return {"index": index, "status": "READY_FOR_REVIEW"}


def build_plan(directory: Path, wallet_map_path: Path | None = None) -> dict[str, Any]:
    """Executa planejamento somente leitura; não inicializa EventStore."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("diretório de fixtures inacessível")
    root = directory.resolve(strict=True)
    wallet_map = _load_wallet_map(wallet_map_path)
    manifests = sorted(root.glob("*.manifest.json"), key=lambda item: item.name)
    reports = [plan_manifest(path, root, wallet_map, i) for i, path in enumerate(manifests, 1)]
    counts: dict[str, int] = {}
    for item in reports:
        status = item["status"]
        counts[status] = counts.get(status, 0) + 1
    return {
        "manifest_count": len(manifests),
        "status_counts": dict(sorted(counts.items())),
        "reports": reports,
        "network_access": False,
        "database_access": False,
        "writes_files": False,
        "checkpoint_changes": False,
        "execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Diretório local com manifestos RAW")
    parser.add_argument("--wallet-map", type=Path, default=None,
                        help="JSON local {signature: monitored_wallet}; valores nunca são exibidos")
    args = parser.parse_args()
    try:
        report = build_plan(args.directory, args.wallet_map)
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "writes_files": False,
                          "database_access": False, "network_access": False}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["manifest_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
