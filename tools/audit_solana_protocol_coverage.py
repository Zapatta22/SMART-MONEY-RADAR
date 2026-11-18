#!/usr/bin/env python3
"""Audita cobertura estrutural de programas Solana em fixtures RAW, sem efeitos colaterais."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smart_money_radar.data_sources.fixture_audit import audit_fixture
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.data_sources.solana_token_transfer_decoder import TOKEN_PROGRAM_IDS
from smart_money_radar.domain.program_registry import PROGRAMS_BY_ID


BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# Escopo real dos decoders presentes nesta branch; não significa suporte integral.
DECODER_SCOPE = {
    RAYDIUM_CPMM_PROGRAM_ID: "Raydium CPMM: swap_base_input/output estrutural",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "SPL Token: Transfer/TransferChecked",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022: Transfer/TransferChecked",
}
assert set(DECODER_SCOPE) == {RAYDIUM_CPMM_PROGRAM_ID, *TOKEN_PROGRAM_IDS}


def _keys(message: dict[str, Any], meta: dict[str, Any]) -> list[str]:
    raw = message.get("accountKeys")
    if not isinstance(raw, list):
        raise ValueError("accountKeys inválido")
    parsed = any(isinstance(item, dict) for item in raw)
    result = []
    for item in raw:
        key = item.get("pubkey") if isinstance(item, dict) else item
        if not isinstance(key, str) or not key:
            raise ValueError("account key inválida")
        result.append(key)
    if not parsed:
        loaded = meta.get("loadedAddresses") or {}
        if not isinstance(loaded, dict):
            raise ValueError("loadedAddresses inválido")
        for field in ("writable", "readonly"):
            values = loaded.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError("loadedAddresses inválido")
            result.extend(values)
    return result


def _program_id(instruction: Any, keys: list[str]) -> str | None:
    if not isinstance(instruction, dict):
        return None
    direct = instruction.get("programId")
    if isinstance(direct, str) and direct:
        return direct
    index = instruction.get("programIdIndex")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(keys):
        return None
    return keys[index]


def _decode_base58(value: Any) -> bytes | None:
    if not isinstance(value, str) or not value:
        return None
    number = 0
    try:
        for char in value:
            number = number * 58 + BASE58_ALPHABET.index(char)
    except ValueError:
        return None
    leading_zeroes = len(value) - len(value.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return (b"\\x00" * leading_zeroes) + body


def _inspect_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("RPC result inválido")
    transaction = result.get("transaction")
    meta = result.get("meta")
    if not isinstance(transaction, dict) or not isinstance(meta, dict):
        raise ValueError("transaction/meta inválido")
    message = transaction.get("message")
    if not isinstance(message, dict):
        raise ValueError("message inválido")
    keys = _keys(message, meta)
    outer = message.get("instructions")
    inner_groups = meta.get("innerInstructions", [])
    if not isinstance(outer, list) or not isinstance(inner_groups, list):
        raise ValueError("instruções inválidas")

    counts: dict[str, int] = {}
    supported: dict[str, int] = {}
    profiles: dict[tuple[Any, ...], int] = {}
    unknown_count = 0
    unresolved_count = 0
    total = 0

    def add(instruction: Any, source: str) -> None:
        nonlocal unknown_count, unresolved_count, total
        total += 1
        program_id = _program_id(instruction, keys)
        if program_id is None:
            unresolved_count += 1
            return
        spec = PROGRAMS_BY_ID.get(program_id)
        if spec is None:
            unknown_count += 1
            return
        counts[spec.name] = counts.get(spec.name, 0) + 1
        if program_id in DECODER_SCOPE:
            supported[spec.name] = supported.get(spec.name, 0) + 1
        if spec.venue or spec.kind == "aggregator":
            decoded = _decode_base58(instruction.get("data"))
            prefix = decoded[:8].hex() if decoded else "unavailable"
            accounts = instruction.get("accounts")
            account_count = len(accounts) if isinstance(accounts, list) else None
            stack_height = instruction.get("stackHeight")
            if isinstance(stack_height, bool) or not isinstance(stack_height, int) or stack_height < 1:
                stack_height = None
            profile = (
                spec.name, source, prefix,
                len(decoded) if decoded is not None else None,
                account_count, stack_height,
            )
            profiles[profile] = profiles.get(profile, 0) + 1

    for instruction in outer:
        add(instruction, "top_level")
    for group in inner_groups:
        if not isinstance(group, dict) or not isinstance(group.get("instructions"), list):
            raise ValueError("inner instruction group inválido")
        for instruction in group["instructions"]:
            add(instruction, "inner")

    return {
        "instruction_count": total,
        "registered_program_counts": dict(sorted(counts.items())),
        "decoder_scope_counts": dict(sorted(supported.items())),
        "venue_instruction_profiles": [
            {
                "program": key[0],
                "location": key[1],
                "data_prefix_hex": key[2],
                "data_length": key[3],
                "account_count": key[4],
                "stack_height": key[5],
                "count": count,
            }
            for key, count in sorted(profiles.items(), key=lambda item: tuple(str(v) for v in item[0]))
        ],
        "unregistered_program_instruction_count": unknown_count,
        "unresolved_program_instruction_count": unresolved_count,
    }


def inspect_manifest(manifest_path: Path, root: Path, index: int) -> dict[str, Any]:
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
        candidate_raw = resolved_root / raw_name
        if candidate_raw.is_symlink() or candidate_raw.resolve(strict=True).parent != resolved_root:
            return {"index": index, "status": "FIXTURE_INVALID"}
        audit = audit_fixture(manifest_path)
        if not audit.valid:
            return {"index": index, "status": "FIXTURE_INVALID"}
        payload = json.loads(audit.raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload inválido")
        metrics = _inspect_payload(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RuntimeError):
        return {"index": index, "status": "STRUCTURE_INVALID"}
    return {"index": index, "status": "AUDITED", **metrics}


def build_report(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("diretório de fixtures inacessível")
    root = directory.resolve(strict=True)
    manifests = sorted(root.glob("*.manifest.json"), key=lambda path: path.name)
    reports = [inspect_manifest(path, root, index) for index, path in enumerate(manifests, 1)]
    return {
        "manifest_count": len(manifests),
        "audited_count": sum(item["status"] == "AUDITED" for item in reports),
        "status_counts": {
            status: sum(item["status"] == status for item in reports)
            for status in sorted({item["status"] for item in reports})
        },
        "reports": reports,
        "registered_programs_are_not_all_decoder_supported": True,
        "network_access": False,
        "database_access": False,
        "writes_files": False,
        "checkpoint_changes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.directory)
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "network_access": False,
                          "database_access": False, "writes_files": False}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["manifest_count"] and report["audited_count"] == report["manifest_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
