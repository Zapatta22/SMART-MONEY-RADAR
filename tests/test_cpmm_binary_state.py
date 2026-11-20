import base64
import hashlib
import json
import unittest
from pathlib import Path
from smart_money_radar.domain.cpmm_binary_state import (
    POOL_LENGTH, CONFIG_LENGTH, POOL_DISCRIMINATOR, CONFIG_DISCRIMINATOR,
    decode_pool_state, decode_amm_config, verify_pool_swap_identity,
)


class CPMMBinaryStateTests(unittest.TestCase):
    def pool(self):
        raw = bytearray(POOL_LENGTH)
        raw[:8] = POOL_DISCRIMINATOR
        for index in range(10):
            raw[8 + index*32:8 + (index+1)*32] = bytes([index+1])*32
        raw[331] = 9
        raw[332] = 6
        raw[341:349] = (12).to_bytes(8, "little")
        return raw

    def config(self):
        raw = bytearray(CONFIG_LENGTH)
        raw[:8] = CONFIG_DISCRIMINATOR
        raw[12:20] = (2500).to_bytes(8, "little")
        raw[20:28] = (120000).to_bytes(8, "little")
        raw[28:36] = (100000).to_bytes(8, "little")
        raw[108:116] = (500).to_bytes(8, "little")
        return raw

    def test_decodes_pool_and_config(self):
        pool = decode_pool_state(bytes(self.pool()))
        config = decode_amm_config(bytes(self.config()))
        self.assertEqual(pool.protocol_fees_token_0, 12)
        self.assertEqual((pool.mint_0_decimals, pool.mint_1_decimals), (9, 6))
        self.assertEqual(config.trade_fee_rate, 2500)
        self.assertEqual(config.creator_fee_rate, 500)
        self.assertTrue(verify_pool_swap_identity(
            pool, config, amm_config=pool.amm_config,
            input_vault=pool.token_0_vault, output_vault=pool.token_1_vault,
            input_mint=pool.token_0_mint, output_mint=pool.token_1_mint,
            input_token_program=pool.token_0_program,
            output_token_program=pool.token_1_program))
        self.assertTrue(verify_pool_swap_identity(
            pool, config, amm_config=pool.amm_config,
            input_vault=pool.token_1_vault, output_vault=pool.token_0_vault,
            input_mint=pool.token_1_mint, output_mint=pool.token_0_mint,
            input_token_program=pool.token_1_program,
            output_token_program=pool.token_0_program))

    def test_rejects_invalid_discriminator_length_and_status(self):
        with self.assertRaises(ValueError):
            decode_pool_state(bytes(POOL_LENGTH))
        with self.assertRaises(ValueError):
            decode_amm_config(bytes(CONFIG_LENGTH - 1))
        raw = self.pool()
        raw[329] = 4
        pool = decode_pool_state(bytes(raw))
        config = decode_amm_config(bytes(self.config()))
        with self.assertRaisesRegex(ValueError, "desabilitado"):
            verify_pool_swap_identity(
                pool, config, amm_config=pool.amm_config,
                input_vault=pool.token_0_vault, output_vault=pool.token_1_vault,
                input_mint=pool.token_0_mint, output_mint=pool.token_1_mint,
                input_token_program=pool.token_0_program,
                output_token_program=pool.token_1_program)

    def test_pubkey_preserves_binary_zero_prefix_and_ascii_zero_byte(self):
        raw = self.pool()
        raw[8:40] = bytes(31) + b"\x01"
        self.assertEqual(decode_pool_state(bytes(raw)).amm_config, "1" * 31 + "2")
        raw[8:40] = bytes(32)
        self.assertEqual(decode_pool_state(bytes(raw)).amm_config, "1" * 32)
        raw[8:40] = bytes([48]) + bytes(31)
        self.assertFalse(decode_pool_state(bytes(raw)).amm_config.startswith("1"))

    def test_rejects_invalid_creator_fee_mode_and_boolean(self):
        for offset, value in ((389, 3), (390, 2)):
            with self.subTest(offset=offset):
                raw = self.pool()
                raw[offset] = value
                with self.assertRaisesRegex(ValueError, "taxa do criador"):
                    decode_pool_state(bytes(raw))

    def test_matches_archived_mainnet_snapshot_and_independent_raydium_pool_metadata(self):
        fixture = Path(__file__).resolve().parents[1] / "data/fixtures/mainnet/raydium-cpmm-state"
        digests = {
            "request.json": "4ab717f3aaa08d807ea51ffb73a8163443adf8a0a61f115a0d0cc667de7502e8",
            "response.json": "7b449069fce62d5ccf96cf3cb96644e205ba19e6d71af67ad4b34648eedd71f4",
            "raydium-pool-keys.json": "849c2b6d3adefcbc94382890adc8b193d1b80abf672272cba0414aa8d4107043",
        }

        def load(name):
            raw = (fixture / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digests[name])
            return json.loads(raw)

        request = load("request.json")
        response = load("response.json")
        keys = load("raydium-pool-keys.json")["data"][0]
        self.assertEqual(request["method"], "getMultipleAccounts")
        self.assertEqual(request["id"], response["id"])
        self.assertEqual(request["params"][1], {"encoding": "base64", "commitment": "finalized"})
        self.assertEqual(response["result"]["context"]["slot"], 471539976)
        self.assertEqual(request["params"][0], [
            keys["id"], keys["config"]["id"], keys["vault"]["A"], keys["vault"]["B"],
        ])
        accounts = response["result"]["value"]
        state_account, config_account = accounts[:2]
        for account in (state_account, config_account):
            self.assertEqual(account["owner"], keys["programId"])
            self.assertIs(account["executable"], False)
            self.assertEqual(account["data"][1], "base64")
        state = decode_pool_state(base64.b64decode(state_account["data"][0], validate=True))
        config = decode_amm_config(base64.b64decode(config_account["data"][0], validate=True))
        for field, expected in {
            "amm_config": keys["config"]["id"],
            "token_0_vault": keys["vault"]["A"], "token_1_vault": keys["vault"]["B"],
            "token_0_mint": keys["mintA"]["address"], "token_1_mint": keys["mintB"]["address"],
            "token_0_program": keys["mintA"]["programId"], "token_1_program": keys["mintB"]["programId"],
            "mint_0_decimals": keys["mintA"]["decimals"], "mint_1_decimals": keys["mintB"]["decimals"],
            "observation_key": keys["observationId"], "open_time": int(keys["openTime"]),
        }.items():
            with self.subTest(field=field):
                self.assertEqual(getattr(state, field), expected)
        self.assertEqual((config.trade_fee_rate, config.protocol_fee_rate,
                          config.fund_fee_rate, config.creator_fee_rate),
                         tuple(keys["config"][key] for key in (
                             "tradeFeeRate", "protocolFeeRate", "fundFeeRate", "creatorFeeRate",
                         )))

    def test_rejects_invalid_rates(self):
        raw = self.config()
        raw[12:20] = (1000001).to_bytes(8, "little")
        with self.assertRaises(ValueError):
            decode_amm_config(bytes(raw))


if __name__ == "__main__":
    unittest.main()
