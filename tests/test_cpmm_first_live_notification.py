"""Comando 24: only synthetic test frames, real RPC baseline fixture reused."""
import base64,hashlib,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession
from smart_money_radar.services.cpmm_ws_baseline_bridge import inspect_contemporaneous_baseline

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
F=ROOT/"live-cpmm-baseline-slot-471884671"
ORIGIN=json.loads((F/"manifest.json").read_bytes())
ACCOUNTS=tuple(ORIGIN["accounts"])
NOW=datetime(2026,11,20,21,30,tzinfo=timezone.utc)
AUTH="GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL"
TOKEN="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

class FirstNotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rpc_raw=(F/"baseline.response.raw.json").read_bytes()
        cls.rpc_request=(F/"baseline.request.raw.json").read_bytes()
        assert hashlib.sha256(cls.rpc_raw).hexdigest()==ORIGIN["baseline_response_sha256"]
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.store=SQLiteGeyserRawStore(Path(self.d.name)/"journal.db")
        self.ws=PublicCpmmWsSession(self.store,source_id="test",
                 session_id="session",accounts=ACCOUNTS)
        self.ws.start()
        for sub,key in enumerate(ACCOUNTS):
            self.ws.register_subscription(100+sub,key)
    def tearDown(self):
        if self.ws.active:self.ws.finish("test_completed")
        self.store.close()
        self.d.cleanup()
    def notify(self,index=2,slot=471884672,mutate=False,when=None):
        account=json.loads(self.rpc_raw)["result"]["value"][index]
        if mutate:
            raw=bytearray(base64.b64decode(account["data"][0]))
            raw[64]=(raw[64]+1)%256
            account["data"]=[base64.b64encode(raw).decode(),"base64"]
        packet=json.dumps({"jsonrpc":"2.0","method":"accountNotification",
            "params":{"subscription":100+index,"result":{
              "context":{"slot":slot},"value":account}}},sort_keys=True).encode()
        receipt=self.ws.process_frame(packet,received_at=when or NOW)
        return receipt,packet
    def compare(self,notifications=(),**kw):
        args=dict(session=self.ws,response_raw=self.rpc_raw,request_raw=self.rpc_request,
            requested_at=NOW-timedelta(seconds=4),
            available_at=NOW-timedelta(seconds=2),
            endpoint="https://api.mainnet-beta.solana.com",
            original_swap_slot=471039497,authority=AUTH,
            input_mint="7ymF66Z6VhgNiwadtVhjTtT6U7iQRpSxeiRrhfufhigh",
            output_mint="So11111111111111111111111111111111111111112",
            input_token_program=TOKEN,output_token_program=TOKEN,
            notifications=notifications,cutoff=NOW+timedelta(minutes=1))
        args.update(kw)
        return inspect_contemporaneous_baseline(**args)
    def test_real_baseline_fixture_no_notifications(self):
        audit=self.compare()
        self.assertTrue(audit.baseline_validated_as_snapshot)
        self.assertEqual(audit.baseline_slot,471884671)
        self.assertEqual(audit.account_observations,())
        self.assertEqual(audit.coverage,"PARTIAL")
        self.assertFalse(audit.economic_execution_authorized)
    def test_synthetic_post_baseline_notification_compares_without_order_promotion(self):
        o,raw=self.notify()
        a=self.compare(((o,raw),))
        self.assertEqual(a.account_observations[0].relationship,"AFTER_BASELINE_SLOT")
        self.assertFalse(a.global_order_proven)
        self.assertFalse(a.continuous_updates_proven)
    def test_same_slot_identical_content_is_not_write_proof(self):
        o,raw=self.notify(slot=471884671)
        a=self.compare(((o,raw),))
        self.assertEqual(a.account_observations[0].relationship,"SAME_SLOT_STATE_MATCH")
        self.assertIsNone(a.account_observations[0].transaction_signature)
    def test_same_slot_mismatch_conflict(self):
        o,raw=self.notify(slot=471884671,mutate=True)
        a=self.compare(((o,raw),))
        self.assertEqual(a.coverage,"CONFLICT")
    def test_pre_baseline_notification_retained(self):
        o,raw=self.notify(slot=471884670)
        self.assertEqual(self.compare(((o,raw),)).account_observations[0].relationship,
                         "BEFORE_BASELINE_SLOT")
    def test_wrong_account_subscription_rejected(self):
        o,raw=self.notify()
        frame=json.loads(raw)
        frame["params"]["subscription"]=999
        self.assertIsNone(self.ws.process_frame(json.dumps(frame).encode(),received_at=NOW))
    def test_modified_raw_hash_cannot_be_reconciled(self):
        o,raw=self.notify()
        with self.assertRaisesRegex(ValueError,"integrity"):
            self.compare(((o,raw+b" "),))
    def test_regressive_slot_detected(self):
        self.notify(slot=471884680)
        o,_=self.notify(slot=471884679)
        self.assertEqual(o.status,"CONFLICT")
    def test_duplicate_preserves_same_payload_sha_not_new_write(self):
        o1,r1=self.notify()
        o2,r2=self.notify()
        self.assertEqual(o1.raw_sha256,o2.raw_sha256)
        self.assertFalse(self.ws.report()["account_write_order_verified"])
    def test_reconnection_preserves_gap(self):
        self.ws.mark_disconnect()
        self.assertEqual(self.ws.report()["coverage"],"UNKNOWN")
        self.assertIn("connection_lost",self.ws.gaps)
    def test_baseline_missing_is_unknown(self):
        invalid=json.loads(self.rpc_raw)
        invalid["result"]["value"][0]=None
        a=self.compare(response_raw=json.dumps(invalid).encode())
        self.assertEqual(a.coverage,"UNKNOWN")
    def test_cutoff_blocks_future_notification(self):
        o,raw=self.notify(when=NOW+timedelta(minutes=3))
        with self.assertRaisesRegex(ValueError,"after cutoff"):
            self.compare(((o,raw),))
    def test_interrupted_journal_cannot_promote_coverage(self):
        self.notify()
        self.ws.finish("interrupted")
        proof=self.store.verify_wire_session("test","session","session")
        self.assertEqual(proof["verified_frames"],1)
        self.assertEqual(self.store.integrity_check(),["ok"])
        self.assertFalse(self.ws.report()["baseline_validated"])
    def test_replay_and_financial_locks(self):
        self.assertEqual(self.compare(),self.compare())
        self.assertFalse(self.ws.report()["economic_execution_authorized"])
if __name__=="__main__":unittest.main()
