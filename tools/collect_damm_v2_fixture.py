#!/usr/bin/env python3
"""Coleta somente o candidato mainnet Meteora DAMM v2 para fixture RAW local."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smart_money_radar.data_sources.rpc_fixture_collector import (
    RpcFixtureCollector,
    endpoint_from_environment,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "data/fixtures/candidates/solana_mainnet_candidates.json"
DEFAULT_OUTPUT = ROOT / "data/fixtures/raw/damm-v2"


def find_damm_v2_signature(candidates: object) -> str:
    """Retorna a única assinatura DAMM v2 do catálogo, sem escolher ambiguamente."""
    if not isinstance(candidates, list):
        raise ValueError("O catálogo de candidatos deve ser uma lista.")

    matches = [
        item.get("signature")
        for item in candidates
        if isinstance(item, dict)
        and item.get("protocol") == "Meteora DAMM v2"
        and isinstance(item.get("signature"), str)
        and item["signature"].strip()
    ]
    if len(matches) != 1:
        raise ValueError(
            "O catálogo deve conter exatamente um candidato Meteora DAMM v2 "
            "com assinatura não vazia."
        )
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Coleta somente a fixture RAW do candidato Meteora DAMM v2."
    )
    parser.add_argument(
        "--candidate-file",
        type=Path,
        default=DEFAULT_CANDIDATES,
        help="Catálogo JSON de assinaturas candidatas.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Diretório local para RAW e manifesto.",
    )
    args = parser.parse_args()

    try:
        candidates = json.loads(args.candidate_file.read_text(encoding="utf-8"))
        signature = find_damm_v2_signature(candidates)
        collector = RpcFixtureCollector(
            endpoint_from_environment(),
            args.output,
        )
        result = collector.collect(signature)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(
        f"OK protocol=Meteora-DAMM-v2 signature={result.signature} "
        f"slot={result.slot} sha256={result.sha256} raw={result.raw_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
