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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-file", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=ROOT / "data/fixtures/raw/damm-v2")
    args = parser.parse_args()

    try:
        candidates = json.loads(args.candidate_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Não foi possível ler candidatos: {type(exc).__name__}")
    if not isinstance(candidates, list):
        parser.error("O catálogo de candidatos deve ser uma lista JSON.")

    matches = [
        item for item in candidates
        if isinstance(item, dict) and item.get("protocol") == "Meteora DAMM v2"
    ]
    signatures = {
        item.get("signature") for item in matches
        if isinstance(item.get("signature"), str) and item["signature"]
    }
    if len(signatures) != 1:
        parser.error(
            "Era esperado exatamente um candidato Meteora DAMM v2 no catálogo."
        )

    signature = next(iter(signatures))
    collector = RpcFixtureCollector(
        endpoint_from_environment(),
        args.output,
    )
    result = collector.collect(signature)
    print(
        f"OK protocol=Meteora-DAMM-v2 signature={result.signature} "
        f"slot={result.slot} sha256={result.sha256} raw={result.raw_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
