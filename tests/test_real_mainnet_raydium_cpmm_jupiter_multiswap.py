"""Integration coverage for a finalized Jupiter route with two Raydium CPMM CPIs.

The fixture is pseudonymized, not anonymous. Both swaps are decoded independently, but temporary
intermediate token accounts have no non-zero pre/post delta and therefore must
not produce economic observations.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
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
from smart_money_radar.domain.raydium_cpmm_persistence_pipeline import (
    process_raydium_cpmm_observation,
)
from smart_money_radar.storage.event_store import SQLiteEventStore
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
        self.assertTrue(self.manifest["pseudonymized"])
        self.assertFalse(self.manifest["anonymized"])
        self.assertNotIn("signature", self.manifest)
        self.assertNotIn("raw_sha256", self.manifest)
        self.assertEqual(self.manifest["fixture_id"], "smr-fixture-raydium-cpmm-jupiter-multiswap-v1")
        self.assertEqual(self.fixture["result"]["transaction"]["signatures"][0], "1" * 64)
        self.assertEqual(self.fixture["result"]["transaction"]["message"]["recentBlockhash"], "1" * 32)
        self.assertEqual(self.manifest["commitment"], "finalized")
        self.assertEqual(self.manifest["slot"], 469955314)
        self.assertEqual(self.manifest["projection_file"], FIXTURE_PATH.name)
        self.assertEqual(
            hashlib.sha256(self.fixture_bytes).hexdigest(),
            self.manifest["projection_sha256"],
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
                self.manifest["fixture_id"],
                item.instruction_index,
                item.cpi_path,
            )
            for item in swaps
        }
        self.assertEqual(len(operation_ids), 2)

    def test_matches_first_hop_and_rejects_token2022_net_credit_mismatch(self) -> None:
        result = self.fixture["result"]
        swaps = decode_raydium_cpmm_swaps(self.fixture)
        transfers = decode_solana_token_transfers(self.fixture)
        # Keep zero-net snapshots: intermediate accounts can receive and send
        # tokens within the route while ending with the same pre/post balance.
        deltas = decode_token_account_balance_deltas(
            self.fixture,
            include_unchanged=True,
        )
        delta_by_account = {item.token_account: item for item in deltas}

        self.assertGreaterEqual(len(transfers), 4)
        first_intermediate = delta_by_account[swaps[0].accounts.output_token_account]
        second_intermediate = delta_by_account[swaps[1].accounts.input_token_account]
        self.assertEqual(first_intermediate.delta_raw, 0)
        self.assertEqual(second_intermediate.delta_raw, 0)

        wallet = result["transaction"]["message"]["accountKeys"][0]
        reconciliations = reconcile_raydium_cpmm_swaps(
            swaps,
            transfers,
            deltas,
            monitored_wallet=wallet,
        )
        self.assertEqual(len(reconciliations), 2)
        # First swap is fully reconcilable, including the intermediate account
        # whose incoming and outgoing transfers net to zero. The second swap
        # remains incomplete because Token-2022 gross output differs from the
        # recipient account's net balance increase.
        self.assertEqual(
            [item.status for item in reconciliations],
            ["MATCHED", "INCOMPLETE"],
        )
        self.assertEqual(reconciliations[0].input_amount_raw, 4421780000)
        self.assertEqual(reconciliations[0].output_amount_raw, 1390888)
        self.assertIsNotNone(reconciliations[0].input_token_account_delta_raw)
        self.assertEqual(reconciliations[0].output_token_account_delta_raw, 0)
        self.assertIsNotNone(reconciliations[0].input_vault_delta_raw)
        self.assertIsNotNone(reconciliations[0].output_vault_delta_raw)
        self.assertIn("token account de saída", reconciliations[1].reason)
        self.assertIn("não reconcilia", reconciliations[1].reason)

        bundles = build_swap_domain_bundles(
            reconciliations,
            chain="solana",
            signature=self.manifest["fixture_id"],
            monitored_wallet=wallet,
            observed_at=datetime.fromtimestamp(result["blockTime"], tz=timezone.utc),
            parser_version="smr-real-mainnet-jupiter-multiswap-v1",
        )
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0].observation.input_amount, Decimal("4421.78"))
        self.assertEqual(bundles[0].observation.output_amount, Decimal("1.390888"))
        self.assertEqual(bundles[0].classification.side, "UNKNOWN")
        self.assertTrue(any(item.startswith("input_vault_delta_raw:") for item in bundles[0].evidence.evidence))

        # With an explicitly configured reference mint, the same observed
        # direction is classified relative to that quote asset.
        sell_bundles = build_swap_domain_bundles(
            reconciliations,
            chain="solana",
            signature=self.manifest["fixture_id"],
            monitored_wallet=wallet,
            observed_at=datetime.fromtimestamp(result["blockTime"], tz=timezone.utc),
            parser_version="smr-real-mainnet-jupiter-multiswap-v1",
            reference_mints={swaps[0].accounts.output_token_mint},
        )
        self.assertEqual(len(sell_bundles), 1)
        self.assertEqual(sell_bundles[0].classification.side, "SELL")


    def test_jupiter_multi_swap_persists_matched_hop_and_keeps_failed_hop_pending(self) -> None:
        import tempfile

        result = self.fixture["result"]
        wallet = result["transaction"]["message"]["accountKeys"][0]
        signature = result["transaction"]["signatures"][0]
        swaps = decode_raydium_cpmm_swaps(self.fixture)
        matched_operation_id = build_swap_operation_id(
            "solana", signature, swaps[0].instruction_index, swaps[0].cpi_path
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "jupiter.sqlite3")
            try:
                first = process_raydium_cpmm_observation(
                    store, self.fixture, wallet_address=wallet, signature=signature
                )
                self.assertEqual(first.status, "pending_reconciliation")
                self.assertEqual(first.decoded_swaps, 2)
                self.assertEqual(first.matched_swaps, 1)
                self.assertEqual(first.unresolved_swaps, 1)
                self.assertEqual(first.saved_bundles, 1)
                self.assertFalse(first.checkpoint_advanced)
                self.assertIsNotNone(store.get_swap_bundle(matched_operation_id))
                self.assertFalse(store.has_processed_signature(wallet, signature))
                self.assertEqual(store.get_pending_signatures(wallet), [signature])

                replay = process_raydium_cpmm_observation(
                    store, self.fixture, wallet_address=wallet, signature=signature
                )
                self.assertEqual(replay.status, "pending_reconciliation")
                self.assertEqual(replay.saved_bundles, 0)
                self.assertFalse(replay.checkpoint_advanced)
                self.assertIsNotNone(store.get_swap_bundle(matched_operation_id))
            finally:
                store.close()



if __name__ == "__main__":
    unittest.main()
