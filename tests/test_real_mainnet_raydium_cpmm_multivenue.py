"""Integration coverage for a finalized real-mainnet CPMM CPI in a multi-venue route."""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest
from pathlib import Path

from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
from smart_money_radar.data_sources.raydium_cpmm_transfer_reconciliation import reconcile_raydium_cpmm_swaps
from smart_money_radar.data_sources.solana_token_balance_deltas import decode_token_account_balance_deltas
from smart_money_radar.data_sources.solana_token_transfer_decoder import decode_solana_token_transfers
from smart_money_radar.domain.swap_bundle_builder import build_swap_domain_bundles
from smart_money_radar.domain.models import build_swap_operation_id
from smart_money_radar.domain.raydium_cpmm_persistence_pipeline import (
    process_raydium_cpmm_observation,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

FIXTURE_PATH = (Path(__file__).resolve().parents[1] / "data" / "fixtures" / "mainnet" / "anonymized" / "raydium-cpmm-route-multivenue.json")
MANIFEST_PATH = FIXTURE_PATH.with_suffix(".json.manifest.json")


class RealMainnetCpmmMultiVenueFixtureTests(unittest.TestCase):
    @staticmethod
    def _fixture_with_resolved_loaded_addresses(fixture):
        """Normaliza a projeção legada que preserva loadedAddresses mas omite ALT lookups.

        O fixture anonimizado contém os endereços já resolvidos pelo RPC, porém
        não preserva addressTableLookups. Para os testes econômicos, expande a
        ordem canônica static + writable + readonly e remove o campo separado.
        A fixture original e seu hash/manifesto permanecem intactos.
        """
        projected = copy.deepcopy(fixture)
        result = projected.get("result", {})
        transaction = result.get("transaction", {})
        message = transaction.get("message", {})
        meta = result.get("meta", {})
        loaded = meta.get("loadedAddresses") if isinstance(meta, dict) else None
        lookups = message.get("addressTableLookups", [])
        if loaded is not None and not lookups:
            writable = loaded.get("writable") if isinstance(loaded, dict) else None
            readonly = loaded.get("readonly") if isinstance(loaded, dict) else None
            keys = message.get("accountKeys")
            if (
                not isinstance(keys, list)
                or not isinstance(writable, list)
                or not isinstance(readonly, list)
                or any(not isinstance(key, str) or not key for key in writable + readonly)
            ):
                raise ValueError("Projeção ALT incompleta: não é possível resolver accountKeys.")
            message["accountKeys"] = keys + writable + readonly
            meta.pop("loadedAddresses", None)
        return projected

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
        self.assertEqual(self.manifest["fixture_id"], "smr-fixture-raydium-cpmm-multivenue-v1")
        self.assertEqual(self.fixture["result"]["transaction"]["signatures"][0], "1" * 64)
        self.assertEqual(self.fixture["result"]["transaction"]["message"]["recentBlockhash"], "1" * 32)
        self.assertEqual(self.manifest["commitment"], "finalized")
        self.assertEqual(self.manifest["slot"], 388739013)
        self.assertEqual(self.manifest["projection_file"], FIXTURE_PATH.name)
        self.assertEqual(hashlib.sha256(self.fixture_bytes).hexdigest(), self.manifest["projection_sha256"])
        self.assertIsNone(self.fixture["result"]["meta"]["err"])

    def test_reconciles_real_cpmm_cpi_with_zero_net_input_account_and_forwarded_output(self) -> None:
        fixture = self._fixture_with_resolved_loaded_addresses(self.fixture)
        result = fixture["result"]
        swaps = decode_raydium_cpmm_swaps(fixture)
        self.assertEqual(len(swaps), 1)
        swap = swaps[0]
        self.assertEqual((swap.instruction_index, swap.inner_instruction_index), (2, 14))
        self.assertEqual(swap.stack_height, 2)
        self.assertEqual(swap.cpi_path, (3,))

        transfers = decode_solana_token_transfers(fixture)
        self.assertEqual(len(transfers), 10)
        deltas = decode_token_account_balance_deltas(fixture, include_unchanged=True)
        delta_by_account = {item.token_account: item for item in deltas}
        self.assertEqual(delta_by_account[swap.accounts.input_token_account].delta_raw, 0)
        self.assertEqual(delta_by_account[swap.accounts.output_token_account].delta_raw, 74030)
        self.assertEqual(delta_by_account[swap.accounts.input_vault].delta_raw, 4484029903)
        self.assertEqual(delta_by_account[swap.accounts.output_vault].delta_raw, -165074030)

        wallet = result["transaction"]["message"]["accountKeys"][0]
        reconciliations = reconcile_raydium_cpmm_swaps(swaps, transfers, deltas, monitored_wallet=wallet)
        self.assertEqual([item.status for item in reconciliations], ["MATCHED"])
        self.assertEqual(reconciliations[0].input_amount_raw, 4484029903)
        self.assertEqual(reconciliations[0].output_amount_raw, 165074030)
        self.assertEqual(reconciliations[0].input_token_account_delta_raw, 0)
        self.assertEqual(reconciliations[0].output_token_account_delta_raw, 74030)
        self.assertEqual(reconciliations[0].input_vault_delta_raw, 4484029903)
        self.assertEqual(reconciliations[0].output_vault_delta_raw, -165074030)
        self.assertEqual(reconciliations[0].input_decimals, 6)
        self.assertEqual(reconciliations[0].output_decimals, 8)

        common = dict(
            chain="solana", signature=self.manifest["fixture_id"], monitored_wallet=wallet,
            observed_at=datetime.fromtimestamp(result["blockTime"], tz=timezone.utc),
            parser_version="smr-real-mainnet-multivenue-cpmm-v1",
        )
        bundles = build_swap_domain_bundles(reconciliations, **common)
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0].observation.input_amount, Decimal("4484.029903"))
        self.assertEqual(bundles[0].observation.output_amount, Decimal("1.65074030"))
        self.assertEqual(bundles[0].classification.side, "UNKNOWN")
        self.assertIn("input_token_account_delta_raw:0", bundles[0].evidence.evidence)
        self.assertIn("output_token_account_delta_raw:74030", bundles[0].evidence.evidence)

        buy = build_swap_domain_bundles(reconciliations, reference_mints={swap.accounts.input_token_mint}, **common)
        sell = build_swap_domain_bundles(reconciliations, reference_mints={swap.accounts.output_token_mint}, **common)
        self.assertEqual(buy[0].classification.side, "BUY")
        self.assertEqual(sell[0].classification.side, "SELL")


    def test_real_mainnet_fixture_runs_end_to_end_through_sqlite_pipeline(self) -> None:
        import tempfile

        fixture = self._fixture_with_resolved_loaded_addresses(self.fixture)
        result = fixture["result"]
        wallet = result["transaction"]["message"]["accountKeys"][0]
        signature = result["transaction"]["signatures"][0]
        operation_id = build_swap_operation_id("solana", signature, 2, (3,))

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "pipeline.sqlite3")
            try:
                outcome = process_raydium_cpmm_observation(
                    store,
                    fixture,
                    wallet_address=wallet,
                    signature=signature,
                )

                self.assertEqual(outcome.status, "processed")
                self.assertEqual(outcome.decoded_swaps, 1)
                self.assertEqual(outcome.matched_swaps, 1)
                self.assertEqual(outcome.unresolved_swaps, 0)
                self.assertEqual(outcome.saved_bundles, 1)
                self.assertTrue(outcome.checkpoint_advanced)
                self.assertTrue(store.has_processed_signature(wallet, signature))
                self.assertEqual(store.get_checkpoint(wallet), signature)
                self.assertEqual(store.get_raw_transaction(wallet, signature), result)

                bundle = store.get_swap_bundle(operation_id)
                self.assertIsNotNone(bundle)
                self.assertEqual(bundle["observation"].input_amount, Decimal("4484.029903"))
                self.assertEqual(bundle["observation"].output_amount, Decimal("1.65074030"))
                self.assertEqual(bundle["classification"].side, "UNKNOWN")
                audit = store.get_swap_reconciliation_attempts(wallet, signature)
                self.assertEqual(len(audit), 1)
                self.assertEqual(audit[0]["status"], "MATCHED")
                self.assertIn("reconciliados", audit[0]["reason"])

                self.assertIn("input_token_account_delta_raw:0", bundle["evidence"].evidence)
                self.assertIn("output_token_account_delta_raw:74030", bundle["evidence"].evidence)
                self.assertIn("input_vault_delta_raw:4484029903", bundle["evidence"].evidence)
                self.assertIn("output_vault_delta_raw:-165074030", bundle["evidence"].evidence)
            finally:
                store.close()



    def test_real_mainnet_cpmm_fixture_runs_through_shared_wallet_monitor(self) -> None:
        import asyncio

        from smart_money_radar.services.wallet_monitor import WalletMonitor
        from smart_money_radar.settings import HeliusSettings

        fixture = self._fixture_with_resolved_loaded_addresses(self.fixture)
        result = fixture["result"]
        wallet = result["transaction"]["message"]["accountKeys"][0]
        signature = result["transaction"]["signatures"][0]

        class ReplaySource:
            async def get_transaction_async(self, requested_signature: str):
                if requested_signature != signature:
                    raise ValueError("WalletMonitor solicitou assinatura divergente.")
                return fixture

        store = SQLiteEventStore(":memory:")
        try:
            monitor = WalletMonitor(
                HeliusSettings(api_key="fixture-validation"),
                ReplaySource(),
                store,
            )
            completed = asyncio.run(
                monitor._collect_transaction(wallet, signature)
            )

            self.assertTrue(completed)
            self.assertTrue(store.has_processed_signature(wallet, signature))
            self.assertEqual(store.get_checkpoint(wallet), signature)
            attempts = store.get_swap_reconciliation_attempts(wallet, signature)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["status"], "MATCHED")
            operation_id = attempts[0]["operation_id"]
            bundle = store.get_swap_bundle(operation_id)
            self.assertIsNotNone(bundle)
            self.assertEqual(bundle["evidence"].venue, "Raydium CPMM")
            self.assertEqual(bundle["classification"].side, "UNKNOWN")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
