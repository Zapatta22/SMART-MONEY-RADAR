"""Integration coverage for a finalized real-mainnet CPMM CPI in a multi-venue route."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

from smart_money_radar.cli import main

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
        result = self.fixture["result"]
        swaps = decode_raydium_cpmm_swaps(self.fixture)
        self.assertEqual(len(swaps), 1)
        swap = swaps[0]
        self.assertEqual((swap.instruction_index, swap.inner_instruction_index), (2, 14))
        self.assertEqual(swap.stack_height, 2)
        self.assertEqual(swap.cpi_path, (3,))

        transfers = decode_solana_token_transfers(self.fixture)
        self.assertEqual(len(transfers), 10)
        deltas = decode_token_account_balance_deltas(self.fixture, include_unchanged=True)
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

        result = self.fixture["result"]
        wallet = result["transaction"]["message"]["accountKeys"][0]
        signature = result["transaction"]["signatures"][0]
        operation_id = build_swap_operation_id("solana", signature, 2, (3,))

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "pipeline.sqlite3")
            try:
                outcome = process_raydium_cpmm_observation(
                    store,
                    self.fixture,
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

                observation = bundle["observation"]
                market = {
                    "wallet": wallet, "program": bundle["evidence"].program_id,
                    "base_mint": observation.output_mint, "quote_mint": observation.input_mint,
                }
                archived, = store.list_swap_replay_archive(**market)
                self.assertEqual(archived["operation_id"], operation_id)
                self.assertGreater(datetime.fromisoformat(archived["available_at"]),
                                   datetime.fromisoformat(archived["occurred_at"]))
                process_raydium_cpmm_observation(
                    store, self.fixture, wallet_address=wallet, signature=signature,
                    reference_mints=(observation.input_mint,),
                )
                self.assertEqual(store.get_swap_bundle(operation_id)["classification"].side, "BUY")
                self.assertEqual(store.list_swap_replay_archive(**market), [archived])
                path = Path(directory) / "scenario.json"
                path.write_text(json.dumps({
                    "config": {"initial_cash": "1000", "max_entry_cash": "100", "max_exposure": "0.1"},
                    "market": {**market, "min_confidence": "0.6", "signal_ttl_seconds": 30},
                }))
                stdout = StringIO()
                with redirect_stdout(stdout):
                    main(["paper-replay", str(path), "--archive", str(store.database_path)])
                report = json.loads(stdout.getvalue())
                self.assertEqual(report["archive"]["ticks"], 1)
                self.assertEqual(report["immediate"]["fills"], [])
                self.assertIsNone(report["immediate"]["pending_side"])
                before_capture = StringIO()
                with redirect_stdout(before_capture):
                    main([
                        "paper-replay", str(path), "--archive", str(store.database_path),
                        "--as-of", archived["occurred_at"],
                    ])
                early = json.loads(before_capture.getvalue())
                self.assertEqual(early["archive"]["ticks"], 0)
                self.assertNotEqual(early["archive"]["receipts_sha256"],
                                    report["archive"]["receipts_sha256"])

                quotes = Path(directory) / "quotes.json"
                available = datetime.fromisoformat(archived["available_at"])
                entries = []
                for offset in (1, 2):
                    at = (available + timedelta(seconds=offset)).isoformat()
                    entries.append({
                        "quote_id": f"quote-{offset}", "market_at": at, "available_at": at,
                        "bid": 10.1, "ask": 10.2, "bid_size": "3", "ask_size": "3", "volume": 100,
                    })
                quote_market = {key: market[key] for key in ("base_mint", "quote_mint", "program")}
                quotes.write_text(json.dumps({**quote_market, "source": "fixture-source", "quotes": entries}))
                quote_output = StringIO()
                with redirect_stdout(quote_output):
                    main([
                        "paper-replay", str(path), "--archive", str(store.database_path),
                        "--quotes", str(quotes), "--as-of", entries[0]["available_at"],
                    ])
                quote_report = json.loads(quote_output.getvalue())["archive"]
                self.assertEqual(quote_report["quote_archive"]["quotes"], 1)
                self.assertEqual(quote_report["quote_archive"]["source"], "fixture-source")
                self.assertEqual(len(quote_report["quote_archive"]["sha256"]), 64)
                audit = store.get_swap_reconciliation_attempts(wallet, signature)
                self.assertEqual(len(audit), 2)
                self.assertEqual(audit[0]["status"], "MATCHED")
                self.assertIn("reconciliados", audit[0]["reason"])

                self.assertIn("input_token_account_delta_raw:0", bundle["evidence"].evidence)
                self.assertIn("output_token_account_delta_raw:74030", bundle["evidence"].evidence)
                self.assertIn("input_vault_delta_raw:4484029903", bundle["evidence"].evidence)
                self.assertIn("output_vault_delta_raw:-165074030", bundle["evidence"].evidence)
            finally:
                store.close()



if __name__ == "__main__":
    unittest.main()
