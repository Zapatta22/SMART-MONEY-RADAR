import unittest

from smart_money_radar.data_sources.damm_v2_analyzer import (
    _decode_base58,
    analyze_damm_v2_swap_events,
)
from smart_money_radar.data_sources.damm_v2_decoder import (
    EVENT_CPI_TAG,
    EVT_SWAP2_DISCRIMINATOR,
    METEORA_DAMM_V2_PROGRAM_ID,
    SWAP_DISCRIMINATOR,
    SWAP2_DISCRIMINATOR,
)


ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data):
    zeros = len(data) - len(data.lstrip(b"\x00"))
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = ALPHABET[remainder] + encoded
    return "1" * zeros + (encoded or ("" if zeros else "1"))


def u64(value):
    return value.to_bytes(8, "little")


def swap_data():
    return SWAP_DISCRIMINATOR + u64(100) + u64(90)


def swap2_data(amount_in=100, minimum_amount_out=90, mode=0):
    return SWAP2_DISCRIMINATOR + u64(amount_in) + u64(minimum_amount_out) + bytes((mode,))


def event_data():
    body = (
        bytes(32) + bytes((0, 0, 0))
        + u64(100) + u64(90) + bytes((0,))
        + u64(100) + u64(0) + u64(0) + u64(90) + bytes(16)
        + u64(0) + u64(0) + u64(0) + u64(0)
        + u64(0) + u64(0) + u64(0)
        + u64(1) + u64(2) + u64(3)
    )
    data = EVENT_CPI_TAG + EVT_SWAP2_DISCRIMINATOR + body
    assert len(data) == 196
    return data


def instruction(data, height=None):
    result = {
        "programId": METEORA_DAMM_V2_PROGRAM_ID,
        "accounts": [0],
        "data": b58encode(data),
    }
    if height is not None:
        result["stackHeight"] = height
    return result


def transaction(outer, inner):
    return {
        "result": {
            "transaction": {
                "message": {
                    "accountKeys": ["payer"],
                    "instructions": outer,
                }
            },
            "meta": {
                "err": None,
                "innerInstructions": [
                    {"index": index, "instructions": instructions}
                    for index, instructions in inner.items()
                ],
            },
        }
    }


