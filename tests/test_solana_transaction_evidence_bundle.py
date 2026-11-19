import hashlib
import json
import unittest

from smart_money_radar.data_sources.damm_v2_decoder import (
    EVENT_CPI_TAG,
    EVT_SWAP2_DISCRIMINATOR,
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP_DISCRIMINATOR,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import TOKEN_2022_PROGRAM_ID

from smart_money_radar.data_sources.solana_transaction_evidence_bundle import (
    build_solana_transaction_evidence_bundle,
)



ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data):
    zeros = len(data) - len(data.lstrip(b"\x00"))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * zeros + (encoded or ("" if zeros else "1"))


def _u64(value):
    return value.to_bytes(8, "little")


def _swap_data():
    return SWAP_DISCRIMINATOR + _u64(100) + _u64(90)


def _event_data():
    body = (
        bytes(32) + bytes((0, 0, 0))
        + _u64(100) + _u64(90) + bytes((0,))
        + _u64(100) + _u64(0) + _u64(0) + _u64(90) + bytes(16)
        + _u64(0) + _u64(0) + _u64(0) + _u64(0)
        + _u64(0) + _u64(0) + _u64(0)
        + _u64(1) + _u64(2) + _u64(3)
    )
    return EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + body


def _damm_transaction(invalid_account_index=False):
    keys = [
        "authority", _b58encode(bytes(32)), "user-a", "user-b",
        "vault-a", "vault-b", "mint-a", "mint-b", "payer",
        TOKEN_2022_PROGRAM_ID, TOKEN_2022_PROGRAM_ID, "referral",
        "event-authority", METEORA_DAMM_V2_PROGRAM_ID,
    ]
    accounts = list(range(14))
    if invalid_account_index:
        accounts[4] = 999
    return {
        "result": {
            "transaction": {
                "signatures": ["1" * 64],
                "message": {
                    "accountKeys": keys,
                    "instructions": [{"programId": "aggregator", "accounts": [], "data": "1"}],
                },
            },
            "meta": {
                "err": None,
                "innerInstructions": [{
                    "index": 0,
                    "instructions": [
                        {"programId": METEORA_DAMM_V2_PROGRAM_ID, "accounts": accounts,
                         "data": _b58encode(_swap_data()), "stackHeight": 2},
                        {"programId": METEORA_DAMM_V2_PROGRAM_ID, "accounts": [0],
                         "data": _b58encode(_event_data()), "stackHeight": 3},
                    ],
                }],
                "preTokenBalances": [],
                "postTokenBalances": [],
            },
            "slot": 123,
        }
    }


def _transaction(signature="1" * 64, slot=123):
    return {
        "transaction": {
            "signatures": [signature],
            "message": {
                "accountKeys": [],
                "instructions": [],
            },
        },
        "meta": {
            "err": None,
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
        "slot": slot,
    }


class SolanaTransactionEvidenceBundleTests(unittest.TestCase):
    def test_builds_complete_bundle_from_one_rpc_payload(self):
        raw = _transaction()
        bundle = build_solana_transaction_evidence_bundle(
            raw, source_id="geyser-provider-a"
        )

        expected_hash = hashlib.sha256(
            json.dumps(
                raw,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

        self.assertEqual(bundle.identity.transaction_signature, "1" * 64)
        self.assertEqual(bundle.identity.slot, 123)
        self.assertEqual(bundle.identity.source_id, "geyser-provider-a")
        self.assertEqual(bundle.identity.payload_sha256, expected_hash)
        self.assertTrue(bundle.instruction_inventory.complete)
        self.assertTrue(bundle.balance_deltas.complete)
        self.assertEqual(bundle.transfers, ())
        self.assertTrue(bundle.structurally_complete)

    def test_accepts_standard_rpc_result_wrapper(self):
        raw = {"jsonrpc": "2.0", "result": _transaction()}
        bundle = build_solana_transaction_evidence_bundle(
            raw, source_id="rpc-a"
        )

        self.assertEqual(bundle.identity.transaction_signature, "1" * 64)
        self.assertEqual(bundle.identity.slot, 123)
        self.assertTrue(bundle.structurally_complete)

    def test_rejects_missing_source_identity(self):
        with self.assertRaisesRegex(ValueError, "source_id"):
            build_solana_transaction_evidence_bundle(
                _transaction(), source_id=" "
            )

    def test_rejects_missing_transaction_signature(self):
        raw = _transaction(signature="")
        with self.assertRaisesRegex(ValueError, "assinatura"):
            build_solana_transaction_evidence_bundle(
                raw, source_id="rpc-a"
            )

    def test_rejects_invalid_slot(self):
        for slot in (None, -1, True, "123"):
            with self.subTest(slot=slot):
                with self.assertRaisesRegex(ValueError, "slot"):
                    build_solana_transaction_evidence_bundle(
                        _transaction(slot=slot), source_id="rpc-a"
                    )

    def test_preserves_incomplete_decoder_evidence_as_ineligible(self):
        raw = _transaction()
        raw["meta"].pop("postTokenBalances")
        bundle = build_solana_transaction_evidence_bundle(
            raw, source_id="rpc-a"
        )

        self.assertFalse(bundle.balance_deltas.complete)
        self.assertFalse(bundle.structurally_complete)


    def test_binds_damm_association_and_context_to_same_payload(self):
        bundle = build_solana_transaction_evidence_bundle(
            _damm_transaction(), source_id="rpc-a"
        )

        self.assertEqual(len(bundle.damm_v2_associations), 1)
        association = bundle.damm_v2_associations[0]
        self.assertEqual(association.status, "MATCHED")
        self.assertEqual(association.resolved_accounts[1], _b58encode(bytes(32)))
        self.assertEqual(len(bundle.damm_v2_contexts), 1)
        self.assertEqual(bundle.damm_v2_contexts[0].accounts.pool, _b58encode(bytes(32)))
        self.assertEqual(len(bundle.damm_v2_transfer_evidence), 1)
        self.assertEqual(bundle.damm_v2_transfer_evidence[0].status, "TRANSFER_MISSING")
        self.assertFalse(bundle.damm_v2_complete)

    def test_invalid_damm_account_reference_fails_closed(self):
        bundle = build_solana_transaction_evidence_bundle(
            _damm_transaction(invalid_account_index=True), source_id="rpc-a"
        )

        self.assertEqual(len(bundle.damm_v2_associations), 1)
        self.assertIsNone(bundle.damm_v2_associations[0].resolved_accounts)
        self.assertEqual(bundle.damm_v2_contexts, ())
        self.assertTrue(bundle.damm_v2_issues)
        self.assertFalse(bundle.damm_v2_complete)

    def test_rejects_non_json_payload_instead_of_hashing_repr(self):
        raw = _transaction()
        raw["non_json"] = object()
        with self.assertRaisesRegex(ValueError, "canonicalizado"):
            build_solana_transaction_evidence_bundle(
                raw, source_id="rpc-a"
            )


if __name__ == "__main__":
    unittest.main()
