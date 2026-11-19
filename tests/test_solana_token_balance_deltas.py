import unittest

from smart_money_radar.data_sources.solana_token_balance_deltas import (
    decode_token_account_balance_deltas,
)


def _balance(index, mint="mint-a", amount="0", decimals=6, owner="wallet-a"):
    return {
        "accountIndex": index,
        "mint": mint,
        "owner": owner,
        "uiTokenAmount": {"amount": amount, "decimals": decimals},
    }


def _tx(pre, post, keys=None, meta_extra=None):
    meta = {"err": None, "preTokenBalances": pre, "postTokenBalances": post}
    if meta_extra:
        meta.update(meta_extra)
    return {
        "transaction": {
            "message": {
                "accountKeys": keys or ["token-account-0", "token-account-1", "wallet-a"],
                "instructions": [],
            }
        },
        "meta": meta,
    }


class TokenAccountBalanceDeltaTests(unittest.TestCase):
    def test_calculates_exact_raw_delta_for_account(self):
        result = decode_token_account_balance_deltas(_tx(
            [_balance(0, amount="1000000")],
            [_balance(0, amount="1750000")],
        ))
        self.assertEqual(len(result), 1)
        delta = result[0]
        self.assertEqual(delta.account_index, 0)
        self.assertEqual(delta.token_account, "token-account-0")
        self.assertEqual(delta.mint, "mint-a")
        self.assertEqual(delta.owner, "wallet-a")
        self.assertEqual(delta.pre_amount_raw, 1000000)
        self.assertEqual(delta.post_amount_raw, 1750000)
        self.assertEqual(delta.delta_raw, 750000)
        self.assertEqual(delta.decimals, 6)

    def test_keeps_two_accounts_of_same_mint_separate(self):
        result = decode_token_account_balance_deltas(_tx(
            [_balance(0, amount="100"), _balance(1, amount="900")],
            [_balance(0, amount="150"), _balance(1, amount="850")],
        ))
        self.assertEqual([item.delta_raw for item in result], [50, -50])
        self.assertEqual([item.token_account for item in result], [
            "token-account-0", "token-account-1"
        ])

    def test_treats_missing_pre_side_as_zero_for_created_account(self):
        result = decode_token_account_balance_deltas(_tx(
            [],
            [_balance(1, amount="500")],
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pre_amount_raw, 0)
        self.assertEqual(result[0].post_amount_raw, 500)
        self.assertEqual(result[0].delta_raw, 500)

    def test_treats_missing_post_side_as_zero_for_closed_account(self):
        result = decode_token_account_balance_deltas(_tx(
            [_balance(1, amount="500")],
            [],
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pre_amount_raw, 500)
        self.assertEqual(result[0].post_amount_raw, 0)
        self.assertEqual(result[0].delta_raw, -500)

    def test_ignores_unchanged_account(self):
        self.assertEqual(decode_token_account_balance_deltas(_tx(
            [_balance(0, amount="100")],
            [_balance(0, amount="100")],
        )), [])

    def test_resolves_loaded_address_table_keys(self):
        result = decode_token_account_balance_deltas(_tx(
            [_balance(3, amount="10")],
            [_balance(3, amount="20")],
            keys=["static-0", "static-1", "static-2"],
            meta_extra={"loadedAddresses": {
                "writable": ["loaded-token-account"],
                "readonly": [],
            }},
        ))
        self.assertEqual(result[0].token_account, "loaded-token-account")

    def test_rejects_missing_pre_or_post_array(self):
        raw = _tx([], [])
        del raw["meta"]["preTokenBalances"]
        with self.assertRaisesRegex(ValueError, "preTokenBalances"):
            decode_token_account_balance_deltas(raw)

    def test_rejects_duplicate_account_index(self):
        with self.assertRaisesRegex(ValueError, "duplicado"):
            decode_token_account_balance_deltas(_tx(
                [_balance(0, amount="1"), _balance(0, amount="2")],
                [],
            ))

    def test_rejects_mint_or_decimals_change_for_same_account(self):
        with self.assertRaisesRegex(ValueError, "mint/decimals divergentes"):
            decode_token_account_balance_deltas(_tx(
                [_balance(0, mint="mint-a", amount="1")],
                [_balance(0, mint="mint-b", amount="2")],
            ))

    def test_rejects_owner_change_for_same_account(self):
        with self.assertRaisesRegex(ValueError, "owner divergente"):
            decode_token_account_balance_deltas(_tx(
                [_balance(0, amount="1", owner="wallet-a")],
                [_balance(0, amount="2", owner="wallet-b")],
            ))

    def test_rejects_non_integer_raw_amount(self):
        with self.assertRaisesRegex(ValueError, "amount bruto inválido"):
            decode_token_account_balance_deltas(_tx(
                [_balance(0, amount="1.5")],
                [],
            ))

    def test_failed_transaction_has_no_executed_balance_deltas(self):
        raw = _tx([_balance(0, amount="1")], [_balance(0, amount="2")])
        raw["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        self.assertEqual(decode_token_account_balance_deltas(raw), [])


if __name__ == "__main__":
    unittest.main()
