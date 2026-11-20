import unittest
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

    def test_rejects_invalid_rates(self):
        raw = self.config()
        raw[12:20] = (1000001).to_bytes(8, "little")
        with self.assertRaises(ValueError):
            decode_amm_config(bytes(raw))


if __name__ == "__main__":
    unittest.main()