class DammV2AnalyzerTests(unittest.TestCase):
    def test_base58_round_trip_preserves_leading_zero_bytes(self):
        original = b"\x00\x00SMR"
        self.assertEqual(_decode_base58(b58encode(original)), original)

    def test_rejects_mixed_account_key_formats(self):
        raw = transaction([], {})
        raw["result"]["transaction"]["message"]["accountKeys"] = [
            {"pubkey": "parsed-key", "signer": True},
            "compiled-key",
        ]
        with self.assertRaisesRegex(ValueError, "mistura formatos"):
            analyze_damm_v2_swap_events(raw)

    def test_missing_execution_status_fails_closed(self):
        raw = transaction([], {})
        del raw["result"]["meta"]["err"]
        with self.assertRaisesRegex(ValueError, "meta.err ausente"):
            analyze_damm_v2_swap_events(raw)

    def test_missing_outer_instruction_list_fails_closed(self):
        raw = transaction([], {})
        del raw["result"]["transaction"]["message"]["instructions"]
        with self.assertRaisesRegex(ValueError, "message.instructions ausente"):
            analyze_damm_v2_swap_events(raw)

    def test_missing_inner_instruction_metadata_fails_closed(self):
        raw = transaction([], {})
        del raw["result"]["meta"]["innerInstructions"]
        with self.assertRaisesRegex(ValueError, "innerInstructions ausente/nulo"):
            analyze_damm_v2_swap_events(raw)

    def test_null_inner_instruction_metadata_fails_closed(self):
        raw = transaction([], {})
        raw["result"]["meta"]["innerInstructions"] = None
        with self.assertRaisesRegex(ValueError, "innerInstructions ausente/nulo"):
            analyze_damm_v2_swap_events(raw)

    def test_resolves_damm_program_from_loaded_addresses(self):
        raw = transaction(
            [{"programId": "aggregator", "accounts": [], "data": b58encode(b"route")}],
            {0: [instruction(swap_data(), 2), instruction(event_data(), 3)]},
        )
        message = raw["result"]["transaction"]["message"]
        message["accountKeys"] = ["payer"]
        message["addressTableLookups"] = [{
            "accountKey": "lookup-table",
            "writableIndexes": [],
            "readonlyIndexes": [0],
        }]
        raw["result"]["meta"]["loadedAddresses"] = {
            "writable": [],
            "readonly": [METEORA_DAMM_V2_PROGRAM_ID],
        }
        for item in raw["result"]["meta"]["innerInstructions"][0]["instructions"]:
            item.pop("programId")
            item["programIdIndex"] = 1
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual([item.status for item in result], ["MATCHED"])

    def test_rejects_loaded_addresses_without_lookup_tables(self):
        raw = transaction([], {})
        raw["result"]["meta"]["loadedAddresses"] = {
            "writable": ["unexpected"],
            "readonly": [],
        }
        with self.assertRaisesRegex(ValueError, "sem addressTableLookups"):
            analyze_damm_v2_swap_events(raw)

    def test_rejects_loaded_address_count_mismatch(self):
        raw = transaction([], {})
        raw["result"]["transaction"]["message"]["addressTableLookups"] = [{
            "accountKey": "lookup-table",
            "writableIndexes": [0],
            "readonlyIndexes": [],
        }]
        raw["result"]["meta"]["loadedAddresses"] = {
            "writable": [],
            "readonly": [],
        }
        with self.assertRaisesRegex(ValueError, "não corresponde à quantidade"):
            analyze_damm_v2_swap_events(raw)

    def test_associates_event_cpi_with_outer_swap(self):
        raw = transaction(
            [instruction(swap_data())],
            {0: [instruction(event_data(), 2)]},
        )
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, "MATCHED")
        self.assertEqual(result[0].instruction_index, 0)
        self.assertIsNone(result[0].inner_instruction_index)
        self.assertEqual(result[0].event_inner_instruction_index, 0)
        self.assertEqual(result[0].event_stack_height, 2)

    def test_associates_event_with_nested_swap_under_aggregator(self):
        outer = [{"programId": "aggregator", "accounts": [], "data": b58encode(b"route")}]
        raw = transaction(
            outer,
            {0: [instruction(swap_data(), 2), instruction(event_data(), 3)]},
        )
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, "MATCHED")
        self.assertEqual(result[0].inner_instruction_index, 0)
        self.assertEqual(result[0].event_inner_instruction_index, 1)
        self.assertEqual(result[0].cpi_path, (0,))
        self.assertEqual(result[0].event_cpi_path, (0, 0))

    def test_keeps_sequential_swaps_and_events_as_two_operations(self):
        raw = transaction(
            [{"programId": "aggregator", "accounts": [], "data": b58encode(b"route")}],
            {0: [
                instruction(swap_data(), 2), instruction(event_data(), 3),
                instruction(swap_data(), 2), instruction(event_data(), 3),
            ]},
        )
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual([item.status for item in result], ["MATCHED", "MATCHED"])
        self.assertEqual(
            [item.inner_instruction_index for item in result], [0, 2]
        )
        self.assertEqual(
            [item.event_inner_instruction_index for item in result], [1, 3]
        )

    def test_keeps_two_sequential_swap2_calls_as_two_matched_operations(self):
        raw = transaction(
            [{"programId": "aggregator", "accounts": [], "data": b58encode(b"route")}],
            {0: [
                instruction(swap2_data(), 2), instruction(event_data(), 3),
                instruction(swap2_data(amount_in=200, minimum_amount_out=180), 2),
                instruction(event_data(), 3),
            ]},
        )
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual([item.status for item in result], ["MATCHED", "MATCHED"])
        self.assertEqual([item.inner_instruction_index for item in result], [0, 2])
        self.assertEqual([item.instruction.instruction_name for item in result], ["swap2", "swap2"])
        self.assertEqual([item.instruction.amount_0 for item in result], [100, 200])
        self.assertEqual([item.event_inner_instruction_index for item in result], [1, 3])

    def test_missing_stack_height_never_creates_association(self):
        raw = transaction(
            [{"programId": "aggregator", "accounts": [], "data": b58encode(b"route")}],
            {0: [instruction(swap_data()), instruction(event_data(), 3)]},
        )
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            {item.status for item in result},
            {"EVENT_MISSING", "UNMATCHED_EVENT"},
        )

    def test_event_before_swap_is_not_associated(self):
        raw = transaction(
            [{"programId": "aggregator", "accounts": [], "data": b58encode(b"route")}],
            {0: [instruction(event_data(), 3), instruction(swap_data(), 2)]},
        )
        result = analyze_damm_v2_swap_events(raw)
        self.assertEqual({item.status for item in result}, {"EVENT_MISSING", "UNMATCHED_EVENT"})

    def test_failed_transaction_has_no_operations(self):
        raw = transaction([instruction(swap_data())], {0: [instruction(event_data(), 2)]})
        raw["result"]["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        self.assertEqual(analyze_damm_v2_swap_events(raw), [])


if __name__ == "__main__":
    unittest.main()
