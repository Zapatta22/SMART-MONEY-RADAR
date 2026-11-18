import unittest

from smart_money_radar.domain.damm_v2_persistence_pipeline import (
    process_damm_v2_observation,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

from smart_money_radar.data_sources.damm_v2_decoder import (
    EVENT_CPI_TAG,
    EVT_SWAP2_DISCRIMINATOR,
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP_DISCRIMINATOR,
    SWAP2_DISCRIMINATOR,
)

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data):
    zeros = len(data) - len(data.lstrip(bytes([0])))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * zeros + (encoded or ("" if zeros else "1"))


def _u64(value):
    return value.to_bytes(8, "little")


def _damm_swap_event_raw():
    swap_data = SWAP_DISCRIMINATOR + _u64(100) + _u64(90)
    event_body = (
        bytes(32) + bytes((0, 0, 0))
        + _u64(100) + _u64(90) + bytes((0,))
        + _u64(100) + _u64(0) + _u64(0) + _u64(90) + bytes(16)
        + _u64(0) + _u64(0) + _u64(0) + _u64(0)
        + _u64(0) + _u64(0) + _u64(0)
        + _u64(1) + _u64(2) + _u64(3)
    )
    event_data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + event_body
    def instruction(data, height):
        return {
            "programId": METEORA_DAMM_V2_PROGRAM_ID,
            "accounts": [0],
            "data": _b58encode(data),
            "stackHeight": height,
        }
    raw = _raw()
    raw["transaction"]["message"] = {
        "accountKeys": ["payer"],
        "instructions": [{
            "programId": "aggregator", "accounts": [], "data": _b58encode(b"route")
        }],
    }
    raw["meta"]["innerInstructions"] = [{
        "index": 0,
        "instructions": [instruction(swap_data, 2), instruction(event_data, 3)],
    }]
    return raw


