import unittest

from smart_money_radar.data_sources.solana_wrapped_sol_funding import (
    decode_wrapped_sol_funding,
)


ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58(data):
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, digit = divmod(number, 58)
        encoded = ALPHABET[digit] + encoded
    return "1" * (len(data) - len(data.lstrip(b"\\0"))) + (encoded or "")


def _transaction(amount=20700, lamports_delta=0, sync_index=1):
    keys = [
        "wallet",
        "wsol-account",
        "11111111111111111111111111111111",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "damm-program",
    ]
    transfer_data = (2).to_bytes(4, "little") + amount.to_bytes(8, "little")
    instructions = [
        {
            "programIdIndex": 2,
            "accounts": [0, 1],
            "data": _b58(transfer_data),
        },
        {
            "programIdIndex": 3,
            "accounts": [1],
            "data": _b58(bytes([17])),
        },
        {
            "programIdIndex": 4,
            "accounts": [0, 1],
            "data": _b58(b"swap"),
        },
    ]
    if sync_index is None:
        instructions.pop(1)
    elif sync_index != 1:
        sync = instructions.pop(1)
        instructions.insert(sync_index, sync)
    return {
        "result": {
            "transaction": {
                "message": {
                    "accountKeys": keys,
                    "instructions": instructions,
                }
            },
            "meta": {
                "preBalances": [10_000_000, 2_000_000, 1, 1, 1],
                "postBalances": [10_000_000 - amount, 2_000_000 + lamports_delta, 1, 1, 1],
            },
        }
    }


class WrappedSolFundingTests(unittest.TestCase):
    def _decode(self, raw, amount=20700):
        return decode_wrapped_sol_funding(
            raw,
            token_account="wsol-account",
            source_wallet="wallet",
            amount_raw=amount,
            before_instruction_index=2,
        )

    def test_recognizes_exact_system_transfer_then_sync_native(self):
        result = self._decode(_transaction())
        self.assertIsNotNone(result)
        self.assertEqual(result.amount_raw, 20700)
        self.assertEqual(result.system_transfer_index, 0)
        self.assertEqual(result.sync_native_index, 1)
        self.assertEqual(result.lamports_delta_raw, 0)

    def test_rejects_funding_amount_mismatch(self):
        with self.assertRaisesRegex(ValueError, "diverge"):
            self._decode(_transaction(amount=20701))

    def test_aggregates_multiple_funding_transfers_before_one_sync_native(self):
        raw = _transaction(amount=20700)
        instructions = raw["result"]["transaction"]["message"]["instructions"]
        transfer = dict(instructions[0])
        sync = dict(instructions[1])
        instructions[:] = [transfer, transfer, sync, instructions[2]]
        result = decode_wrapped_sol_funding(
            raw, token_account="wsol-account", source_wallet="wallet",
            amount_raw=41400, before_instruction_index=3,
        )
        self.assertEqual(result.amount_raw, 41400)
        self.assertEqual(result.system_transfer_indices, (0, 1))
        self.assertEqual(result.sync_native_index, 2)

    def test_rejects_missing_sync_native(self):
        with self.assertRaisesRegex(ValueError, "SyncNative"):
            self._decode(_transaction(sync_index=None))


    def test_rejects_funding_from_a_different_wallet(self):
        raw = _transaction()
        raw["result"]["transaction"]["message"]["instructions"][0]["accounts"] = [1, 0]
        with self.assertRaisesRegex(ValueError, "origem/destino"):
            self._decode(raw)

    def test_rejects_sync_native_after_the_swap(self):
        raw = _transaction()
        instructions = raw["result"]["transaction"]["message"]["instructions"]
        sync = instructions.pop(1)
        instructions.append(sync)
        with self.assertRaisesRegex(ValueError, "ordem"):
            decode_wrapped_sol_funding(
                raw, token_account="wsol-account", source_wallet="wallet",
                amount_raw=20700, before_instruction_index=2,
            )

    def test_rejects_duplicate_sync_native(self):
        raw = _transaction()
        instructions = raw["result"]["transaction"]["message"]["instructions"]
        instructions.insert(2, dict(instructions[1]))
        with self.assertRaisesRegex(ValueError, "univocamente"):
            self._decode(raw)

    def test_rejects_duplicate_system_transfers(self):
        raw = _transaction()
        instructions = raw["result"]["transaction"]["message"]["instructions"]
        instructions.insert(1, dict(instructions[0]))
        with self.assertRaisesRegex(ValueError, "diverge"):
            self._decode(raw)

    def test_rejects_missing_lamport_snapshots(self):
        raw = _transaction()
        raw["result"]["meta"]["preBalances"] = []
        with self.assertRaisesRegex(ValueError, "lamport snapshots"):
            self._decode(raw)

    def test_returns_none_when_no_native_funding_touches_the_account(self):
        raw = _transaction()
        raw["result"]["transaction"]["message"]["instructions"].pop(0)
        self.assertIsNone(self._decode(raw))

    def test_rejects_nonzero_wrapped_account_lamport_delta(self):
        with self.assertRaisesRegex(ValueError, "lamports"):
            self._decode(_transaction(lamports_delta=1))


if __name__ == "__main__":
    unittest.main()
