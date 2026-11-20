import base64
import json
import unittest
from pathlib import Path

from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.domain.cpmm_pool_config_envelope import (
    CPMM_VAULT_AUTHORITY,
    validate_finalized_cpmm_snapshot,
    validate_pool_config_rpc_envelope,
)


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


class FinalizedCpmmSnapshotTests(unittest.TestCase):
    fixture = Path(__file__).resolve().parents[1] / "data/fixtures/mainnet/raydium-cpmm-state"
    pool = "47hq28mcL7q5GhBg7epyGF2dnuJd4MKFt8QhT7CzYUp4"
    slot = 471539976
    block_time = 1795135275

    def check(self, *, request=None, response=None, **overrides):
        args = dict(expected_slot=self.slot, expected_pool=self.pool, block_time=self.block_time)
        args.update(overrides)
        return validate_finalized_cpmm_snapshot(
            raw_request=self.fixture.joinpath("request.json").read_bytes()
            if request is None else json.dumps(request).encode(),
            raw_response=self.fixture.joinpath("response.json").read_bytes()
            if response is None else json.dumps(response).encode(),
            **args,
        )

    def test_mainnet_snapshot_binds_actual_vault_authority_and_effective_reserves(self):
        verified = self.check()
        keys = json.loads(self.fixture.joinpath("raydium-pool-keys.json").read_bytes())["data"][0]
        self.assertEqual(keys["authority"], CPMM_VAULT_AUTHORITY)
        self.assertEqual(verified.pool.auth_bump, 253)
        self.assertEqual(verified.pool_address, self.pool)
        self.assertEqual(verified.slot, self.slot)
        self.assertEqual((verified.reserve_0_raw, verified.reserve_1_raw), (2289766103, 166893788))
        self.assertEqual(verified.configuration.trade_fee_rate, 3000)
        self.assertEqual(verified.response_sha256, "7b449069fce62d5ccf96cf3cb96644e205ba19e6d71af67ad4b34648eedd71f4")

    def test_rejects_rpc_context_id_order_and_unfinalized_partial_reads(self):
        request_path = self.fixture / "request.json"
        response_path = self.fixture / "response.json"
        with self.assertRaisesRegex(ValueError, "slot"):
            self.check(expected_slot=self.slot + 1)
        response = json.loads(response_path.read_bytes())
        response["id"] = "3"
        with self.assertRaisesRegex(ValueError, "identificador"):
            self.check(response=response)
        request = json.loads(request_path.read_bytes())
        request["params"][1]["commitment"] = "confirmed"
        with self.assertRaisesRegex(ValueError, "finalizado"):
            self.check(request=request)
        request = json.loads(request_path.read_bytes())
        request["params"][1]["dataSlice"] = {"offset": 0, "length": 10}
        with self.assertRaisesRegex(ValueError, "integral"):
            self.check(request=request)
        request = json.loads(request_path.read_bytes())
        request["params"][0][2:] = reversed(request["params"][0][2:])
        with self.assertRaisesRegex(ValueError, "ordem"):
            self.check(request=request)
        response = json.loads(response_path.read_bytes())
        response["result"]["value"][2:] = reversed(response["result"]["value"][2:])
        with self.assertRaisesRegex(ValueError, "mint ou autoridade"):
            self.check(response=response)

    def test_rejects_changed_vault_authority_and_unavailable_reserves(self):
        for offset, value, message in (
            (32, bytes(32), "autoridade"),
            (64, bytes(8), "reserva efetiva disponível"),
        ):
            with self.subTest(offset=offset):
                response = json.loads(self.fixture.joinpath("response.json").read_bytes())
                data = response["result"]["value"][2]["data"]
                raw = bytearray(base64.b64decode(data[0]))
                raw[offset:offset + len(value)] = value
                data[0] = base64.b64encode(raw).decode()
                with self.assertRaisesRegex(ValueError, message):
                    self.check(response=response)

    def test_rejects_unopened_pool_and_non_spl_legacy_modes(self):
        with self.assertRaisesRegex(ValueError, "fora do escopo"):
            self.check(block_time=0)
        for offset, value in ((329, 4), (390, 1), (328, 252)):
            with self.subTest(offset=offset):
                response = json.loads(self.fixture.joinpath("response.json").read_bytes())
                data = response["result"]["value"][0]["data"]
                raw = bytearray(base64.b64decode(data[0]))
                raw[offset] = value
                data[0] = base64.b64encode(raw).decode()
                with self.assertRaisesRegex(ValueError, "fora do escopo"):
                    self.check(response=response)


if __name__ == "__main__":
    unittest.main()
