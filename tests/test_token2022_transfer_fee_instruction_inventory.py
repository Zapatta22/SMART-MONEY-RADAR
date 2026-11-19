import unittest

from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    TOKEN_2022_PROGRAM_ID,
    decode_solana_instruction_inventory,
)
from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    collect_transfer_fee_config_init_positions,
)


def _b58(data):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = alphabet[rem] + encoded
    return "1" * (len(data) - len(data.lstrip(b"\\x00"))) + encoded


def _init_fee(basis_points=100, maximum_fee=999):
    return (
        bytes([26, 0]) + bytes(4) + bytes(4)
        + basis_points.to_bytes(2, "little")
        + maximum_fee.to_bytes(8, "little")
    )


def _set_fee(basis_points=250, maximum_fee=1234):
    return (
        bytes([26, 5]) + basis_points.to_bytes(2, "little")
        + maximum_fee.to_bytes(8, "little")
    )


def _tx(instructions, inner=None, keys=None):
    return {
        "transaction": {
            "signatures": ["sig"],
            "message": {
                "accountKeys": keys or ["mint", TOKEN_2022_PROGRAM_ID],
                "instructions": instructions,
            },
        },
        "meta": {
            "err": None,
            "innerInstructions": [] if inner is None else inner,
        },
        "slot": 123,
    }


class Token2022TransferFeeInstructionInventoryTests(unittest.TestCase):
    def test_collects_outer_and_inner_initialize_positions_for_exact_mint(self):
        raw = _tx(
            [
                {
                    "programId": TOKEN_2022_PROGRAM_ID,
                    "accounts": [0],
                    "data": _b58(_init_fee()),
                },
                {
                    "programId": TOKEN_2022_PROGRAM_ID,
                    "accounts": [0],
                    "data": _b58(_set_fee()),
                },
            ],
            inner=[
                {
                    "index": 0,
                    "instructions": [
                        {
                            "programId": TOKEN_2022_PROGRAM_ID,
                            "accounts": [0],
                            "data": _b58(_init_fee(200, 2000)),
                            "stackHeight": 2,
                        }
                    ],
                }
            ],
        )
        inventory = decode_solana_instruction_inventory(raw)
        result = collect_transfer_fee_config_init_positions(inventory, "mint")
        self.assertTrue(inventory.complete)
        self.assertTrue(result.complete)
        self.assertEqual(result.initialization_positions, ((0, -1), (0, 0)))

    def test_ignores_initialize_instruction_for_another_mint(self):
        raw = _tx(
            [{
                "programId": TOKEN_2022_PROGRAM_ID,
                "accounts": [0],
                "data": _b58(_init_fee()),
            }],
            keys=["other-mint", TOKEN_2022_PROGRAM_ID],
        )
        inventory = decode_solana_instruction_inventory(raw)
        result = collect_transfer_fee_config_init_positions(inventory, "mint")
        self.assertTrue(result.complete)
        self.assertEqual(result.initialization_positions, ())

    def test_set_transfer_fee_is_validated_but_not_recorded_as_initialization(self):
        raw = _tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": [0],
            "data": _b58(_set_fee()),
        }])
        result = collect_transfer_fee_config_init_positions(
            decode_solana_instruction_inventory(raw), "mint"
        )
        self.assertTrue(result.complete)
        self.assertEqual(result.initialization_positions, ())

    def test_missing_inner_instruction_inventory_fails_closed(self):
        raw = _tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": [0],
            "data": _b58(_init_fee()),
        }])
        del raw["meta"]["innerInstructions"]
        inventory = decode_solana_instruction_inventory(raw)
        result = collect_transfer_fee_config_init_positions(inventory, "mint")
        self.assertFalse(inventory.complete)
        self.assertFalse(result.complete)
        self.assertTrue(result.issues)

    def test_unknown_transfer_fee_extension_subtag_fails_closed_for_mint(self):
        raw = _tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": [0],
            "data": _b58(bytes([26, 99, 1, 2, 3])),
        }])
        result = collect_transfer_fee_config_init_positions(
            decode_solana_instruction_inventory(raw), "mint"
        )
        self.assertFalse(result.complete)
        self.assertIn("subtag TransferFeeExtension desconhecida", result.issues[0])

    def test_supports_json_parsed_initialize_instruction(self):
        raw = _tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": ["mint"],
            "parsed": {
                "type": "initializeTransferFeeConfig",
                "info": {
                    "transferFeeBasisPoints": 100,
                    "maximumFee": 999,
                },
            },
        }])
        result = collect_transfer_fee_config_init_positions(
            decode_solana_instruction_inventory(raw), "mint"
        )
        self.assertTrue(result.complete)
        self.assertEqual(result.initialization_positions, ((0, -1),))

    def test_rejects_malformed_transfer_fee_init_instruction(self):
        raw = _tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": [0],
            "data": _b58(bytes([26, 0, 2, 0, 0, 0])),
        }])
        result = collect_transfer_fee_config_init_positions(
            decode_solana_instruction_inventory(raw), "mint"
        )
        self.assertFalse(result.complete)
        self.assertIn("InitializeTransferFeeConfig inválida", result.issues[0])



    def test_failed_transaction_is_not_a_complete_instruction_inventory(self):
        raw = _tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": [0],
            "data": _b58(_init_fee()),
        }])
        raw["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        inventory = decode_solana_instruction_inventory(raw)
        self.assertFalse(inventory.complete)
        self.assertIn("não foi executada", inventory.issues[0])

if __name__ == "__main__":
    unittest.main()
