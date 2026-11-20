"""Adversarial synchronization tests on the existing four-account Solana RPC fixture."""
import base64, hashlib, json, tempfile, unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession
from smart_money_radar.services.cpmm_ws_baseline_bridge import inspect_contemporaneous_baseline

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
OLD=ROOT/"prospective-slot-471860762"
BASE_ACCOUNTS=("CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu",
 "D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2",
 "C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU",
 "8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG")
NOW=datetime(2026,11,20,21,tzinfo=timezone.utc)
OWNER="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

class BaselineBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=SQLiteGeyserRawStore(Path(self.temp.name)/"raw.sqlite")
        self.session=PublicCpmmWsSession(self.db,source_id="test-ws",
                       session_id="s1",accounts=BASE_ACCOUNTS)
        self.session.start()
        self.session.register_subscription(777,BASE_ACCOUNTS[2])
        self.request=(OLD/"request.raw.json").read_bytes()
        self.response=(OLD/"response.raw.json").read_bytes()

    def tearDown(self):
        if self.session.active:self.session.finish("tests")
        self.db.close()
        self.temp.cleanup()

    def inspect(self,**changes):
        opts=dict(session=self.session,request_raw=self.request,response_raw=self.response,
                  requested_at=NOW,available_at=NOW+timedelta(seconds=2),
                  cutoff=NOW+timedelta(minutes=2),
                  endpoint="https://api.mainnet-beta.solana.com",
                  original_swap_slot=471039497,
                  authority="GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL",
                  input_mint="7ymF66Z6VhgNiwadtVhjTtT6U7iQRpSxeiRrhfufhigh",
                  output_mint="So11111111111111111111111111111111111111112",
                  input_token_program=OWNER,output_token_program=OWNER,
                  notifications=())
        opts.update(changes)
        return inspect_contemporaneous_baseline(**opts)

    def notification(self,slot:int,*,data:bytes|None=None,received_at:datetime|None=None):
        original=json.loads(self.response)["result"]["value"][2]
        encoded=original["data"][0] if data is None else base64.b64encode(data).decode()
        packet=json.dumps({"jsonrpc":"2.0","method":"accountNotification",
            "params":{"subscription":777,
              "result":{"context":{"slot":slot},"value":{
                **original,"data":[encoded,"base64"]}}}},sort_keys=True).encode()
        observation=self.session.process_frame(packet,received_at=received_at or NOW)
        self.assertIsNotNone(observation)
        return observation,packet

    def test_real_existing_snapshot_decodes_as_strict_baseline(self):
        x=self.inspect()
        self.assertTrue(x.baseline_validated_as_snapshot,x.reasons)
        self.assertEqual(x.baseline_slot,471860762)
        self.assertEqual(x.coverage,"PARTIAL")
        self.assertEqual(x.baseline_response_sha256,hashlib.sha256(self.response).hexdigest())
        self.assertFalse(x.continuous_updates_proven)
        self.assertFalse(x.economic_execution_authorized)

    def test_same_slot_identical_binary_is_not_global_order_proof(self):
        t=self.notification(471860762)
        x=self.inspect(notifications=(t,))
        self.assertEqual(x.account_observations[0].relationship,"SAME_SLOT_STATE_MATCH")
        self.assertFalse(x.global_order_proven)
        self.assertFalse(x.continuous_updates_proven)

    def test_same_slot_different_binary_is_conflict(self):
        t=self.notification(471860762,data=b"not-a-real-token-account")
        x=self.inspect(notifications=(t,))
        self.assertEqual(x.coverage,"CONFLICT")
        self.assertEqual(x.account_observations[0].relationship,"SAME_SLOT_STATE_CONFLICT")

    def test_pre_baseline_notification_not_discarded(self):
        t=self.notification(471860761)
        x=self.inspect(notifications=(t,))
        self.assertEqual(len(x.account_observations),1)
        self.assertEqual(x.account_observations[0].relationship,"BEFORE_BASELINE_SLOT")

    def test_post_baseline_observation_does_not_imply_stream_continuity(self):
        t=self.notification(471860763)
        x=self.inspect(notifications=(t,))
        self.assertEqual(x.account_observations[0].relationship,"AFTER_BASELINE_SLOT")
        self.assertEqual(x.coverage,"PARTIAL")

    def test_tampered_raw_rejected(self):
        t=self.notification(471860762)
        with self.assertRaisesRegex(ValueError,"integrity"):
            self.inspect(notifications=((t[0],t[1]+b" "),))

    def test_baseline_after_cutoff_rejected(self):
        with self.assertRaisesRegex(ValueError,"after cutoff"):
            self.inspect(cutoff=NOW+timedelta(seconds=1))

    def test_notification_after_cutoff_rejected(self):
        t=self.notification(471860762,received_at=NOW+timedelta(seconds=120))
        with self.assertRaisesRegex(ValueError,"after cutoff"):
            self.inspect(notifications=(t,),cutoff=NOW+timedelta(seconds=20))

    def test_rpc_wrong_scope_remains_unknown(self):
        request=json.loads(self.request)
        request["params"][0][0]="wrong-pool"
        x=self.inspect(request_raw=json.dumps(request).encode())
        self.assertFalse(x.baseline_validated_as_snapshot)
        self.assertEqual(x.coverage,"UNKNOWN")

    def test_rpc_invalid_account_is_unknown(self):
        response=json.loads(self.response)
        response["result"]["value"][0]=None
        x=self.inspect(response_raw=json.dumps(response).encode())
        self.assertEqual(x.coverage,"UNKNOWN")

    def test_reconnect_cannot_promote_coverage(self):
        self.session.mark_disconnect()
        x=self.inspect()
        self.assertFalse(x.continuous_updates_proven)
        self.assertEqual(x.coverage,"PARTIAL")

    def test_observation_missing_raw_rejected(self):
        t=self.notification(471860762)
        with self.assertRaises(TypeError):
            self.inspect(notifications=((t[0],None),))

    def test_no_signature_or_write_version_claims(self):
        t=self.notification(471860762)
        item=self.inspect(notifications=(t,)).account_observations[0]
        self.assertIsNone(item.transaction_signature)
        self.assertIsNone(item.write_version)
        self.assertFalse(item.economic_execution_authorized)

    def test_deterministic_fixture(self):
        self.assertEqual(self.inspect(),self.inspect())

if __name__=="__main__":unittest.main()
