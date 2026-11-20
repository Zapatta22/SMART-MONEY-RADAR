import json
import unittest
from smart_money_radar.domain.cpmm_vault_account_check import validate_same_slot_vault_accounts

TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


class VaultAccountCheckTests(unittest.TestCase):
    def data(self):
        def account(mint, amount):
            return {"owner": TOKEN, "executable": False,
                    "data": {"parsed": {"type": "account", "info": {
                        "mint": mint, "owner": "authority",
                        "tokenAmount": {"amount": amount, "decimals": 6}}}}}
        return {"result": {"context": {"slot": 123}, "value": [
            account("mint-in", "1000000"), account("mint-out", "2000000")]}}

    def check(self, data=None, **overrides):
        kwargs = dict(expected_slot=123, input_vault="vault-in",
                      output_vault="vault-out", input_mint="mint-in",
                      output_mint="mint-out", expected_authority="authority",
                      input_token_program=TOKEN, output_token_program=TOKEN)
        kwargs.update(overrides)
        return validate_same_slot_vault_accounts(
            raw_payload=json.dumps(data if data is not None else self.data()).encode(),
            **kwargs,
        )

    def test_accepts_parsed_vault_metadata_but_not_pool_state(self):
        result = self.check()
        self.assertEqual(result["input_reserve_raw"], 1000000)
        self.assertEqual(result["slot"], 123)
        self.assertEqual(result["verification"], "VAULT_METADATA_ONLY_POOL_STATE_NOT_VERIFIED")

    def test_rejects_wrong_slot(self):
        with self.assertRaisesRegex(ValueError, "slot RPC"):
            self.check(expected_slot=124)

    def test_rejects_wrong_mint_owner_and_program(self):
        for field, value in (("mint", "other"), ("owner", "other")):
            data = self.data()
            data["result"]["value"][0]["data"]["parsed"]["info"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(data)
        data = self.data()
        data["result"]["value"][1]["owner"] = "other"
        with self.assertRaises(ValueError):
            self.check(data)

    def test_rejects_ambiguous_or_invalid_amounts(self):
        data = self.data()
        data["result"]["value"][0]["data"]["parsed"]["info"]["tokenAmount"]["amount"] = "-5"
        with self.assertRaises(ValueError):
            self.check(data)
        with self.assertRaises(ValueError):
            self.check(input_vault="vault-out")


if __name__ == "__main__":
    unittest.main()
