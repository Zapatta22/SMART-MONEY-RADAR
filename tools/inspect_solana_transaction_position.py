#!/usr/bin/env python3
"""Imprime a posição exata de uma assinatura em seu bloco Solana finalized."""
from __future__ import annotations

import argparse
import json
import os

from smart_money_radar.data_sources.solana_transaction_position import get_transaction_index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--slot", required=True, type=int)
    parser.add_argument(
        "--rpc-url",
        default=os.environ.get("SMR_SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
    )
    args = parser.parse_args()
    try:
        index = get_transaction_index(args.rpc_url, args.slot, args.signature)
    except Exception as exc:
        print(json.dumps({
            "status": "POSITION_LOOKUP_INCOMPLETE",
            "signature": args.signature,
            "slot": args.slot,
            "reason": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({
        "status": "POSITION_FOUND",
        "signature": args.signature,
        "slot": args.slot,
        "transaction_index": index,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
