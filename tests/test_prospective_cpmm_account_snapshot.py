"""Synthetic fixtures for single-read prospective CPMM account verifier.

These are NOT observations of on-chain historical PoolState or AmmConfig.
"""
import base64
import hashlib
import json
import unittest
from datetime import datetime,timedelta,timezone

from smart_money_radar.domain.cpmm_binary_state import (
    POOL_LENGTH,CONFIG_LENGTH,POOL_DISCRIMINATOR,CONFIG_DISCRIMINATOR,_pubkey,
)
from smart_money_radar.services.prospective_cpmm_account_snapshot import (
    inspect_prospective_cpmm_response,SPL_TOKEN_PROGRAM,
)

NOW=datetime(2026,11,20,20,tzinfo=timezone.utc)
ALPHABET="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def from58(s):
    n=0
    for c in s:n=n*58+ALPHABET.index(c)
    return b"\\x00"*(len(s)-len(s.lstrip("1")))+n.to_bytes((n.bit_length()+7)//8,"big")

def key(i):
    return _pubkey(bytes([i])*32)

POOL=key(90)
CONFIG=key(91)
INPUT=key(92)
OUTPUT=key(93)
MINT_IN=key(94)
MINT_OUT=key(95)
AUTH=key(96)

def fixture(amount_in=1000,amount_out=3000,fee_in=12,fee_out=17):
    pool=bytearray(POOL_LENGTH)
    pool[:8]=POOL_DISCRIMINATOR
    for n,k in {0:CONFIG,2:INPUT,3:OUTPUT,5:MINT_IN,6:MINT_OUT,
                7:SPL_TOKEN_PROGRAM,8:SPL_TOKEN_PROGRAM}.items():
        pool[8+n*32:8+(n+1)*32]=from58(k)
    pool[331]=6
    pool[332]=9
    pool[341:349]=fee_in.to_bytes(8,"little")
    pool[349:357]=fee_out.to_bytes(8,"little")
    cfg=bytearray(CONFIG_LENGTH)
    cfg[:8]=CONFIG_DISCRIMINATOR
    cfg[12:20]=(2500).to_bytes(8,"little")
    cfg[108:116]=(500).to_bytes(8,"little")
    def vault(mint,amount):
        raw=bytearray(165)
        raw[:32]=from58(mint)
        raw[32:64]=from58(AUTH)
        raw[64:72]=amount.to_bytes(8,"little")
        raw[108]=1
        return bytes(raw)
    binary=[bytes(pool),bytes(cfg),vault(MINT_IN,amount_in),
            vault(MINT_OUT,amount_out)]
    def entry(raw,owner):
        return dict(owner=owner,executable=False,
                    data=[base64.b64encode(raw).decode(),"base64"],lamports=1000)
    payload={"jsonrpc":"2.0","id":1,"result":{
        "context":{"slot":471039777},
        "value":[entry(binary[0],"CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"),
                 entry(binary[1],"CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"),
                 entry(binary[2],SPL_TOKEN_PROGRAM),
                 entry(binary[3],SPL_TOKEN_PROGRAM)]}}
    return payload

def probe(payload=None,**overrides):
    args=dict(response_raw=json.dumps(fixture() if payload is None else payload).encode(),
              request_raw=json.dumps({"jsonrpc":"2.0","id":1,"method":"getMultipleAccounts","params":[[POOL,CONFIG,INPUT,OUTPUT],{"encoding":"base64","commitment":"finalized"}]}).encode(),
              source_id="test-only",endpoint="https://example.invalid/rpc",
              observed_at=NOW,available_at=NOW+timedelta(milliseconds=5),
              pool=POOL,amm_config=CONFIG,input_vault=INPUT,output_vault=OUTPUT,
              input_mint=MINT_IN,output_mint=MINT_OUT,authority=AUTH,
              input_token_program=SPL_TOKEN_PROGRAM,
              output_token_program=SPL_TOKEN_PROGRAM,
              original_swap_slot=471039497)
    args.update(overrides)
    return inspect_prospective_cpmm_response(**args)

class ProspectCpmmTests(unittest.TestCase):
    def test_existing_pubkey_decoder_handles_zero_prefix(self):
        self.assertEqual(_pubkey(bytes(32)),"1"*32)
        self.assertEqual(from58(_pubkey(bytes([0])+bytes([5])*31)),bytes([0])+bytes([5])*31)

    def test_valid_synthetic_snapshot_is_never_historical(self):
        q=probe()
        self.assertEqual(q.status,"RPC_DECLARED_PROSPECTIVE_ONLY")
        self.assertEqual(q.effective_input_raw,988)
        self.assertEqual(q.effective_output_raw,2983)
        self.assertEqual(q.declared_trade_fee_rate,2500)
        self.assertEqual(q.declared_creator_fee_rate,500)
        self.assertEqual(q.slot,471039777)
        self.assertFalse(q.pre_swap_state_of_original_tx)
        self.assertFalse(q.provider_independently_authenticated)
        self.assertFalse(q.operational_authorized)

    def test_same_raw_same_result(self):
        self.assertEqual(probe(),probe())

    def test_other_pool_rejected(self):
        q=probe(pool=key(111))
        self.assertEqual(q.status,"UNKNOWN")
        self.assertIn("incomplete_or_conflicted_snapshot",q.reasons)

    def test_wrong_config_binary_address_rejected(self):
        x=fixture()
        raw=bytearray(base64.b64decode(x["result"]["value"][0]["data"][0]))
        raw[8:40]=from58(key(113))
        x["result"]["value"][0]["data"][0]=base64.b64encode(raw).decode()
        self.assertEqual(probe(x).status,"UNKNOWN")

    def test_missing_pool_or_vault_rejected(self):
        x=fixture()
        x["result"]["value"][2]=None
        self.assertEqual(probe(x).status,"UNKNOWN")

    def test_owner_mismatch_rejected(self):
        x=fixture()
        x["result"]["value"][0]["owner"]=SPL_TOKEN_PROGRAM
        self.assertEqual(probe(x).status,"UNKNOWN")

    def test_vault_mint_mismatch_rejected(self):
        x=fixture()
        raw=bytearray(base64.b64decode(x["result"]["value"][2]["data"][0]))
        raw[:32]=from58(MINT_OUT)
        x["result"]["value"][2]["data"][0]=base64.b64encode(raw).decode()
        self.assertEqual(probe(x).status,"UNKNOWN")

    def test_vault_authority_mismatch_rejected(self):
        x=fixture()
        raw=bytearray(base64.b64decode(x["result"]["value"][3]["data"][0]))
        raw[32:64]=from58(key(125))
        x["result"]["value"][3]["data"][0]=base64.b64encode(raw).decode()
        self.assertEqual(probe(x).status,"UNKNOWN")

    def test_accumulated_fees_exceed_vault_rejected(self):
        self.assertEqual(probe(fixture(fee_in=2000)).status,"UNKNOWN")

    def test_historical_context_original_slot_rejected(self):
        x=fixture()
        x["result"]["context"]["slot"]=471039497
        self.assertEqual(probe(x).status,"UNKNOWN")

    def test_rpc_error_rejected(self):
        self.assertEqual(probe({"error":{"code":-32000}}).status,"UNKNOWN")

    def test_invalid_json_type_rejected(self):
        self.assertEqual(probe([]).status,"UNKNOWN")

    def test_temporal_order_violations_rejected(self):
        with self.assertRaises(ValueError):
            probe(available_at=NOW-timedelta(seconds=1))

    def test_caller_cannot_claim_execution_from_snapshot(self):
        q=probe()
        self.assertFalse(q.executable_quote_proven)
        self.assertFalse(q.chronological_instruction_order_proven)

if __name__=="__main__":unittest.main()
