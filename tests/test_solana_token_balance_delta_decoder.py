import unittest

from smart_money_radar.data_sources.solana_token_balance_delta_decoder import (
    decode_solana_token_account_balance_deltas,
)


def _entry(index, mint="mint-a", amount="100", decimals=6, owner="owner-a"):
    return {
        "accountIndex": index,
        "mint": mint,
        "owner": owner,
        "uiTokenAmount": {"amount": amount, "decimals": decimals},
    }


def _tx(pre, post, keys=None):
    return {
        "transaction": {
            "message": {
                "accountKeys": keys or ["account-0", "account-1", "account-2"],
                "instructions": [],
            }
        },
        "meta": {
            "err": None,
            "preTokenBalances": pre,
            "postTokenBalances": post,
        },
    }


class SolanaTokenBalanceDeltaDecoderTests(unittest.TestCase):
    def test_decodes_paired_balance_delta_and_preserves_raw_units(self):
        result = decode_solana_token_account_balance_deltas(_tx(
            [_entry(1, amount="1000")],
            [_entry(1, amount="725")],
        ))
        self.assertTrue(result.complete)
        self.assertEqual(len(result.deltas), 1)
        delta = result.deltas[0]
        self.assertEqual(delta.token_account, "account-1")
        self.assertEqual(delta.mint, "mint-a")
        self.assertEqual(delta.pre_amount_raw, 1000)
        self.assertEqual(delta.post_amount_raw, 725)
        self.assertEqual(delta.delta_raw, -275)
        self.assertEqual(delta.decimals, 6)

    def test_rejects_mixed_account_key_formats(self):
        tx = _tx([], [], keys=[
            {"pubkey": "parsed-key", "signer": True},
            "compiled-key",
        ])
        result = decode_solana_token_account_balance_deltas(tx)
        self.assertFalse(result.complete)
        self.assertIn("ACCOUNT_KEYS_INVALID", [issue.code for issue in result.issues])

    def test_resolves_loaded_addresses(self):
        tx = _tx([_entry(3)], [_entry(3, amount="120")],
                 keys=["static-0", "static-1", "static-2"])
        tx["meta"]["loadedAddresses"] = {
            "writable": ["loaded-token-account"],
            "readonly": [],
        }
        result = decode_solana_token_account_balance_deltas(tx)
        self.assertEqual(result.deltas[0].token_account, "loaded-token-account")

    def test_failed_transaction_has_no_deltas(self):
        tx = _tx([_entry(1)], [_entry(1, amount="90")])
        tx["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        result = decode_solana_token_account_balance_deltas(tx)
        self.assertEqual(result.deltas, ())
        self.assertIn("TRANSACTION_FAILED", [x.code for x in result.issues])

    def test_missing_execution_status_is_not_assumed_success(self):
        tx = _tx([_entry(1)], [_entry(1, amount="90")])
        del tx["meta"]["err"]
        result = decode_solana_token_account_balance_deltas(tx)
        self.assertEqual(result.deltas, ())
        self.assertIn("EXECUTION_STATUS_UNKNOWN", [x.code for x in result.issues])

    def test_missing_snapshot_side_is_not_assumed_zero(self):
        result = decode_solana_token_account_balance_deltas(_tx(
            [_entry(1)], []
        ))
        self.assertFalse(result.complete)
        self.assertEqual(result.deltas, ())
        self.assertIn("SNAPSHOT_SIDE_MISSING", [x.code for x in result.issues])

    def test_rejects_duplicate_account_index(self):
        result = decode_solana_token_account_balance_deltas(_tx(
            [_entry(1), _entry(1, amount="101")],
            [_entry(1, amount="120")],
        ))
        self.assertFalse(result.complete)
        self.assertEqual(result.deltas, ())
        self.assertIn("DUPLICATE_ACCOUNT_INDEX", [x.code for x in result.issues])

    def test_rejects_mint_and_decimal_changes(self):
        mint = decode_solana_token_account_balance_deltas(_tx(
            [_entry(1, mint="mint-a")], [_entry(1, mint="mint-b")]
        ))
        decimals = decode_solana_token_account_balance_deltas(_tx(
            [_entry(1, decimals=6)], [_entry(1, decimals=9)]
        ))
        self.assertIn("MINT_MISMATCH", [x.code for x in mint.issues])
        self.assertIn("DECIMALS_MISMATCH", [x.code for x in decimals.issues])

    def test_rejects_owner_change(self):
        result = decode_solana_token_account_balance_deltas(_tx(
            [_entry(1, owner="owner-a")],
            [_entry(1, owner="owner-b")],
        ))
        self.assertIn("OWNER_MISMATCH", [x.code for x in result.issues])
        self.assertEqual(result.deltas, ())

    def test_rejects_unresolved_account_index(self):
        result = decode_solana_token_account_balance_deltas(_tx(
            [_entry(99)], [_entry(99)]
        ))
        self.assertIn("ACCOUNT_INDEX_UNRESOLVED", [x.code for x in result.issues])

    def test_rejects_non_integer_or_negative_raw_amount(self):
        for raw in ("1.5", "-1", True):
            result = decode_solana_token_account_balance_deltas(_tx(
                [_entry(1, amount="1")],
                [_entry(1, amount=raw)],
            ))
            self.assertFalse(result.complete)
            self.assertEqual(result.deltas, ())


if __name__ == "__main__":
    unittest.main()
