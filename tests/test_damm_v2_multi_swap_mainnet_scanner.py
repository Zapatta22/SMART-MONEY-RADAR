import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import scan_damm_v2_multi_swap_mainnet as scanner


class DammV2MultiSwapMainnetScannerTests(unittest.TestCase):
    def _candidate_dependencies(self):
        associations = [
            SimpleNamespace(
                status="MATCHED",
                instruction=SimpleNamespace(instruction_name="swap2"),
                event=SimpleNamespace(trade_direction="A_TO_B"),
            ),
            SimpleNamespace(
                status="MATCHED",
                instruction=SimpleNamespace(instruction_name="swap2"),
                event=SimpleNamespace(trade_direction="B_TO_A"),
            ),
        ]
        contexts = [
            SimpleNamespace(
                association=associations[0],
                accounts=SimpleNamespace(
                    input_token_account="input-0",
                    input_mint="MINT-A",
                    output_token_account="output-0",
                    output_mint="MINT-B",
                ),
            ),
            SimpleNamespace(
                association=associations[1],
                accounts=SimpleNamespace(
                    input_token_account="input-1",
                    input_mint="MINT-C",
                    output_token_account="output-1",
                    output_mint="MINT-D",
                ),
            ),
        ]
        result = SimpleNamespace(
            status="RECONCILED",
            reason="lote reconciliado",
            contexts=contexts,
            reconciliation=None,
        )
        return associations, result

    def test_finds_reconciled_multi_swap_without_shared_wsol(self):
        associations, result = self._candidate_dependencies()
        with (
            patch.object(
                scanner, "_fetch_signatures",
                return_value=([{"signature": "signature"}], "https://rpc"),
            ),
            patch.object(scanner, "fetch_transaction", return_value={"slot": 42}),
            patch.object(
                scanner, "analyze_damm_v2_swap_events",
                return_value=associations,
            ),
            patch.object(scanner, "infer_monitored_wallet", return_value="wallet"),
            patch.object(
                scanner, "process_damm_v2_transaction", return_value=result
            ),
        ):
            report = scanner.scan(
                ("https://rpc",), limit=1, pages=1, target="non-shared-wsol"
            )

        self.assertEqual(report["status"], "FOUND_NON_SHARED_WSOL_MULTI_SWAP")
        self.assertEqual(report["inspected"], 1)
        self.assertEqual(report["candidate"]["matched_swap2_count"], 2)
        self.assertEqual(report["candidate"]["pipeline_status"], "RECONCILED")
        self.assertEqual(report["candidate"]["shared_wsol_accounts"], [])
        self.assertEqual(report["candidate"]["reconciled_shared_wsol_accounts"], [])

    def test_mainnet_scan_failure_records_signature_and_continues(self):
        associations, result = self._candidate_dependencies()
        with (
            patch.object(
                scanner, "_fetch_signatures",
                return_value=(
                    [
                        {"signature": "bad-signature", "slot": 10},
                        {"signature": "good-signature", "slot": 20},
                    ],
                    "https://rpc",
                ),
            ),
            patch.object(
                scanner, "fetch_transaction",
                side_effect=[{"slot": 10}, {"slot": 20}],
            ),
            patch.object(
                scanner, "analyze_damm_v2_swap_events",
                side_effect=[ValueError("malformed swap payload"), associations],
            ),
            patch.object(scanner, "infer_monitored_wallet", return_value="wallet"),
            patch.object(
                scanner, "process_damm_v2_transaction", return_value=result
            ),
        ):
            report = scanner.scan(
                ("https://rpc",), limit=2, pages=1, target="non-shared-wsol"
            )

        self.assertEqual(report["status"], "FOUND_NON_SHARED_WSOL_MULTI_SWAP")
        self.assertEqual(report["candidate"]["signature"], "good-signature")
        self.assertEqual(len(report["failure_samples"]), 1)
        self.assertEqual(
            report["failure_samples"][0]["signature"], "bad-signature"
        )
        self.assertEqual(report["failure_samples"][0]["slot"], 10)
        self.assertIn("malformed swap payload", report["failure_samples"][0]["error"])


    def test_shared_wsol_search_keeps_its_existing_default(self):
        associations, result = self._candidate_dependencies()
        with (
            patch.object(
                scanner, "_fetch_signatures",
                return_value=([{"signature": "signature"}], "https://rpc"),
            ),
            patch.object(scanner, "fetch_transaction", return_value={"slot": 42}),
            patch.object(
                scanner, "analyze_damm_v2_swap_events",
                return_value=associations,
            ),
            patch.object(scanner, "infer_monitored_wallet", return_value="wallet"),
            patch.object(
                scanner, "process_damm_v2_transaction", return_value=result
            ),
        ):
            report = scanner.scan(("https://rpc",), limit=1, pages=1)

        self.assertEqual(report["status"], "NO_SHARED_WSOL_MULTI_SWAP_FOUND")
        self.assertEqual(len(report["multi_swap_candidates"]), 1)
        self.assertEqual(
            report["multi_swap_candidates"][0]["pipeline_status"], "RECONCILED"
        )


if __name__ == "__main__":
    unittest.main()
