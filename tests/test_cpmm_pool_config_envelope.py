import base64
import json
import unittest

from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.domain.cpmm_pool_config_envelope import validate_pool_config_rpc_envelope


class PoolConfigEnvelopeTests(unittest.TestCase):
    def payload(self):
        def account(raw):
            return {"owner": RAYDIUM_CPMM_PROGRAM_ID, "executable": False,
                    "data": [base64.b64encode(raw).decode(), "base64"]}
        return {"result": {"context": {"slot": 42}, "value": [
            account(b"pool-state"), account(b"amm-config")]}}

    def check(self, data=None, **overrides):
        args = dict(expected_slot=42, expected_pool="pool",
                    expected_config="config")
        args.update(overrides)
        return validate_pool_config_rpc_envelope(
            raw_payload=json.dumps(self.payload() if data is None else data).encode(),
            **args)

    def test_accepts_owned_binary_accounts_without_claiming_layout(self):
        result = self.check()
        self.assertEqual(result["slot"], 42)
        self.assertEqual(result["verification"],
                         "PROGRAM_OWNER_AND_RAW_HASH_ONLY_LAYOUT_UNVERIFIED")
        self.assertEqual(len(result["pool_data_sha256"]), 64)

    def test_rejects_wrong_owner_slot_and_missing_config(self):
        with self.assertRaises(ValueError):
            self.check(expected_slot=43)
        data = self.payload()
        data["result"]["value"][0]["owner"] = "another-program"
        with self.assertRaises(ValueError):
            self.check(data)
        data = self.payload()
        data["result"]["value"][1] = None
        with self.assertRaises(ValueError):
            self.check(data)

    def test_rejects_invalid_binary_and_rpc_error(self):
        data = self.payload()
        data["result"]["value"][0]["data"] = ["%", "base64"]
        with self.assertRaises(ValueError):
            self.check(data)
        with self.assertRaises(ValueError):
            self.check({"error": {"code": -32000}})
        with self.assertRaises(ValueError):
            self.check(expected_config="pool")


if __name__ == "__main__":
    unittest.main()
