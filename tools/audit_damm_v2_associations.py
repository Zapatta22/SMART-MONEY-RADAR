#!/usr/bin/env python3
"""Audita associações DAMM v2 ↔ EvtSwap2 em fixtures RAW, sem efeitos colaterais."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from smart_money_radar.data_sources.damm_v2_analyzer import analyze_damm_v2_swap_events
from smart_money_radar.data_sources.fixture_audit import audit_fixture


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
        raw_path = resolved_root / raw_name
        if raw_path.is_symlink() or raw_path.resolve(strict=True).parent != resolved_root:
            return {"index": index, "status": "FIXTURE_INVALID"}
        audit = audit_fixture(manifest_path)
        if not audit.valid:
            return {"index": index, "status": "FIXTURE_INVALID"}
        payload = json.loads(audit.raw_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"index": index, "status": "STRUCTURE_INVALID"}
        associations = analyze_damm_v2_swap_events(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RuntimeError):
        return {"index": index, "status": "STRUCTURE_INVALID"}

    swap_statuses = Counter(
        item.status for item in associations if item.instruction is not None
    )
    event_statuses = Counter(
        item.status for item in associations if item.event is not None
    )
    return {
        "index": index,
        "status": "AUDITED",
        "swap_operation_count": sum(swap_statuses.values()),
        "swap_status_counts": dict(sorted(swap_statuses.items())),
        "event_count": sum(event_statuses.values()),
        "event_status_counts": dict(sorted(event_statuses.items())),
    }


def build_report(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("diretório de fixtures inacessível")
    root = directory.resolve(strict=True)
    manifests = sorted(root.glob("*.manifest.json"), key=lambda path: path.name)
    reports = [
        inspect_manifest(path, root, index)
        for index, path in enumerate(manifests, 1)
    ]
    statuses = sorted({item["status"] for item in reports})
    return {
        "manifest_count": len(manifests),
        "audited_count": sum(item["status"] == "AUDITED" for item in reports),
        "status_counts": {
            status: sum(item["status"] == status for item in reports)
            for status in statuses
        },
        "reports": reports,
        "network_access": False,
        "database_access": False,
        "writes_files": False,
        "checkpoint_changes": False,
        "execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.directory)
    except ValueError as exc:
        print(json.dumps({
            "error": str(exc),
            "network_access": False,
            "database_access": False,
            "writes_files": False,
            "checkpoint_changes": False,
            "execution_authorized": False,
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["manifest_count"] == 0:
        return 2
    return 0 if report["audited_count"] == report["manifest_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
