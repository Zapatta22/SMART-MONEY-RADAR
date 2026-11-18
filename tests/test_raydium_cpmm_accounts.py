import unittest

from smart_money_radar.data_sources.raydium_cpmm_accounts import (
    decode_raydium_cpmm_accounts,
)


class TestRaydiumCpmmAccounts(unittest.TestCase):
    def test_decodes_thirteen_required_accounts(self):
        accounts = [f"Account{i}" for i in range(13)]
        result = decode_raydium_cpmm_accounts(accounts)
        self.assertEqual(result.payer, "Account0")
        self.assertEqual(result.observation_state, "Account12")
        self.assertEqual(result.remaining_accounts, ())

    def test_preserves_remaining_accounts(self):
        accounts = [f"Account{i}" for i in range(16)]
        result = decode_raydium_cpmm_accounts(accounts)
        self.assertEqual(result.pool_state, "Account3")
        self.assertEqual(
            result.remaining_accounts,
            ("Account13", "Account14", "Account15"),
        )

    def test_rejects_fewer_than_thirteen(self):
        with self.assertRaisesRegex(ValueError, "pelo menos 13"):
            decode_raydium_cpmm_accounts(["Account"] * 12)

    def test_rejects_invalid_account_value(self):
        accounts = [f"Account{i}" for i in range(13)]
        accounts.append("")
        with self.assertRaisesRegex(ValueError, "strings não vazias"):
            decode_raydium_cpmm_accounts(accounts)

    def test_rejects_invalid_container(self):
        with self.assertRaises(TypeError):
            decode_raydium_cpmm_accounts("not-a-list")


if __name__ == "__main__":
    unittest.main()