def _raw(meta=None):
    return {
        "slot": 123,
        "blockTime": 1795000000,
        "transaction": {
            "signatures": ["signature"],
            "message": {"accountKeys": [], "instructions": []},
        },
        "meta": meta or {
            "err": None,
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
    }


def _damm_two_swap2_one_invalid_accounts_raw():
    event_body = (
        bytes(32) + bytes((0, 0, 0))
        + _u64(100) + _u64(90) + bytes((0,))
        + _u64(100) + _u64(0) + _u64(0) + _u64(90) + bytes(16)
        + _u64(0) + _u64(0) + _u64(0) + _u64(0)
        + _u64(0) + _u64(0) + _u64(0)
        + _u64(1) + _u64(2) + _u64(3)
    )
    event_data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + event_body
    keys = [
        "authority", "1" * 32, "user-in", "user-out", "vault-a", "vault-b",
        "mint-a", "mint-b", "payer",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        "referral", "event-authority", METEORA_DAMM_V2_PROGRAM_ID,
    ]
    def compiled(data, accounts, height):
        return {
            "programId": METEORA_DAMM_V2_PROGRAM_ID,
            "accounts": accounts,
            "data": _b58encode(data),
            "stackHeight": height,
        }
    raw = _raw()
    raw["transaction"]["message"] = {
        "accountKeys": keys,
        "instructions": [{
            "programId": "aggregator", "accounts": [], "data": _b58encode(b"route")
        }],
    }
    raw["meta"]["innerInstructions"] = [{
        "index": 0,
        "instructions": [
            compiled(SWAP2_DISCRIMINATOR + _u64(100) + _u64(90) + bytes((0,)), list(range(14)), 2),
            compiled(event_data, [0], 3),
            compiled(SWAP2_DISCRIMINATOR + _u64(200) + _u64(180) + bytes((0,)), [0], 2),
            compiled(event_data, [0], 3),
        ],
    }]
    return raw


def _damm_two_swap2_reconciled_raw():
    from smart_money_radar.data_sources.solana_token_transfer_decoder import (
        SPL_TOKEN_PROGRAM_ID,
    )

    keys = ["wallet", "authority", "payer", SPL_TOKEN_PROGRAM_ID,
            METEORA_DAMM_V2_PROGRAM_ID]
    snapshots = []
    inner = []
    for operation in range(2):
        suffix = str(operation)
        pool = "1" * 32
        user_in, user_out = "user-in-" + suffix, "user-out-" + suffix
        vault_a, vault_b = "vault-a-" + suffix, "vault-b-" + suffix
        mint_a, mint_b = "mint-a-" + suffix, "mint-b-" + suffix
        referral, event_authority = "referral-" + suffix, "event-" + suffix
        account_values = [
            "authority", pool, user_in, user_out, vault_a, vault_b,
            mint_a, mint_b, "payer", SPL_TOKEN_PROGRAM_ID,
            SPL_TOKEN_PROGRAM_ID, referral, event_authority,
            METEORA_DAMM_V2_PROGRAM_ID,
        ]
        indexes = []
        for value in account_values:
            if value not in keys:
                keys.append(value)
            indexes.append(keys.index(value))
        def checked_transfer(source, mint, destination, amount):
            return {
                "programId": SPL_TOKEN_PROGRAM_ID,
                "accounts": [keys.index(source), keys.index(mint),
                             keys.index(destination), keys.index("authority")],
                "data": _b58encode(bytes((12,)) + _u64(amount) + bytes((6,))),
                "stackHeight": 3,
            }
        event_body = (
            bytes(32) + bytes((0, 0, 0))
            + _u64(100) + _u64(90) + bytes((0,))
            + _u64(100) + _u64(0) + _u64(0) + _u64(90) + bytes(16)
            + _u64(0) + _u64(0) + _u64(0) + _u64(0)
            + _u64(100) + _u64(90) + _u64(90)
            + _u64(1) + _u64(2) + _u64(3)
        )
        event_data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + event_body
        inner.extend([
            {
                "programId": METEORA_DAMM_V2_PROGRAM_ID,
                "accounts": indexes,
                "data": _b58encode(SWAP2_DISCRIMINATOR + _u64(100) + _u64(90) + bytes((0,))),
                "stackHeight": 2,
            },
            checked_transfer(user_in, mint_a, vault_a, 100),
            checked_transfer(vault_b, mint_b, user_out, 90),
            {
                "programId": METEORA_DAMM_V2_PROGRAM_ID,
                "accounts": [indexes[0]],
                "data": _b58encode(event_data),
                "stackHeight": 3,
            },
        ])
        for account, mint, owner, before, after in (
            (user_in, mint_a, "wallet", 1_000, 900),
            (vault_a, mint_a, "pool-owner", 2_000, 2_100),
            (vault_b, mint_b, "pool-owner", 3_000, 2_910),
            (user_out, mint_b, "wallet", 4_000, 4_090),
        ):
            index = keys.index(account)
            common = {
                "accountIndex": index,
                "mint": mint,
                "owner": owner,
                "uiTokenAmount": {"amount": str(before), "decimals": 6, "uiAmount": before / 1_000_000, "uiAmountString": str(before / 1_000_000)},
            }
            snapshots.append((index, common, {
                **common,
                "uiTokenAmount": {"amount": str(after), "decimals": 6, "uiAmount": after / 1_000_000, "uiAmountString": str(after / 1_000_000)},
            }))
    raw = _raw()
    raw["transaction"]["message"] = {
        "accountKeys": keys,
        "instructions": [{
            "programId": "aggregator", "accounts": [], "data": _b58encode(b"route")
        }],
    }
    raw["meta"]["innerInstructions"] = [{"index": 0, "instructions": inner}]
    raw["meta"]["preTokenBalances"] = [item[1] for item in snapshots]
    raw["meta"]["postTokenBalances"] = [item[2] for item in snapshots]
    return raw


class DammV2PersistencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteEventStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_no_damm_v2_swap_archives_observation_without_checkpoint(self):
        result = process_damm_v2_observation(
            self.store, _raw(), wallet_address="wallet", signature="signature"
        )
        self.assertEqual(result.status, "no_damm_v2_swaps")
        self.assertTrue(result.ready_for_next_venue)
        self.assertIsNotNone(
            self.store.get_raw_transaction("wallet", "signature")
        )
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))

    def test_missing_inner_instruction_metadata_stays_pending_for_replay(self):
        raw = _raw()
        del raw["meta"]["innerInstructions"]
        result = process_damm_v2_observation(
            self.store, raw, wallet_address="wallet", signature="signature"
        )
        self.assertEqual(result.status, "pending_reconciliation")
        self.assertFalse(result.ready_for_next_venue)
        self.assertEqual(result.unresolved_swaps, 1)
        self.assertIsNotNone(
            self.store.get_raw_transaction("wallet", "signature")
        )
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )

    def test_failed_on_chain_is_delegated_to_checkpoint_coordinator(self):
        result = process_damm_v2_observation(
            self.store,
            _raw({"err": {"InstructionError": [0, "Custom"]}}),
            wallet_address="wallet",
            signature="signature",
        )
        self.assertEqual(result.status, "failed_on_chain")
        self.assertTrue(result.ready_for_next_venue)
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )

    def test_signature_mismatch_is_rejected_before_persistence(self):
        with self.assertRaises(ValueError):
            process_damm_v2_observation(
                self.store, _raw(), wallet_address="wallet",
                signature="different-signature",
            )
        self.assertIsNone(
            self.store.get_raw_transaction("wallet", "different-signature")
        )

    def test_matched_event_with_invalid_account_inventory_is_audited_and_blocks_checkpoint(self):
        result = process_damm_v2_observation(
            self.store,
            _damm_swap_event_raw(),
            wallet_address="wallet",
            signature="signature",
        )
        self.assertEqual(result.status, "pending_reconciliation")
        self.assertFalse(result.ready_for_next_venue)
        self.assertEqual(result.decoded_swaps, 1)
        self.assertEqual(result.unresolved_swaps, 1)
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertEqual(
            self.store.get_pending_signatures("wallet"),
            ["signature"],
        )
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status"], "INCOMPLETE")
        self.assertIn("14 contas", attempts[0]["reason"])

    def test_normalization_error_archives_raw_without_checkpoint(self):
        from unittest.mock import patch
        with patch(
            "smart_money_radar.domain.damm_v2_persistence_pipeline.normalize_transaction",
            side_effect=ValueError("invalid normalized payload"),
        ):
            with self.assertRaisesRegex(ValueError, "invalid normalized payload"):
                process_damm_v2_observation(
                    self.store, _raw(), wallet_address="wallet",
                    signature="signature",
                )
        self.assertIsNotNone(
            self.store.get_raw_transaction("wallet", "signature")
        )
        self.assertEqual(
            self.store.get_observation_metadata("wallet", "signature")["parse_status"],
            "parse_error",
        )
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )


    def test_partial_multi_bundle_write_retries_idempotently_after_second_bundle_failure(self):
        from datetime import datetime, timezone
        from decimal import Decimal
        from types import SimpleNamespace
        from unittest.mock import patch

        from smart_money_radar.domain.models import (
            SwapClassification, SwapEvidence, SwapObservation,
            build_swap_operation_id,
        )

        observed_at = datetime(2026, 11, 18, tzinfo=timezone.utc)
        bundles = []
        associations = []
        for instruction_index, cpi_path in ((2, (0,)), (3, (1,))):
            operation_id = build_swap_operation_id(
                "solana", "signature", instruction_index, cpi_path
            )
            observation = SwapObservation(
                operation_id=operation_id,
                chain="solana",
                wallet_address="wallet",
                signature="signature",
                input_mint="input-mint",
                output_mint="output-mint",
                input_amount=Decimal("1.25"),
                output_amount=Decimal("2.50"),
                observed_at=observed_at,
                parser_version="pipeline-retry-test",
            )
            classification = SwapClassification(
                operation_id=operation_id,
                side="UNKNOWN",
                confidence=Decimal("0"),
                reason="Direction is intentionally unclassified.",
            )
            evidence = SwapEvidence(
                operation_id=operation_id,
                program_id="damm-v2-program",
                venue="Meteora DAMM v2",
                instruction_index=instruction_index,
                cpi_path=cpi_path,
                evidence=("synthetic reconciled pipeline contract",),
            )
            bundles.append(SimpleNamespace(
                observation=observation,
                classification=classification,
                evidence=evidence,
            ))
            associations.append(SimpleNamespace(
                instruction=object(),
                instruction_index=instruction_index,
                cpi_path=cpi_path,
                inner_instruction_index=0,
                status="MATCHED",
            ))

        reconciled = SimpleNamespace(
            status="RECONCILED",
            reason="Both operations reconciled.",
            associations=associations,
            bundles=bundles,
        )
        original_save = self.store.save_swap_bundle
        calls = 0

        def fail_on_second_bundle_once(observation, classification, evidence):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("forced second bundle write failure")
            return original_save(observation, classification, evidence)

        with patch(
            "smart_money_radar.domain.damm_v2_persistence_pipeline.process_damm_v2_transaction",
            return_value=reconciled,
        ), patch.object(
            self.store,
            "save_swap_bundle",
            side_effect=fail_on_second_bundle_once,
        ):
            with self.assertRaisesRegex(RuntimeError, "second bundle write failure"):
                process_damm_v2_observation(
                    self.store, _raw(), wallet_address="wallet",
                    signature="signature", observed_at=observed_at,
                )

        first_id, second_id = [
            bundle.observation.operation_id for bundle in bundles
        ]
        self.assertIsNotNone(self.store.get_swap_bundle(first_id))
        self.assertIsNone(self.store.get_swap_bundle(second_id))
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )

        with patch(
            "smart_money_radar.domain.damm_v2_persistence_pipeline.process_damm_v2_transaction",
            return_value=reconciled,
        ):
            retry = process_damm_v2_observation(
                self.store, _raw(), wallet_address="wallet",
                signature="signature", observed_at=observed_at,
            )

        self.assertEqual(retry.status, "reconciled")
        self.assertTrue(retry.ready_for_next_venue)
        self.assertEqual(retry.decoded_swaps, 2)
        self.assertEqual(retry.reconciled_swaps, 2)
        self.assertEqual(retry.saved_bundles, 1)
        self.assertIsNotNone(self.store.get_swap_bundle(first_id))
        self.assertIsNotNone(self.store.get_swap_bundle(second_id))
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 4)
        self.assertTrue(all(item["status"] == "MATCHED" for item in attempts))


    def test_two_real_swap2_associations_block_entire_batch_when_second_account_decode_fails(self):
        raw = _damm_two_swap2_one_invalid_accounts_raw()
        result = process_damm_v2_observation(
            self.store, raw, wallet_address="wallet", signature="signature"
        )

        self.assertEqual(result.status, "pending_reconciliation")
        self.assertEqual(result.decoded_swaps, 2)
        self.assertEqual(result.reconciled_swaps, 0)
        self.assertEqual(result.unresolved_swaps, 2)
        self.assertFalse(result.ready_for_next_venue)
        self.assertFalse(
            self.store.has_processed_signature("wallet", "signature")
        )
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 2)
        self.assertEqual([item["status"] for item in attempts], ["INCOMPLETE", "INCOMPLETE"])
        self.assertTrue(all("14 contas" in item["reason"] for item in attempts))
        from smart_money_radar.domain.models import build_swap_operation_id
        for instruction_index, cpi_path in ((0, (0,)), (0, (2,))):
            operation_id = build_swap_operation_id(
                "solana", "signature", instruction_index, cpi_path
            )
            self.assertIsNone(self.store.get_swap_bundle(operation_id))


    def test_wallet_monitor_blocks_cpmm_on_real_two_swap_economic_mismatch(self):
        import asyncio
        from unittest.mock import patch
        from smart_money_radar.services.wallet_monitor import WalletMonitor
        from smart_money_radar.settings import HeliusSettings

        raw = _damm_two_swap2_reconciled_raw()
        second_user_output_index = raw["transaction"]["message"]["accountKeys"].index(
            "user-out-1"
        )
        second_output_snapshot = next(
            item for item in raw["meta"]["postTokenBalances"]
            if item["accountIndex"] == second_user_output_index
        )
        second_output_snapshot["uiTokenAmount"]["amount"] = "4089"
        second_output_snapshot["uiTokenAmount"]["uiAmount"] = 0.004089
        second_output_snapshot["uiTokenAmount"]["uiAmountString"] = "0.004089"

        class Source:
            async def get_transaction_async(self, signature):
                self.signature = signature
                return raw

        monitor = WalletMonitor(
            HeliusSettings(api_key="simulated-key"), Source(), self.store
        )
        with patch(
            "smart_money_radar.services.wallet_monitor.process_raydium_cpmm_observation"
        ) as cpmm:
            result = asyncio.run(
                monitor._collect_transaction("wallet", "signature")
            )

        self.assertFalse(result)
        cpmm.assert_not_called()
        self.assertFalse(self.store.has_processed_signature("wallet", "signature"))
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        self.assertEqual(
            self.store.get_pending_signatures("wallet"), ["signature"]
        )
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(item["status"] == "INCOMPLETE" for item in attempts))


    def test_two_swap2_economic_mismatch_blocks_both_bundles_and_next_venue(self):
        raw = _damm_two_swap2_reconciled_raw()
        second_user_output_index = raw["transaction"]["message"]["accountKeys"].index(
            "user-out-1"
        )
        second_output_snapshot = next(
            item for item in raw["meta"]["postTokenBalances"]
            if item["accountIndex"] == second_user_output_index
        )
        second_output_snapshot["uiTokenAmount"]["amount"] = "4089"
        second_output_snapshot["uiTokenAmount"]["uiAmount"] = 0.004089
        second_output_snapshot["uiTokenAmount"]["uiAmountString"] = "0.004089"

        result = process_damm_v2_observation(
            self.store, raw, wallet_address="wallet", signature="signature"
        )

        self.assertEqual(result.status, "pending_reconciliation")
        self.assertEqual(result.decoded_swaps, 2)
        self.assertEqual(result.reconciled_swaps, 0)
        self.assertEqual(result.unresolved_swaps, 2)
        self.assertEqual(result.saved_bundles, 0)
        self.assertFalse(result.ready_for_next_venue)
        self.assertFalse(self.store.has_processed_signature("wallet", "signature"))
        self.assertIsNone(self.store.get_checkpoint("wallet"))
        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(item["status"] == "INCOMPLETE" for item in attempts))
        self.assertTrue(all("delta" in item["reason"] for item in attempts))
        for item in attempts:
            self.assertIsNone(self.store.get_swap_bundle(item["operation_id"]))


    def test_two_swap2_payload_runs_full_pipeline_and_persists_both_bundles(self):
        from datetime import datetime, timezone

        observed_at = datetime(2026, 11, 18, tzinfo=timezone.utc)
        raw = _damm_two_swap2_reconciled_raw()
        result = process_damm_v2_observation(
            self.store, raw, wallet_address="wallet",
            signature="signature", observed_at=observed_at,
        )

        self.assertEqual(
            result.status, "reconciled",
            str(self.store.get_swap_reconciliation_attempts("wallet", "signature")),
        )
        self.assertEqual(result.decoded_swaps, 2)
        self.assertEqual(result.reconciled_swaps, 2)
        self.assertEqual(result.unresolved_swaps, 0)
        self.assertEqual(result.saved_bundles, 2)
        self.assertTrue(result.ready_for_next_venue)

        attempts = self.store.get_swap_reconciliation_attempts(
            "wallet", "signature"
        )
        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(item["status"] == "MATCHED" for item in attempts))
        operation_ids = [
            item["operation_id"] for item in attempts
        ]
        self.assertEqual(len(set(operation_ids)), 2)
        persisted = [self.store.get_swap_bundle(item) for item in operation_ids]
        self.assertTrue(all(item is not None for item in persisted))
        self.assertTrue(all(item["classification"].side == "UNKNOWN" for item in persisted))
        self.assertEqual(
            [item["evidence"].instruction_index for item in persisted], [0, 0]
        )


if __name__ == "__main__":
    unittest.main()
