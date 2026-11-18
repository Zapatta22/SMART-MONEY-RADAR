"""Integration coverage for a finalized Jupiter route with two Raydium CPMM CPIs.

The fixture is anonymized. Both swaps are decoded independently, but temporary
intermediate token accounts have no non-zero pre/post delta and therefore must
not produce economic observations.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from smart_money_radar.data_sources.raydium_cpmm_analyzer import (
    decode_raydium_cpmm_swaps,
)
from smart_money_radar.data_sources.raydium_cpmm_transfer_reconciliation import (
    reconcile_raydium_cpmm_swaps,
)
from smart_money_radar.data_sources.solana_token_balance_deltas import (
    decode_token_account_balance_deltas,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    decode_solana_token_transfers,
)
from smart_money_radar.domain.models import build_swap_operation_id
from smart_money_radar.domain.swap_bundle_builder import build_swap_domain_bundles


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "fixtures"
    / "mainnet"
    / "anonymized"
    / "raydium-cpmm-jupiter-multiswap.json"
)
MANIFEST_PATH = FIXTURE_PATH.with_suffix(".json.manifest.json")


class RealMainnetJupiterMultiSwapFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_bytes = FIXTURE_PATH.read_bytes()
        cls.fixture = json.loads(cls.fixture_bytes)
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_projection_manifest_and_hash_are_valid(self) -> None:
        self.assertTrue(self.manifest["anonymized"])
        self.assertEqual(self.manifest["commitment"], "finalized")
        self.assertEqual(self.manifest["slot"], 469955314)
        self.assertEqual(
            hashlib.sha256(self.fixture_bytes).hexdigest(),
            self.manifest["projection_sha256"],
        )
        self.assertEqual(
            self.fixture["result"]["transaction"]["signatures"][0],
            self.manifest["signature"],
        )
        self.assertIsNone(self.fixture["result"]["meta"]["err"])

    def test_decodes_two_distinct_cpmm_cpi_operations_in_one_jupiter_route(self) -> None:
        swaps = decode_raydium_cpmm_swaps(self.fixture)
        self.assertEqual(len(swaps), 2)
        self.assertEqual([item.instruction_index for item in swaps], [0, 0])
        self.assertEqual([item.inner_instruction_index for item in swaps], [0, 6])
        self.assertNotEqual(swaps[0].cpi_path, swaps[1].cpi_path)

        operation_ids = {
            build_swap_operation_id(
                "solana",
                self.manifest["signature"],
                item.instruction_index,
                item.cpi_path,
            )
            for item in swaps
        }
        self.assertEqual(len(operation_ids), 2)

    def test_intermediate_accounts_without_net_deltas_fail_closed_individually(self) -> None:
        result = self.fixture["result"]
        swaps = decode_raydium_cpmm_swaps(self.fixture)
        transfers = decode_solana_token_transfers(self.fixture)
        deltas = decode_token_account_balance_deltas(self.fixture)
        delta_accounts = {item.token_account for item in deltas}

        self.assertGreaterEqual(len(transfers), 4)
        # First CPMM output and second CPMM input are intermediate accounts
        # whose pre/post token balance is unchanged after the full route.
        self.assertNotIn(swaps[0].accounts.output_token_account, delta_accounts)
        self.assertNotIn(swaps[1].accounts.input_token_account, delta_accounts)

        wallet = result["transaction"]["message"]["accountKeys"][0]
        reconciliations = reconcile_raydium_cpmm_swaps(
            swaps,
            transfers,
            deltas,
            monitored_wallet=wallet,
        )
        self.assertEqual(len(reconciliations), 2)
        self.assertEqual(
            [item.status for item in reconciliations],
            ["INCOMPLETE", "INCOMPLETE"],
        )
        self.assertTrue(
            all("Falta delta pre/post" in item.reason for item in reconciliations)
        )

        bundles = build_swap_domain_bundles(
            reconciliations,
            chain="solana",
            signature=self.manifest["signature"],
            monitored_wallet=wallet,
            observed_at=datetime.fromtimestamp(result["blockTime"], tz=timezone.utc),
            parser_version="smr-real-mainnet-jupiter-multiswap-v1",
        )
        self.assertEqual(bundles, [])


if __name__ == "__main__":
    unittest.main()
