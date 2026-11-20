import base64
import unittest
from dataclasses import replace
from decimal import Decimal

from smart_money_radar.data_sources.geyser_proto_adapter import _base58_encode
from smart_money_radar.data_sources.raydium_cpmm_decoder import RAYDIUM_CPMM_PROGRAM_ID
from smart_money_radar.data_sources.raydium_cpmm_quote_snapshot import (
    decode_cpmm_snapshot, model_cpmm_quotes,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID, _decode_base58,
)


def _key(index):
    return bytes([index]) * 32


def _label(index):
    return _base58_encode(_key(index), field="fixture")


def fixture(*, creator_enabled=False):
    state = bytearray(637)
    state[:8] = bytes.fromhex("f7ede3f5d7c3de46")
    for offset, key in ((8, 2), (72, 3), (104, 4), (168, 5), (200, 6)):
        state[offset:offset + 32] = _key(key)
    for offset in (232, 264):
        state[offset:offset + 32] = _decode_base58(SPL_TOKEN_PROGRAM_ID)
    state[331:333] = bytes((3, 2))
    state[341:349] = (50).to_bytes(8, "little")
    state[357:365] = (20).to_bytes(8, "little")
    state[405:413] = (5).to_bytes(8, "little")
    state[373:381] = (100).to_bytes(8, "little")
    state[390] = int(creator_enabled)
    configuration = bytearray(236)
    configuration[:8] = bytes.fromhex("daf42168cbcb2b6f")
    configuration[12:20] = (3000).to_bytes(8, "little")

    def account(data, owner):
        return {"owner": owner, "executable": False,
                "data": [base64.b64encode(data).decode(), "base64"]}

    accounts = [account(state, RAYDIUM_CPMM_PROGRAM_ID), account(configuration, RAYDIUM_CPMM_PROGRAM_ID)]
    for index, amount in ((5, 1_000_070), (6, 2_000_005)):
        vault = bytearray(165)
        vault[:32] = _key(index)
        vault[64:72] = amount.to_bytes(8, "little")
        vault[108] = 1
        accounts.append(account(vault, SPL_TOKEN_PROGRAM_ID))
    request = {"id": 5, "method": "getMultipleAccounts",
               "params": [[_label(i) for i in range(1, 5)], {"commitment": "finalized", "encoding": "base64"}]}
    return request, {"id": 5, "result": {"context": {"slot": 7}, "value": accounts}}


class CpmmQuoteTests(unittest.TestCase):
    def test_model_binds_reserves_fees_and_exact_size(self):
        request, response = fixture()
        snapshot = decode_cpmm_snapshot(request, response, base_mint=_label(5), quote_mint=_label(6), block_time=101)
        self.assertEqual((snapshot.base_reserve, snapshot.quote_reserve), (1_000_000, 2_000_000))
        prices = model_cpmm_quotes(snapshot, base_size_raw=10_000)
        self.assertEqual(prices["base_size"], Decimal(10))
        self.assertEqual(prices["bid"], Decimal("19.743"))
        self.assertEqual(prices["ask"], Decimal("20.264"))
        with self.assertRaisesRegex(ValueError, "profundidade"):
            model_cpmm_quotes(replace(snapshot, base_reserve=10), base_size_raw=10)

    def test_rejects_wrong_vault_and_unmodeled_fee_configuration(self):
        request, response = fixture()
        request["params"][0][2] = _label(7)
        with self.assertRaisesRegex(ValueError, "vaults não pertencem"):
            decode_cpmm_snapshot(request, response, base_mint=_label(5), quote_mint=_label(6), block_time=101)
        with self.assertRaisesRegex(ValueError, "taxa do criador"):
            decode_cpmm_snapshot(*fixture(creator_enabled=True), base_mint=_label(5), quote_mint=_label(6), block_time=101)
