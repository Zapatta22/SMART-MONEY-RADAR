import unittest

from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    ACCOUNT_TYPE_ACCOUNT, ACCOUNT_TYPE_MINT, decode_transfer_fee_amount,
    decode_transfer_fee_config,
)


def u16(n):
    return n.to_bytes(2, "little")


def u64(n):
    return n.to_bytes(8, "little")


def tlv(kind, payload):
    return u16(kind) + u16(len(payload)) + payload


def mint_data(entries):
    base = bytearray(165)
    base[45] = 1  # Mint.is_initialized
    return bytes(base) + bytes([ACCOUNT_TYPE_MINT]) + b"".join(entries)


def account_data(entries):
    base = bytearray(165)
    base[108] = 1  # AccountState::Initialized
    return bytes(base) + bytes([ACCOUNT_TYPE_ACCOUNT]) + b"".join(entries)


def config(older=(10, 100, 25), newer=(100, 200, 50), withheld=7):
    return bytes(64) + u64(withheld) + u64(older[0]) + u64(older[1]) + u16(older[2]) + u64(newer[0]) + u64(newer[1]) + u16(newer[2])


class TransferFeeStateDecoderTests(unittest.TestCase):
    def test_config_fields_and_epoch_boundary(self):
        value = decode_transfer_fee_config(mint_data([tlv(1, config())]))
        self.assertEqual(value.withheld_amount, 7)
        self.assertEqual(value.fee_for_epoch(99), value.older_transfer_fee)
        self.assertEqual(value.fee_for_epoch(100), value.newer_transfer_fee)

    def test_account_withheld_amount(self):
        self.assertEqual(decode_transfer_fee_amount(account_data([tlv(2, u64(987))])).withheld_amount, 987)

    def test_skips_known_other_extension(self):
        value = decode_transfer_fee_config(mint_data([tlv(3, b"other"), tlv(1, config())]))
        self.assertEqual(value.newer_transfer_fee.basis_points, 50)

    def test_rejects_unknown_extension_type(self):
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            decode_transfer_fee_config(mint_data([tlv(99, b"unknown"), tlv(1, config())]))

    def test_accepts_zero_padding(self):
        self.assertEqual(decode_transfer_fee_config(mint_data([tlv(1, config())]) + bytes(12)).withheld_amount, 7)

    def test_accepts_single_trailing_byte_during_reallocation(self):
        data = mint_data([tlv(1, config())]) + b"\x7f"
        self.assertEqual(decode_transfer_fee_config(data).withheld_amount, 7)

    def test_uninitialized_tlv_type_terminates_extension_list(self):
        data = mint_data([tlv(1, config())]) + b"\x00\x00\xff\xff"
        self.assertEqual(decode_transfer_fee_config(data).withheld_amount, 7)

    def test_rejects_nonzero_mint_padding(self):
        data = bytearray(mint_data([tlv(1, config())]))
        data[100] = 1
        with self.assertRaisesRegex(ValueError, "padding do mint"):
            decode_transfer_fee_config(bytes(data))

    def test_rejects_wrong_account_type(self):
        wrong_mint = bytearray(mint_data([tlv(1, config())]))
        wrong_mint[165] = ACCOUNT_TYPE_ACCOUNT
        with self.assertRaisesRegex(ValueError, "AccountType"):
            decode_transfer_fee_config(bytes(wrong_mint))
        wrong_account = bytearray(account_data([tlv(2, u64(1))]))
        wrong_account[165] = ACCOUNT_TYPE_MINT
        with self.assertRaisesRegex(ValueError, "AccountType"):
            decode_transfer_fee_amount(bytes(wrong_account))

    def test_rejects_missing_extension(self):
        with self.assertRaisesRegex(ValueError, "ausente"):
            decode_transfer_fee_config(mint_data([]))
        with self.assertRaisesRegex(ValueError, "ausente"):
            decode_transfer_fee_amount(account_data([]))

    def test_rejects_truncated_account_and_tlv(self):
        with self.assertRaises(ValueError):
            decode_transfer_fee_config(bytes(165))
        with self.assertRaisesRegex(ValueError, "cabeçalho TLV"):
            decode_transfer_fee_config(mint_data([]) + b"\x01\x00")
        with self.assertRaisesRegex(ValueError, "payload TLV"):
            decode_transfer_fee_config(mint_data([]) + u16(1) + u16(108) + b"x")

    def test_rejects_wrong_payload_lengths(self):
        with self.assertRaisesRegex(ValueError, "tamanho inválido"):
            decode_transfer_fee_config(mint_data([tlv(1, bytes(107))]))
        with self.assertRaisesRegex(ValueError, "tamanho inválido"):
            decode_transfer_fee_amount(account_data([tlv(2, bytes(7))]))

    def test_rejects_duplicate_extension(self):
        entry = tlv(1, config())
        with self.assertRaisesRegex(ValueError, "duplicada"):
            decode_transfer_fee_config(mint_data([entry, entry]))

    def test_rejects_basis_points_above_10000(self):
        with self.assertRaisesRegex(ValueError, "excede 10000"):
            decode_transfer_fee_config(mint_data([tlv(1, config(older=(1, 1, 10001)))]))

    def test_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            decode_transfer_fee_config(bytearray(200))
        with self.assertRaises(TypeError):
            decode_transfer_fee_amount("no")

    def test_rejects_invalid_epoch(self):
        value = decode_transfer_fee_config(mint_data([tlv(1, config())]))
        with self.assertRaises(ValueError):
            value.fee_for_epoch(True)

    def test_rejects_uninitialized_or_invalid_mint_state(self):
        for state in (0, 2):
            data = bytearray(mint_data([tlv(1, config())]))
            data[45] = state
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "Mint não inicializado"):
                decode_transfer_fee_config(bytes(data))

    def test_rejects_invalid_mint_coption_tags(self):
        data = bytearray(mint_data([tlv(1, config())]))
        data[0] = 2
        with self.assertRaisesRegex(ValueError, "mint_authority"):
            decode_transfer_fee_config(bytes(data))
        data = bytearray(mint_data([tlv(1, config())]))
        data[46] = 2
        with self.assertRaisesRegex(ValueError, "freeze_authority"):
            decode_transfer_fee_config(bytes(data))

    def test_rejects_uninitialized_or_invalid_token_account_state(self):
        for state in (0, 3):
            data = bytearray(account_data([tlv(2, u64(1))]))
            data[108] = state
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "token account"):
                decode_transfer_fee_amount(bytes(data))

    def test_accepts_frozen_token_account(self):
        data = bytearray(account_data([tlv(2, u64(987))]))
        data[108] = 2
        self.assertEqual(decode_transfer_fee_amount(bytes(data)).withheld_amount, 987)

    def test_rejects_invalid_token_account_coption_tags(self):
        for offset, field in ((72, "delegate"), (109, "is_native"), (129, "close_authority")):
            data = bytearray(account_data([tlv(2, u64(1))]))
            data[offset] = 2
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                decode_transfer_fee_amount(bytes(data))

    def test_rejects_multisig_length_collision(self):
        mint = mint_data([tlv(1, config())])
        account = account_data([tlv(2, u64(1))])
        mint += bytes(355 - len(mint))
        account += bytes(355 - len(account))
        with self.assertRaisesRegex(ValueError, "tamanho de base Mint"):
            decode_transfer_fee_config(mint)
        with self.assertRaisesRegex(ValueError, "tamanho de base token account"):
            decode_transfer_fee_amount(account)


if __name__ == "__main__":
    unittest.main()
