"""No simulated notifications are claimed as real. Unit vectors are synthetic."""
import base64,json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_public_ws_capture import PublicCpmmWsSession

ACCOUNTS=("pool111","config111","high111","wsol111")

def frame(*,subscription=17,slot=150,data=b"payload",owner="TokenProgram"):
    return json.dumps({"jsonrpc":"2.0","method":"accountNotification",
        "params":{"result":{"context":{"slot":slot},"value":{
            "data":[base64.b64encode(data).decode(),"base64"],"owner":owner,
            "lamports":2039280,"executable":False,"rentEpoch":0}},
            "subscription":subscription}},sort_keys=True).encode()

class PublicWsCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=SQLiteGeyserRawStore(Path(self.temp.name)/"raw.db")
        self.session=PublicCpmmWsSession(self.db,source_id="test-solana-ws",
             session_id="session1",accounts=ACCOUNTS)
        self.session.start()
        self.session.register_subscription(17,ACCOUNTS[0])
        self.now=datetime(2026,11,20,21,tzinfo=timezone.utc)

    def tearDown(self):
        if self.session.active:self.session.finish("test-ended")
        self.db.close()
        self.temp.cleanup()

    def test_first_notification_is_observed_without_verified_baseline(self):
        obs=self.session.process_frame(frame(),received_at=self.now)
        self.assertEqual(obs.status,"OBSERVED")
        self.assertIsNone(obs.txn_signature)
        self.assertIsNone(obs.write_version)
        self.assertFalse(obs.ordered_across_streams)
        self.assertFalse(obs.finalized_attested)
        self.assertFalse(obs.operational_authorized)
        self.assertFalse(self.session.report()["baseline_validated"])
        self.assertEqual(self.session.report()["coverage"],"UNKNOWN")

    def test_repeated_frame_preserved_but_not_proof_of_write(self):
        raw=frame()
        a=self.session.process_frame(raw,received_at=self.now)
        b=self.session.process_frame(raw,received_at=self.now+timedelta(seconds=1))
        self.assertEqual(a.raw_sha256,b.raw_sha256)
        self.assertEqual(self.session.next_local_sequence,2)
        self.assertFalse(self.session.report()["account_write_order_verified"])

    def test_conflicting_same_slot_account_state(self):
        self.session.process_frame(frame(),received_at=self.now)
        x=self.session.process_frame(frame(data=b"changed"),received_at=self.now)
        self.assertEqual(x.status,"CONFLICT")
        self.assertTrue(any("content_conflict" in g for g in self.session.gaps))

    def test_regressive_slot(self):
        self.session.process_frame(frame(slot=152),received_at=self.now)
        x=self.session.process_frame(frame(slot=151),received_at=self.now)
        self.assertEqual(x.status,"CONFLICT")

    def test_unknown_account_subscription_cannot_be_observed(self):
        self.assertIsNone(self.session.process_frame(frame(subscription=99),received_at=self.now))
        self.assertIn("malformed_or_unmatched_ws_frame",self.session.gaps)

    def test_missing_baseline_preserves_unknown(self):
        self.assertFalse(self.session.baseline_validated)
        self.assertIn("subscription_start_without_verified_baseline",self.session.gaps)

    def test_reconnect_clears_subscription_and_marks_gap(self):
        self.session.mark_disconnect()
        self.assertEqual(self.session.reconnects,1)
        self.assertEqual(self.session.subscription_accounts,{})
        self.assertIsNone(self.session.process_frame(frame(),received_at=self.now))
        self.assertEqual(self.session.report()["coverage"],"UNKNOWN")

    def test_malformed_raw_kept_without_observation(self):
        self.assertIsNone(self.session.process_frame(b"{invalid",received_at=self.now))
        self.assertEqual(self.session.report()["notifications_received"],0)
        self.assertEqual(self.session.next_local_sequence,1)

    def test_integrity_and_checkpoint_does_not_prove_network_coverage(self):
        self.session.process_frame(frame(),received_at=self.now)
        self.assertEqual(self.session.finish("short-session"),1)
        v=self.db.verify_wire_session("test-solana-ws","session1","session1")
        self.assertEqual(v["verified_frames"],1)
        self.assertEqual(self.db.integrity_check(),["ok"])
        self.assertFalse(self.session.report()["baseline_validated"])

    def test_wrong_timestamp_rejected_before_journal_write(self):
        with self.assertRaises(ValueError):
            self.session.process_frame(frame(),received_at=datetime(2026,11,20))
        self.assertEqual(self.session.next_local_sequence,0)

    def test_four_unique_accounts_only(self):
        with self.assertRaises(ValueError):
            PublicCpmmWsSession(self.db,source_id="s",session_id="t",
                accounts=("a","a","b","c"))

    def test_ambiguous_subscription_remapping_rejected(self):
        with self.assertRaises(ValueError):
            self.session.register_subscription(17,ACCOUNTS[1])
        with self.assertRaises(ValueError):
            self.session.register_subscription(18,ACCOUNTS[0])

    def test_unsequenced_cross_stream_claim_not_established(self):
        self.session.process_frame(frame(),received_at=self.now)
        self.assertEqual(self.session.report()["account_write_order_verified"],False)
        self.assertEqual(self.session.report()["economic_execution_authorized"],False)

if __name__=="__main__":unittest.main()
