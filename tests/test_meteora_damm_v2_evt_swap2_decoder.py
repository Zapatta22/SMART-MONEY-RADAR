import unittest

from smart_money_radar.data_sources.meteora_damm_v2_evt_swap2_decoder import (
    ANCHOR_EVENT_DISCRIMINATOR,
    EVT_SWAP2_DISCRIMINATOR,
    EVT_SWAP2_DATA_LENGTH,
    decode_meteora_damm_v2_evt_swap2,
)


def u8(value):
    return bytes([value])


def u64(value):
    return value.to_bytes(8, "little")


def u128(value):
    return value.to_bytes(16, "little")


def sample_data(
    *,
    pool=bytes(32),
    direction=0,
    collect_mode=2,
    has_referral=1,
    swap_mode=1,
):
    body = bytearray(pool)
    body.extend(u8(direction))
    body.extend(u8(collect_mode))
    body.extend(u8(has_referral))
    body.extend(u64(1_000))
    body.extend(u64(900))
    body.extend(u8(swap_mode))
    body.extend(u64(1_000))  # included_fee_input_amount
    body.extend(u64(990))    # excluded_fee_input_amount
    body.extend(u64(10))     # amount_left
    body.extend(u64(950))    # output_amount
    body.extend(u128(1 << 64))
    body.extend(u64(5))      # claiming_fee
    body.extend(u64(2))      # protocol_fee
    body.extend(u64(1))      # compounding_fee
    body.extend(u64(1))      # referral_fee
    body.extend(u64(10))     # included_transfer_fee_amount_in
    body.extend(u64(3))      # included_transfer_fee_amount_out
    body.extend(u64(947))    # excluded_transfer_fee_amount_out
    body.extend(u64(1_700_000_000))
    body.extend(u64(100_000))
    body.extend(u64(200_000))
    assert len(body) == 180
    return ANCHOR_EVENT_DISCRIMINATOR + EVT_SWAP2_DISCRIMINATOR + bytes(body)


class MeteoraDammV2EvtSwap2DecoderTests(unittest.TestCase):
    def test_decodes_current_idl_layout_and_raw_amounts(self):
        event = decode_meteora_damm_v2_evt_swap2(sample_data())
        self.assertEqual(event.pool, "1" * 32)
        self.assertEqual(event.trade_direction, 0)
        self.assertEqual(event.collect_fee_mode, 2)
        self.assertTrue(event.has_referral)
        self.assertEqual(event.amount_0, 1_000)
        self.assertEqual(event.amount_1, 900)
        self.assertEqual(event.swap_mode, 1)
        self.assertEqual(event.included_fee_input_amount, 1_000)
        self.assertEqual(event.excluded_fee_input_amount, 990)
        self.assertEqual(event.amount_left, 10)
        self.assertEqual(event.output_amount, 950)
        self.assertEqual(event.next_sqrt_price, 1 << 64)
        self.assertEqual(event.claiming_fee, 5)
        self.assertEqual(event.protocol_fee, 2)
        self.assertEqual(event.compounding_fee, 1)
        self.assertEqual(event.referral_fee, 1)
        self.assertEqual(event.reserve_a_amount, 100_000)
        self.assertEqual(event.reserve_b_amount, 200_000)

    def test_encodes_nonzero_pool_pubkey_as_base58(self):
        event = decode_meteora_damm_v2_evt_swap2(sample_data(pool=bytes([1]) * 32))
        self.assertTrue(event.pool)
        self.assertNotEqual(event.pool, "1" * 32)

    def test_rejects_wrong_anchor_discriminator(self):
        data = bytearray(sample_data())
        data[0] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "Anchor event discriminator"):
            decode_meteora_damm_v2_evt_swap2(bytes(data))

    def test_rejects_wrong_event_discriminator(self):
        data = bytearray(sample_data())
        data[8] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "EvtSwap2 discriminator"):
            decode_meteora_damm_v2_evt_swap2(bytes(data))

    def test_rejects_truncated_and_trailing_data(self):
        data = sample_data()
        self.assertEqual(len(data), EVT_SWAP2_DATA_LENGTH)
        with self.assertRaisesRegex(ValueError, "tamanho inválido"):
            decode_meteora_damm_v2_evt_swap2(data[:-1])
        with self.assertRaisesRegex(ValueError, "tamanho inválido"):
            decode_meteora_damm_v2_evt_swap2(data + b"\\x00")

    def test_rejects_non_borsh_boolean(self):
        with self.assertRaisesRegex(ValueError, "Borsh bool"):
            decode_meteora_damm_v2_evt_swap2(sample_data(has_referral=2))

    def test_rejects_unknown_trade_direction(self):
        with self.assertRaisesRegex(ValueError, "trade_direction"):
            decode_meteora_damm_v2_evt_swap2(sample_data(direction=2))

    def test_rejects_unknown_collect_fee_mode(self):
        with self.assertRaisesRegex(ValueError, "collect_fee_mode"):
            decode_meteora_damm_v2_evt_swap2(sample_data(collect_mode=3))

    def test_rejects_unknown_swap_mode(self):
        with self.assertRaisesRegex(ValueError, "swap_mode"):
            decode_meteora_damm_v2_evt_swap2(sample_data(swap_mode=3))

    def test_rejects_non_bytes_input(self):
        with self.assertRaises(TypeError):
            decode_meteora_damm_v2_evt_swap2(bytearray(sample_data()))


if __name__ == "__main__":
    unittest.main()
