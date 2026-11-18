import unittest

from smart_money_radar.data_sources.damm_v2_decoder import (
    EVT_SWAP2_DATA_LENGTH,
    EVT_SWAP2_DISCRIMINATOR,
    EVENT_CPI_TAG,
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP2_DISCRIMINATOR,
    SWAP_DISCRIMINATOR,
    decode_damm_v2_evt_swap2,
    decode_damm_v2_instruction,
)


def u64(value):
    return value.to_bytes(8, "little")


def u128(value):
    return value.to_bytes(16, "little")


def event_bytes(*, mode=0, direction=0, fee_mode=0, referral=0):
    body = (
        bytes(range(32))
        + bytes((direction, fee_mode, referral))
        + u64(101) + u64(202) + bytes((mode,))
        + u64(301) + u64(302) + u64(303) + u64(304) + u128(305)
        + u64(306) + u64(307) + u64(308) + u64(309)
        + u64(401) + u64(402) + u64(403)
        + u64(501) + u64(601) + u64(602)
    )
    result = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + body
    assert len(result) == EVT_SWAP2_DATA_LENGTH
    return result


class DammV2DecoderTests(unittest.TestCase):
    def test_decodes_legacy_swap_as_exact_in(self):
        data = SWAP_DISCRIMINATOR + u64(123) + u64(456)
        decoded = decode_damm_v2_instruction(METEORA_DAMM_V2_PROGRAM_ID, data)
        self.assertEqual(decoded.instruction_name, "swap")
        self.assertEqual(decoded.amount_0, 123)
        self.assertEqual(decoded.amount_1, 456)
        self.assertEqual(decoded.swap_mode, "EXACT_IN")
        self.assertTrue(decoded.legacy_exact_in)

    def test_decodes_swap2_exact_out_without_reversing_fields(self):
        data = SWAP2_DISCRIMINATOR + u64(700) + u64(900) + bytes((2,))
        decoded = decode_damm_v2_instruction(METEORA_DAMM_V2_PROGRAM_ID, data)
        self.assertEqual(decoded.swap_mode, "EXACT_OUT")
        self.assertEqual(decoded.amount_0, 700)  # output desejado
        self.assertEqual(decoded.amount_1, 900)  # input máximo

    def test_rejects_invalid_instruction_mode_and_length(self):
        with self.assertRaisesRegex(ValueError, "swap_mode"):
            decode_damm_v2_instruction(
                METEORA_DAMM_V2_PROGRAM_ID,
                SWAP2_DISCRIMINATOR + u64(1) + u64(2) + bytes((3,))
            )
        with self.assertRaisesRegex(ValueError, "exige"):
            decode_damm_v2_instruction(
                METEORA_DAMM_V2_PROGRAM_ID, SWAP_DISCRIMINATOR + u64(1)
            )

    def test_decodes_evt_swap2_fields_and_modes(self):
        decoded = decode_damm_v2_evt_swap2(
            METEORA_DAMM_V2_PROGRAM_ID,
            event_bytes(mode=2, direction=1, fee_mode=2, referral=1),
        )
        self.assertEqual(decoded.trade_direction, "B_TO_A")
        self.assertEqual(decoded.collect_fee_mode, "COMPOUNDING")
        self.assertTrue(decoded.has_referral)
        self.assertEqual(decoded.amount_0, 101)
        self.assertEqual(decoded.amount_1, 202)
        self.assertEqual(decoded.swap_mode, "EXACT_OUT")
        self.assertEqual(decoded.swap_result.included_fee_input_amount, 301)
        self.assertEqual(decoded.swap_result.next_sqrt_price, 305)
        self.assertEqual(decoded.swap_result.referral_fee, 309)
        self.assertEqual(decoded.included_transfer_fee_amount_in, 401)
        self.assertEqual(decoded.current_timestamp, 501)
        self.assertEqual(decoded.reserve_b_amount, 602)

    def test_unknown_event_and_wrong_program_are_not_classified(self):
        data = EVENT_CPI_TAG + bytes.fromhex("0102030405060708") + bytes(180)
        self.assertIsNone(decode_damm_v2_evt_swap2(METEORA_DAMM_V2_PROGRAM_ID, data))
        self.assertIsNone(decode_damm_v2_evt_swap2("other-program", event_bytes()))

    def test_rejects_truncated_event_and_invalid_enum_or_bool(self):
        with self.assertRaisesRegex(ValueError, "exige"):
            decode_damm_v2_evt_swap2(
                METEORA_DAMM_V2_PROGRAM_ID, event_bytes()[:-1]
            )
        with self.assertRaisesRegex(ValueError, "trade_direction"):
            decode_damm_v2_evt_swap2(
                METEORA_DAMM_V2_PROGRAM_ID, event_bytes(direction=2)
            )
        with self.assertRaisesRegex(ValueError, "booleano"):
            decode_damm_v2_evt_swap2(
                METEORA_DAMM_V2_PROGRAM_ID, event_bytes(referral=2)
            )


if __name__ == "__main__":
    unittest.main()
