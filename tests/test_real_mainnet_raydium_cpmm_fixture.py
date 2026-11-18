"""Integration coverage using a finalized, anonymized Solana mainnet transaction."""

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
from smart_money_radar.domain.swap_bundle_builder import build_swap_domain_bundles


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "fixtures"
    / "mainnet"
    / "anonymized"
    / "raydium-cpmm-transient-output.json"
)
MANIFEST_PATH = FIXTURE_PATH.with_suffix(".json.manifest.json")
WSOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_MINT = "CAzFRqFj3WvsgiaVUfzjMbKvf2Kp5vHALPeGQdh1bonk"


class RealMainnetRaydiumCpmmFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_bytes = FIXTURE_PATH.read_bytes()
        cls.fixture = json.loads(cls.fixture_bytes)
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_projection_manifest_and_hash_are_valid(self) -> None:
        self.assertTrue(self.manifest["anonymized"])
        self.assertEqual(self.manifest["commitment"], "finalized")
        self.assertEqual(self.manifest["slot"], 353586080)
        self.assertEqual(
            hashlib.sha256(self.fixture_bytes).hexdigest(),
            self.manifest["projection_sha256"],
        )
        self.assertEqual(
            self.fixture["result"]["transaction"]["signatures"][0],
            self.manifest["signature"],
        )
        self.assertIsNone(self.fixture["result"]["meta"]["err"])

    def test_real_swap_decodes_but_missing_closed_account_delta_fails_closed(self) -> None:
        result = self.fixture["result"]
        message = result["transaction"]["message"]
        monitored_wallet = message["accountKeys"][0]

        swaps = decode_raydium_cpmm_swaps(self.fixture)
        self.assertEqual(len(swaps), 1)
        swap = swaps[0]
        self.assertEqual(swap.instruction_index, 6)
        self.assertEqual(swap.accounts.input_token_mint, TOKEN_MINT)
        self.assertEqual(swap.accounts.output_token_mint, WSOL_MINT)

        transfers = decode_solana_token_transfers(self.fixture)
        self.assertEqual(len(transfers), 2)
        self.assertEqual(
            [transfer.amount_raw for transfer in transfers],
            [11371846366418, 244498263],
        )
        self.assertTrue(
            all(transfer.instruction_type == "TRANSFER_CHECKED" for transfer in transfers)
        )
        self.assertTrue(all(transfer.instruction_index == 6 for transfer in transfers))

        deltas = decode_token_account_balance_deltas(self.fixture)
        delta_accounts = {delta.token_account for delta in deltas}
        self.assertEqual(len(deltas), 3)
        self.assertIn(swap.accounts.input_token_account, delta_accounts)
        self.assertNotIn(swap.accounts.output_token_account, delta_accounts)

        reconciliations = reconcile_raydium_cpmm_swaps(
            swaps,
            transfers,
            deltas,
            monitored_wallet=monitored_wallet,
        )
        self.assertEqual(len(reconciliations), 1)
        self.assertEqual(reconciliations[0].status, "INCOMPLETE")
        self.assertIn("Falta delta pre/post", reconciliations[0].reason)

        bundles = build_swap_domain_bundles(
            reconciliations,
            chain="solana",
            signature=self.manifest["signature"],
            monitored_wallet=monitored_wallet,
            observed_at=datetime.fromtimestamp(result["blockTime"], tz=timezone.utc),
            parser_version="smr-real-mainnet-fixture-v1",
            reference_mints={WSOL_MINT},
        )
        self.assertEqual(bundles, [])


if __name__ == "__main__":
    unittest.main()
