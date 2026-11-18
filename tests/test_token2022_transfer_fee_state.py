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
    return bytes(165) + bytes([ACCOUNT_TYPE_MINT]) + b"".join(entries)


def account_data(entries):
    return bytes(165) + bytes([ACCOUNT_TYPE_ACCOUNT]) + b"".join(entries)


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

    def test_skips_unknown_extension(self):
        value = decode_transfer_fee_config(mint_data([tlv(99, b"unknown"), tlv(1, config())]))
        self.assertEqual(value.newer_transfer_fee.basis_points, 50)

    def test_accepts_zero_padding(self):
        self.assertEqual(decode_transfer_fee_config(mint_data([tlv(1, config())]) + bytes(12)).withheld_amount, 7)

    def test_rejects_nonzero_mint_padding(self):
        data = bytearray(mint_data([tlv(1, config())]))
        data[100] = 1
        with self.assertRaisesRegex(ValueError, "padding do mint"):
            decode_transfer_fee_config(bytes(data))

    def test_rejects_wrong_account_type(self):
        with self.assertRaisesRegex(ValueError, "AccountType"):
            decode_transfer_fee_config(account_data([tlv(1, config())]))
        with self.assertRaisesRegex(ValueError, "AccountType"):
            decode_transfer_fee_amount(mint_data([tlv(2, u64(1))]))

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


if __name__ == "__main__":
    unittest.main()
