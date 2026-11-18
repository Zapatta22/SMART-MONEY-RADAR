#!/usr/bin/env python3
"""Coleta assinaturas conhecidas via RPC HTTPS; uso: python tools/collect_solana_fixtures.py SIG [SIG...]."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from smart_money_radar.data_sources.rpc_fixture_collector import (
    RpcFixtureCollector, endpoint_from_environment,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signatures", nargs="*", help="Assinaturas Solana confirmadas")
    parser.add_argument("--candidate-file", type=Path, help="JSON versionado com candidatos previamente documentados")
    parser.add_argument("--output", default="data/fixtures/raw", help="Diretório para payloads brutos")
    args = parser.parse_args()
    signatures = list(args.signatures)
    if args.candidate_file:
        try:
            candidates = json.loads(args.candidate_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"Não foi possível ler o arquivo de candidatos: {type(exc).__name__}")
        if not isinstance(candidates, list):
            parser.error("O arquivo de candidatos deve conter uma lista JSON.")
        for item in candidates:
            if not isinstance(item, dict) or not isinstance(item.get("signature"), str):
                parser.error("Cada candidato deve ser um objeto com campo signature.")
            signatures.append(item["signature"])
    if not signatures:
        parser.error("Informe assinaturas ou --candidate-file.")
    # Deduplicação estável evita chamadas e gravações repetidas.
    signatures = list(dict.fromkeys(signatures))
    collector = RpcFixtureCollector(endpoint_from_environment(), args.output)
    for signature in signatures:
        result = collector.collect(signature)
        print(f"OK {result.signature} slot={result.slot} sha256={result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
