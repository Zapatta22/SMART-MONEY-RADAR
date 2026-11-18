import unittest

from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    decode_solana_token_transfers,
)


def _b58(data):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = alphabet[rem] + encoded
    return "1" * (len(data) - len(data.lstrip(b"\\x00"))) + encoded


def _transfer(opcode=3, amount=1234, decimals=6):
    data = bytes([opcode]) + amount.to_bytes(8, "little")
    if opcode == 12:
        data += bytes([decimals])
    return _b58(data)


def _tx(instructions, keys=None, meta=None):
    return {
        "transaction": {
            "signatures": ["signature-1"],
            "message": {
                "accountKeys": keys or ["source", "destination", "authority", "mint", SPL_TOKEN_PROGRAM_ID],
                "instructions": instructions,
            },
        },
        "meta": meta if meta is not None else {"err": None},
    }


class TokenTransferDecoderTests(unittest.TestCase):
    def test_decodes_compiled_transfer(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": SPL_TOKEN_PROGRAM_ID,
            "accounts": [0, 1, 2],
            "data": _transfer(3, 500),
        }]))
        self.assertEqual(len(result), 1)
        transfer = result[0]
        self.assertEqual(transfer.instruction_type, "TRANSFER")
        self.assertEqual(transfer.source_account, "source")
        self.assertEqual(transfer.destination_account, "destination")
        self.assertEqual(transfer.authority, "authority")
        self.assertEqual(transfer.amount_raw, 500)
        self.assertIsNone(transfer.mint)
        self.assertEqual(transfer.execution_status, "EXECUTED")
        self.assertEqual(transfer.source_format, "compiled")

    def test_decodes_compiled_transfer_checked(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": SPL_TOKEN_PROGRAM_ID,
            "accounts": [0, 3, 1, 2],
            "data": _transfer(12, 1234567, 6),
        }]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].instruction_type, "TRANSFER_CHECKED")
        self.assertEqual(result[0].mint, "mint")
        self.assertEqual(result[0].amount_raw, 1234567)
        self.assertEqual(result[0].decimals, 6)

    def test_token_2022_uses_the_same_base_transfer_layout(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": TOKEN_2022_PROGRAM_ID,
            "accounts": [0, 3, 1, 2],
            "data": _transfer(12, 77, 2),
        }]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].program_name, "Token-2022")
        self.assertEqual(result[0].amount_raw, 77)
        self.assertEqual(result[0].decimals, 2)

    def test_decodes_json_parsed_transfer(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": SPL_TOKEN_PROGRAM_ID,
            "parsed": {
                "type": "transfer",
                "info": {
                    "source": "source",
                    "destination": "destination",
                    "authority": "authority",
                    "amount": "123",
                },
            },
        }]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].instruction_type, "TRANSFER")
        self.assertEqual(result[0].amount_raw, 123)
        self.assertIsNone(result[0].decimals)

    def test_decodes_json_parsed_transfer_checked(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": SPL_TOKEN_PROGRAM_ID,
            "parsed": {
                "type": "transferChecked",
                "info": {
                    "source": "source",
                    "destination": "destination",
                    "authority": "authority",
                    "mint": "mint",
                    "tokenAmount": {"amount": "9001", "decimals": 6, "uiAmount": 0.009001},
                },
            },
        }]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].amount_raw, 9001)
        self.assertEqual(result[0].decimals, 6)
        self.assertEqual(result[0].source_format, "jsonParsed")

    def test_preserves_parsed_checked_variant_without_optional_mint_metadata(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": SPL_TOKEN_PROGRAM_ID,
            "parsed": {
                "type": "transferChecked",
                "info": {
                    "source": "source",
                    "destination": "destination",
                    "tokenAmount": {"amount": "55"},
                },
            },
        }]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].instruction_type, "TRANSFER_CHECKED")
        self.assertEqual(result[0].amount_raw, 55)
        self.assertIsNone(result[0].mint)
        self.assertIsNone(result[0].decimals)

    def test_resolves_loaded_addresses_for_compiled_cpi(self):
        result = decode_solana_token_transfers(_tx(
            [{"programId": "router", "accounts": [], "data": "1"}],
            keys=["static-0", "static-1", "static-2", "static-3"],
            meta={
                "err": None,
                "loadedAddresses": {
                    "writable": ["loaded-source", "loaded-destination"],
                    "readonly": ["loaded-authority"],
                },
                "innerInstructions": [{
                    "index": 0,
                    "instructions": [{
                        "programId": SPL_TOKEN_PROGRAM_ID,
                        "accounts": [4, 5, 6],
                        "data": _transfer(3, 42),
                        "stackHeight": 2,
                    }],
                }],
            },
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_account, "loaded-source")
        self.assertEqual(result[0].destination_account, "loaded-destination")
        self.assertEqual(result[0].authority, "loaded-authority")
        self.assertEqual(result[0].instruction_index, 0)
        self.assertEqual(result[0].inner_instruction_index, 0)
        self.assertEqual(result[0].cpi_path, (0,))

    def test_derives_nested_cpi_path(self):
        inner = [
            {"programId": "router", "accounts": [], "data": "1", "stackHeight": 2},
            {
                "programId": SPL_TOKEN_PROGRAM_ID,
                "accounts": [0, 1, 2],
                "data": _transfer(3, 8),
                "stackHeight": 3,
            },
        ]
        result = decode_solana_token_transfers(_tx(
            [{"programId": "router", "accounts": [], "data": "1"}],
            meta={"err": None, "innerInstructions": [{"index": 0, "instructions": inner}]},
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].cpi_path, (0, 0))
        self.assertEqual(result[0].stack_height, 3)

    def test_uses_flat_position_without_stack_height(self):
        result = decode_solana_token_transfers(_tx(
            [{"programId": "router", "accounts": [], "data": "1"}],
            meta={"err": None, "innerInstructions": [{
                "index": 0,
                "instructions": [{
                    "programId": SPL_TOKEN_PROGRAM_ID,
                    "accounts": [0, 1, 2],
                    "data": _transfer(3, 8),
                }],
            }]},
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].cpi_path, (0,))
        self.assertIsNone(result[0].stack_height)

    def test_marks_failed_transaction_transfers_as_failed(self):
        result = decode_solana_token_transfers(_tx(
            [{
                "programId": SPL_TOKEN_PROGRAM_ID,
                "accounts": [0, 1, 2],
                "data": _transfer(3, 8),
            }],
            meta={"err": {"InstructionError": [0, "Custom"]}},
        ))
        self.assertEqual(result[0].execution_status, "FAILED")

    def test_ignores_unrelated_token_instructions(self):
        result = decode_solana_token_transfers(_tx([{
            "programId": SPL_TOKEN_PROGRAM_ID,
            "accounts": [0, 1, 2],
            "data": _b58(bytes([9])),
        }]))
        self.assertEqual(result, [])

    def test_rejects_malformed_transfer_layout(self):
        with self.assertRaisesRegex(ValueError, "Transfer exige"):
            decode_solana_token_transfers(_tx([{
                "programId": SPL_TOKEN_PROGRAM_ID,
                "accounts": [0, 1, 2],
                "data": _b58(bytes([3, 1, 2])),
            }]))

    def test_rejects_duplicate_inner_instruction_groups(self):
        group = {"index": 0, "instructions": []}
        with self.assertRaisesRegex(ValueError, "inconsistente"):
            decode_solana_token_transfers(_tx(
                [{"programId": "router", "accounts": [], "data": "1"}],
                meta={"err": None, "innerInstructions": [group, group]},
            ))


if __name__ == "__main__":
    unittest.main()
