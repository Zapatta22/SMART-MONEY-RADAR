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



def find_damm_v2_signature(candidates: object) -> str:
    try:
        signature = find_damm_v2_signature(candidates)
    except ValueError as exc:
        parser.error(str(exc))

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
