import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from smart_money_radar.data_sources.geyser_proto_adapter import _base58_encode
from smart_money_radar.data_sources.raydium_cpmm_launch import (
    INITIALIZE_DISCRIMINATOR,
    deduplicate_cpmm_pool_initializations,
    detect_cpmm_pool_initializations,
)


class RaydiumCpmmLaunchTests(unittest.TestCase):
    fixture = Path(__file__).resolve().parents[1] / "data/fixtures/mainnet/raydium-cpmm-launch"

    def raw(self):
        return json.loads(self.fixture.joinpath("response.json").read_bytes())

    def test_detects_a_finalized_mainnet_initialization_and_account_roles(self):
        request = self.fixture.joinpath("request.json").read_bytes()
        response = self.fixture.joinpath("response.json").read_bytes()
        self.assertEqual(hashlib.sha256(request).hexdigest(), "b30b0f653307cea5c4ddf5f23c3b0f35a6f5b292f89eea3904f7a7313142262c")
        self.assertEqual(hashlib.sha256(response).hexdigest(), "95498b19f9ecfec42b412bc9ac1479a15fecfa474b294e25bdc2f5e52133ebd4")
        transaction = json.loads(response)
        event, = detect_cpmm_pool_initializations(transaction)
        self.assertEqual(INITIALIZE_DISCRIMINATOR.hex(), "afaf6d1f0d989bed")
        self.assertEqual(event.signature, json.loads(request)["params"][0])
        self.assertEqual(json.loads(request)["params"][1]["commitment"], "finalized")
        self.assertEqual((event.slot, event.instruction_index, event.cpi_path), (471578450, 4, ()))
        self.assertEqual(event.pool, "BrRNVcivKs4kRqqbmksT6zXE6o7SAmWHYjrWgFn9JVNC")
        self.assertEqual(event.token_0_mint, "So11111111111111111111111111111111111111112")
        self.assertEqual(event.token_1_mint, "DdapLq3YrPhEYajEXne8KHm9DHdgBayfgaL12VudYpY9")
        self.assertEqual(event.token_0_vault, "2aqkRk7W7jJUzETtgm9JcAKDctWBJ3UEmYngsNN1HDVo")
        self.assertEqual(event.token_1_vault, "J2Y4qX99Lr2wsuGzqvHwFwbboxo333NdET1Ng3C4M1Ck")
        self.assertEqual((event.requested_amount_0_raw, event.requested_amount_1_raw), (300_000_000, 900_000_000_000_000))

    def test_rejects_failed_or_incomplete_transaction(self):
        for field in ("err", "innerInstructions"):
            with self.subTest(field=field):
                transaction = self.raw()
                transaction["result"]["meta"].pop(field)
                self.assertEqual(detect_cpmm_pool_initializations(transaction), ())
        transaction = self.raw()
        transaction["result"]["meta"]["err"] = {"InstructionError": [4, "Custom"]}
        self.assertEqual(detect_cpmm_pool_initializations(transaction), ())

    def test_rejects_malformed_initialization_roles_and_args(self):
        for field in ("authority", "mints", "data"):
            with self.subTest(field=field):
                transaction = self.raw()
                init = transaction["result"]["transaction"]["message"]["instructions"][4]
                if field == "authority":
                    init["accounts"][2] = init["accounts"][3]
                elif field == "mints":
                    init["accounts"][4], init["accounts"][5] = init["accounts"][5], init["accounts"][4]
                else:
                    init["data"] = _base58_encode(INITIALIZE_DISCRIMINATOR, field="fixture")
                self.assertEqual(detect_cpmm_pool_initializations(transaction), ())

    def test_accepts_only_demonstrable_cpi_path(self):
        transaction = self.raw()
        payload = transaction["result"]
        instructions = payload["transaction"]["message"]["instructions"]
        cpi = {**instructions.pop(4), "stackHeight": 2}
        payload["meta"]["innerInstructions"] = [{"index": 0, "instructions": [cpi]}]
        event, = detect_cpmm_pool_initializations(transaction)
        self.assertEqual((event.instruction_index, event.inner_instruction_index, event.cpi_path), (0, 0, (0,)))
        cpi.pop("stackHeight")
        self.assertEqual(detect_cpmm_pool_initializations(transaction), ())

    def test_does_not_treat_swap_or_deposit_instructions_as_creation(self):
        real_swap = self.fixture.parent / "anonymized/raydium-cpmm-route-multivenue.json"
        self.assertEqual(detect_cpmm_pool_initializations(json.loads(real_swap.read_bytes())), ())
        transaction = self.raw()
        init = transaction["result"]["transaction"]["message"]["instructions"][4]
        init["data"] = _base58_encode(hashlib.sha256(b"global:deposit").digest()[:8] + bytes(24), field="fixture")
        self.assertEqual(detect_cpmm_pool_initializations(transaction), ())

    def test_replay_deduplicates_and_conflicting_pool_identities_are_withheld(self):
        observation, = detect_cpmm_pool_initializations(self.raw())
        self.assertEqual(deduplicate_cpmm_pool_initializations([observation, observation]), (observation,))
        alternate = replace(observation, instruction_index=8)
        self.assertEqual(deduplicate_cpmm_pool_initializations([observation, alternate, observation]), ())


if __name__ == "__main__":
    unittest.main()
