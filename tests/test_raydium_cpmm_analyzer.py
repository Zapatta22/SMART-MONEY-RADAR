import unittest

from smart_money_radar.data_sources.raydium_cpmm_analyzer import (
    decode_raydium_cpmm_swaps,
)
from smart_money_radar.data_sources.raydium_cpmm_decoder import (
    RAYDIUM_CPMM_PROGRAM_ID,
    SWAP_BASE_INPUT_DISCRIMINATOR,
    SWAP_BASE_OUTPUT_DISCRIMINATOR,
    RaydiumCpmmSwapBaseInput,
    RaydiumCpmmSwapBaseOutput,
)


def _encode_base58(data):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = alphabet[remainder] + encoded
    leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading_zeros + encoded


def _instruction(discriminator, first=101, second=202, account_count=13):
    data = (
        discriminator
        + first.to_bytes(8, "little")
        + second.to_bytes(8, "little")
    )
    return {
        "programId": RAYDIUM_CPMM_PROGRAM_ID,
        "accounts": list(range(account_count)),
        "data": _encode_base58(data),
    }


def _transaction(instructions, keys=None, meta=None):
    return {
        "transaction": {
            "message": {
                "accountKeys": keys or [f"Account{i}" for i in range(20)],
                "instructions": instructions,
            }
        },
        "meta": meta or {"err": None},
    }


class TestRaydiumCpmmAnalyzer(unittest.TestCase):
    def test_decodes_exact_input(self):
        result = decode_raydium_cpmm_swaps(
            _transaction([_instruction(SWAP_BASE_INPUT_DISCRIMINATOR)])
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].instruction, RaydiumCpmmSwapBaseInput(101, 202))
        self.assertEqual(result[0].instruction_index, 0)

    def test_decodes_exact_output(self):
        result = decode_raydium_cpmm_swaps(
            _transaction([_instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)])
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].instruction, RaydiumCpmmSwapBaseOutput(101, 202))

    def test_preserves_extra_accounts(self):
        result = decode_raydium_cpmm_swaps(
            _transaction([
                _instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR, account_count=15)
            ])
        )
        self.assertEqual(result[0].accounts.remaining_accounts, ("Account13", "Account14"))

    def test_resolves_program_id_index_and_loaded_addresses(self):
        static_keys = [f"Static{i}" for i in range(13)]
        static_keys.append(RAYDIUM_CPMM_PROGRAM_ID)
        instruction = _instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)
        instruction.pop("programId")
        instruction["programIdIndex"] = 13
        instruction["accounts"] = list(range(13))
        meta = {
            "err": None,
            "loadedAddresses": {"writable": [], "readonly": []},
        }
        result = decode_raydium_cpmm_swaps(
            _transaction([instruction], static_keys, meta)
        )
        self.assertEqual(len(result), 1)

    def test_resolves_program_and_accounts_from_loaded_addresses(self):
        static_keys = [f"Static{i}" for i in range(13)]
        instruction = _instruction(
            SWAP_BASE_OUTPUT_DISCRIMINATOR,
            account_count=14,
        )
        instruction.pop("programId")
        instruction["programIdIndex"] = 14
        instruction["accounts"] = list(range(14))
        meta = {
            "err": None,
            "loadedAddresses": {
                "writable": ["LoadedExtra"],
                "readonly": [RAYDIUM_CPMM_PROGRAM_ID],
            },
        }
        result = decode_raydium_cpmm_swaps(
            _transaction([instruction], static_keys, meta)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0].accounts.remaining_accounts,
            ("LoadedExtra",),
        )

    def test_accepts_already_resolved_account_pubkeys(self):
        instruction = _instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)
        instruction["accounts"] = [f"Resolved{i}" for i in range(13)]
        result = decode_raydium_cpmm_swaps(_transaction([instruction]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].accounts.payer, "Resolved0")
        self.assertEqual(result[0].accounts.observation_state, "Resolved12")

    def test_does_not_treat_inner_instruction_as_top_level_swap(self):
        meta = {
            "err": None,
            "innerInstructions": [
                {
                    "index": 0,
                    "instructions": [
                        _instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)
                    ],
                }
            ],
        }
        result = decode_raydium_cpmm_swaps(
            _transaction([], meta=meta)
        )
        self.assertEqual(result, [])

    def test_ignores_failed_transaction(self):
        result = decode_raydium_cpmm_swaps(
            _transaction(
                [_instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)],
                meta={"err": {"InstructionError": [0, "Custom"]}},
            )
        )
        self.assertEqual(result, [])

    def test_rejects_invalid_account_index(self):
        instruction = _instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)
        instruction["accounts"][-1] = 999
        with self.assertRaisesRegex(ValueError, "índice de conta inválido"):
            decode_raydium_cpmm_swaps(_transaction([instruction]))

    def test_rejects_invalid_base58(self):
        instruction = _instruction(SWAP_BASE_OUTPUT_DISCRIMINATOR)
        instruction["data"] = "0"
        with self.assertRaisesRegex(ValueError, "base58 inválido"):
            decode_raydium_cpmm_swaps(_transaction([instruction]))

    def test_rejects_non_dict_transaction(self):
        with self.assertRaises(TypeError):
            decode_raydium_cpmm_swaps("invalid")


if __name__ == "__main__":
    unittest.main()
