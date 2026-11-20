"""No network: deterministic heartbeat, disconnect, retry and RAW recovery tests."""
import json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_ws_resilience import (
    WsResiliencePolicy,disconnect_record,classify_ws_failure,
    reconnection_is_new_observation,
)
from smart_money_radar.services.cpmm_ws_recovery import BoundedCpmmRecovery

ACCOUNTS=("pool111","config111","high111","wsol111")
NOW=datetime(2026,11,20,22,tzinfo=timezone.utc)


class ConnectionClosedError(Exception):
    pass


class PingTimeoutError(TimeoutError):
    pass


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.path=Path(self.t.name)/"s.sqlite"
        self.store=SQLiteGeyserRawStore(self.path)
        self.policy=WsResiliencePolicy()
        self.recovery=BoundedCpmmRecovery(self.store,source_id="test-solana-ws",
            accounts=ACCOUNTS,policy=self.policy)
        self.s=self.recovery.new_connection(new_session_id="conn1")
    def tearDown(self):
        self.recovery.finalize("test_cleanup")
        self.store.close()
        self.t.cleanup()
    def failure(self,exc=None,phase="receive"):
        return disconnect_record(session_id=self.s.session_id,
                   exc=exc or ConnectionClosedError("closed abnormally"),
                   phase=phase,frames=self.s.next_local_sequence,when=NOW)

    def test_closed_error_does_not_prove_provider_fault(self):
        x=self.failure()
        self.assertEqual(x.failure,"CLOSED")
        self.assertEqual(x.error_type,"ConnectionClosedError")
        self.assertEqual(x.coverage,"UNKNOWN")
        self.assertFalse(x.checkpoint_proves_ledger_coverage)

    def test_ping_timeout_classified(self):
        x=self.failure(TimeoutError("no pong"),phase="ping")
        self.assertEqual(x.failure,"PING_TIMEOUT")

    def test_silent_connection_is_not_automatically_disconnected(self):
        self.assertEqual(classify_ws_failure(None,phase="read"),"NORMAL_END")
        self.assertEqual(classify_ws_failure(TimeoutError("idle read"),phase="read"),"IDLE_TIMEOUT")
        self.assertEqual(self.s.next_local_sequence,0)

    def test_during_baseline_disconnect_and_new_domain(self):
        f=self.failure(TimeoutError("lost while baseline"),phase="baseline")
        self.recovery.note_failure(f)
        new=self.recovery.new_connection(recovered_from=f,new_session_id="conn2")
        self.assertEqual(new.session_id,"conn2")
        self.assertEqual(self.recovery.report()["coverage"],"UNKNOWN")
        self.assertEqual(f.failure,"BASELINE_FAILED")

    def test_after_baseline_disconnect_does_not_reuse_old_checkpoint(self):
        self.s._record(b'{"reply":1}',"solana_ws_subscription_ack")
        f=self.failure()
        self.recovery.note_failure(f)
        z=self.recovery.new_connection(recovered_from=f,new_session_id="conn2")
        self.assertEqual(z.next_local_sequence,0)
        self.assertFalse(self.recovery.recovery_ready())
        self.assertEqual(self.store.verify_wire_session("test-solana-ws","conn1","conn1")["verified_frames"],1)

    def test_subscription_failure_keeps_gap(self):
        f=self.failure(ValueError("bad ack"),phase="subscribe")
        self.recovery.note_failure(f)
        new=self.recovery.new_connection(recovered_from=f,new_session_id="conn2")
        self.assertEqual(len(new.subscription_accounts),0)
        self.assertIn("connection_lost",self.s.gaps)
        self.assertEqual(self.recovery.report()["coverage"],"UNKNOWN")

    def test_reconnect_budget_limited(self):
        f=self.failure()
        self.recovery.note_failure(f)
        z=self.recovery.new_connection(recovered_from=f,new_session_id="conn2")
        z.mark_disconnect()
        g=disconnect_record(session_id=z.session_id,exc=ConnectionClosedError(),
                            phase="receive",frames=0,when=NOW)
        self.recovery.note_failure(g)
        with self.assertRaisesRegex(ValueError,"budget"):
            self.recovery.new_connection(recovered_from=g,new_session_id="conn3")

    def test_deterministic_bounded_backoff_and_jitter(self):
        one=self.policy.backoff(1,seed="unchanged-raw")
        self.assertEqual(one,self.policy.backoff(1,seed="unchanged-raw"))
        self.assertGreaterEqual(one,.85)
        self.assertLessEqual(one,1.15)
        with self.assertRaises(ValueError):
            self.policy.backoff(2,seed="unchanged-raw")

    def test_duplicate_data_across_connections_is_not_stream_continuity(self):
        self.s._record(b'{"observed":"x"}',"solana_ws_jsonrpc")
        f=self.failure()
        self.recovery.note_failure(f)
        x=self.recovery.new_connection(recovered_from=f,new_session_id="conn2")
        x._record(b'{"observed":"x"}',"solana_ws_jsonrpc")
        self.assertEqual(self.store.verify_wire_session("test-solana-ws","conn2","conn2")["verified_frames"],1)
        self.assertFalse(self.recovery.report()["account_stream_continuous"])

    def test_raw_hash_conflict_in_same_sequence_is_rejected(self):
        self.s._record(b'{"a":1}',"solana_ws_jsonrpc")
        receipt=self.store.append_wire_frame(source_id="test-solana-ws",
                stream_id="conn1",ordering_domain_id="conn1",stream_sequence=0,
                payload=b'{"a":2}',frame_kind="solana_ws_jsonrpc")
        self.assertNotEqual(receipt.status,"accepted")
        self.assertNotEqual(receipt.status,"duplicate")
        # A conflicting sequence taints the stream; verification must fail closed.
        with self.assertRaisesRegex(ValueError,"interrompido|anomalia"):
            self.store.verify_wire_session("test-solana-ws","conn1","conn1")
        self.assertEqual(self.store.integrity_check(),["ok"])

    def test_sqlite_interruption_does_not_advance_frames(self):
        self.s._record(b'{"a":1}',"solana_ws_jsonrpc")
        n=self.store.verify_wire_session("test-solana-ws","conn1","conn1")
        self.assertEqual(n["verified_frames"],1)
        self.store.close()
        read=SQLiteGeyserRawStore(self.path)
        self.assertEqual(read.verify_wire_session("test-solana-ws","conn1","conn1")["verified_frames"],1)
        self.assertEqual(read.integrity_check(),["ok"])
        read.close()

    def test_regressive_slot_claim_cannot_become_continuity(self):
        self.s.last_slot[ACCOUNTS[0]]=100
        f=self.failure()
        self.recovery.note_failure(f)
        x=self.recovery.new_connection(recovered_from=f,new_session_id="conn2")
        self.assertNotIn(ACCOUNTS[0],x.last_slot)
        self.assertFalse(self.recovery.report()["checkpoint_proves_ledger_coverage"])

    def test_notification_during_sync_not_promoted(self):
        f=self.failure(TimeoutError(),phase="baseline")
        self.recovery.note_failure(f)
        self.assertFalse(self.recovery.report()["initial_session_baseline_verified"])
        self.assertFalse(self.recovery.report()["economic_execution_authorized"])

    def test_no_financial_execution_and_no_complete(self):
        self.assertFalse(self.recovery.report()["economic_execution_authorized"])
        self.assertEqual(self.recovery.report()["coverage"],"UNKNOWN")

if __name__=="__main__":unittest.main()
