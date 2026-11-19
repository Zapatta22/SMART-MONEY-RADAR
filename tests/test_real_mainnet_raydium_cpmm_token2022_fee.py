"""Real mainnet Token-2022 CPMM edge case: vault net differs from transfer gross."""

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
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    decode_solana_token_transfers,
)
from smart_money_radar.domain.swap_bundle_builder import build_swap_domain_bundles


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "fixtures"
    / "mainnet"
    / "anonymized"
    / "raydium-cpmm-token2022-fee.json"
)
MANIFEST_PATH = FIXTURE_PATH.with_suffix(".json.manifest.json")
WSOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_MINT = "DnDi8VpeeydQPtf73Xh25Ht6i9qMGdN27RcB33ACz1b1"


class RealMainnetToken2022FeeFixtureTests(unittest.TestCase):
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
        self.assertEqual(self.manifest["fixture_id"], "smr-fixture-raydium-cpmm-token2022-fee-v1")
        self.assertEqual(self.fixture["result"]["transaction"]["signatures"][0], "1" * 64)
        self.assertEqual(self.fixture["result"]["transaction"]["message"]["recentBlockhash"], "1" * 32)
        self.assertEqual(self.manifest["commitment"], "finalized")
        self.assertEqual(self.manifest["slot"], 344357800)
        self.assertEqual(
            hashlib.sha256(self.fixture_bytes).hexdigest(),
            self.manifest["projection_sha256"],
        )
        self.assertEqual(
            self.fixture["result"]["transaction"]["signatures"][0],
            "1" * 64,
        )
        self.assertIsNone(self.fixture["result"]["meta"]["err"])

    def test_token2022_transfer_and_pool_vault_mismatch_fails_closed(self) -> None:
        result = self.fixture["result"]
        message = result["transaction"]["message"]
        monitored_wallet = message["accountKeys"][0]

        swaps = decode_raydium_cpmm_swaps(self.fixture)
        self.assertEqual(len(swaps), 1)
        swap = swaps[0]
        self.assertEqual(swap.instruction_index, 2)
        self.assertEqual(swap.accounts.input_token_mint, TOKEN_MINT)
        self.assertEqual(swap.accounts.output_token_mint, WSOL_MINT)
        self.assertEqual(swap.accounts.input_token_program, TOKEN_2022_PROGRAM_ID)
        self.assertEqual(swap.accounts.output_token_program, SPL_TOKEN_PROGRAM_ID)

        transfers = decode_solana_token_transfers(self.fixture)
        self.assertEqual(len(transfers), 2)
        self.assertEqual(
            [transfer.amount_raw for transfer in transfers],
            [734738353, 1542848],
        )
        self.assertEqual(
            [transfer.program_id for transfer in transfers],
            [TOKEN_2022_PROGRAM_ID, SPL_TOKEN_PROGRAM_ID],
        )

        deltas = decode_token_account_balance_deltas(self.fixture)
        delta_by_account = {delta.token_account: delta for delta in deltas}
        self.assertEqual(len(deltas), 4)
        self.assertEqual(delta_by_account[swap.accounts.input_token_account].delta_raw, -734738353)
        self.assertEqual(delta_by_account[swap.accounts.output_token_account].delta_raw, 1542848)
        self.assertEqual(delta_by_account[swap.accounts.input_vault].delta_raw, 661264517)
        self.assertEqual(delta_by_account[swap.accounts.output_vault].delta_raw, -1542848)

        # The source wallet debit equals the gross transfer, but the input
        # vault's observed net increase does not. No fee amount is inferred.
        self.assertEqual(
            -delta_by_account[swap.accounts.input_token_account].delta_raw,
            transfers[0].amount_raw,
        )
        self.assertNotEqual(
            delta_by_account[swap.accounts.input_vault].delta_raw,
            transfers[0].amount_raw,
        )

        reconciliations = reconcile_raydium_cpmm_swaps(
            swaps,
            transfers,
            deltas,
            monitored_wallet=monitored_wallet,
        )
        self.assertEqual(len(reconciliations), 1)
        self.assertEqual(reconciliations[0].status, "INCOMPLETE")
        self.assertIn("vault de entrada", reconciliations[0].reason)
        self.assertIn("não reconcilia", reconciliations[0].reason)

        bundles = build_swap_domain_bundles(
            reconciliations,
            chain="solana",
            signature=self.manifest["fixture_id"],
            monitored_wallet=monitored_wallet,
            observed_at=datetime.fromtimestamp(result["blockTime"], tz=timezone.utc),
            parser_version="smr-token2022-mainnet-fixture-v1",
            reference_mints={WSOL_MINT},
        )
        self.assertEqual(bundles, [])


if __name__ == "__main__":
    unittest.main()
