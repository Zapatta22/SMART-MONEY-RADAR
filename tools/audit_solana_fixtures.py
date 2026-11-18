#!/usr/bin/env python3
"""Audita manifestos de fixtures Solana sem acessar a rede."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smart_money_radar.data_sources.fixture_audit import audit_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Diretório com arquivos *.manifest.json")
    args = parser.parse_args()
    manifests = sorted(args.directory.glob("*.manifest.json"))
    if not manifests:
        print(json.dumps({"valid": False, "error": "nenhum manifesto encontrado"}, indent=2))
        return 2
    failed = 0
    for path in manifests:
        result = audit_fixture(path)
        print(json.dumps({
            "manifest": str(result.manifest_path), "signature": result.signature,
            "slot": result.slot, "sha256": result.sha256,
            "valid": result.valid, "errors": result.errors,
        }, ensure_ascii=False))
        failed += not result.valid
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
