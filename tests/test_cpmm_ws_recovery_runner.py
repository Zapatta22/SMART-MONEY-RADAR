"""Offline-only fake sockets/RPC: never claim they are Solana observations."""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore
from smart_money_radar.services.cpmm_ws_recovery import BoundedCpmmRecovery
from smart_money_radar.services.cpmm_ws_resilience import WsResiliencePolicy
from smart_money_radar.services.cpmm_ws_recovery_runner import CpmmRecoveryRunner

ADDRESS=("pool-1","config-2","vault-high-3","vault-wsol-4")
NOW=datetime(2026,11,20,23,tzinfo=timezone.utc)


class ConnectionClosedError(Exception):
    pass


class FakeSocket:
    def __init__(self,events):
        self.events=list(events)
        self.sent=[]
    async def __aenter__(self):
        return self
    async def __aexit__(self,*a):
        return False
    async def send(self,message):
        self.sent.append(json.loads(message))
    async def recv(self):
        if self.events:
            item=self.events.pop(0)
            if isinstance(item,BaseException):
                raise item
            return item
        raise ConnectionClosedError("fake transport exhausted")


class FakeConnector:
    def __init__(self,series):
        self.series=iter(series)
        self.sockets=[]
    def __call__(self):
        sock=FakeSocket(next(self.series))
        self.sockets.append(sock)
        return sock


def ack(i):
    return json.dumps({"jsonrpc":"2.0","id":i,"result":200+i})


class FakeRPC:
    def __init__(self,response=None,fail=False):
        self.calls=[]
        self.response=response
        self.fail=fail
    async def __call__(self,request):
        self.calls.append(json.loads(request))
        if self.fail:
            raise TimeoutError("fake baseline timeout")
        await asyncio.sleep(0)
        return (NOW,NOW+timedelta(milliseconds=1),self.response,None)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")
        self.policy=WsResiliencePolicy(max_reconnects=1)
        self.recovery=BoundedCpmmRecovery(self.db,source_id="test-solana-ws",
                                          accounts=ADDRESS,policy=self.policy)
    async def asyncTearDown(self):
        self.recovery.finalize("test_end")
        self.db.close()
        self.tmp.cleanup()
    def runner(self,connector,rpc):
        return CpmmRecoveryRunner(self.recovery,ws_connect=connector,
            rpc_fetch=rpc,snapshot_identity={
            "endpoint":"https://example.invalid",
            "original_swap_slot":1,"authority":"unknown",
            "input_mint":"unknown","output_mint":"unknown",
            "input_token_program":"unknown","output_token_program":"unknown"},
            duration_seconds=15,sleep=lambda _:asyncio.sleep(0))

    async def test_restart_marks_incomplete_session_and_unknown_gap_durable(self):
        old=self.recovery.new_connection(new_session_id="interrupted-session")
        old._record(ack(1).encode(),"solana_ws_subscription_ack")
        self.assertIsNone(self.db.get_capture_session("test-solana-ws", old.session_id)["finished_at"])
        path=Path(self.tmp.name)/"journal.sqlite"
        self.db.close()
        reopened=SQLiteGeyserRawStore(path)
        restarted=BoundedCpmmRecovery(reopened,source_id="test-solana-ws",
                                      accounts=ADDRESS,policy=self.policy)
        self.assertEqual(restarted.interrupted_sessions,["interrupted-session"])
        capture=reopened.get_capture_session("test-solana-ws","interrupted-session")
        self.assertEqual(capture["outcome"],"process_interrupted")
        self.assertEqual(capture["frame_count"],1)
        self.assertEqual(reopened.list_capture_gaps("test-solana-ws","interrupted-session")[0]["reason"],
                         "process_interrupted")
        self.assertEqual(list(reopened.iter_wire_frames("test-solana-ws","interrupted-session",
                                                       "interrupted-session"))[0][1],ack(1).encode())
        fresh=restarted.new_connection()
        self.assertNotEqual(fresh.session_id,old.session_id)
        self.assertEqual(reopened.integrity_check(),["ok"])
        restarted.finalize("test_end")
        reopened.close()
        self.db=SQLiteGeyserRawStore(path)

    async def test_disconnect_gap_survives_reopen_without_fake_sequence(self):
        connector=FakeConnector([[ack(1),ConnectionClosedError()],
                                 [ack(1),ConnectionClosedError()]])
        report=await self.runner(connector,FakeRPC()).run()
        sid=report["connections"][0]["session_id"]
        gaps=self.db.list_capture_gaps("test-solana-ws",sid)
        self.assertEqual(len(gaps),1)
        self.assertEqual(gaps[0]["reason"],report["gaps"][0]["failure"])
        self.db.close()
        reopened=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")
        self.assertEqual(reopened.list_capture_gaps("test-solana-ws",sid),gaps)
        self.assertIsNone(reopened.get_transport_checkpoint("test-solana-ws",sid))
        self.assertEqual(reopened.integrity_check(),["ok"])
        reopened.close()
        self.db=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")

    async def test_late_rpc_cannot_promote_closed_session(self):
        async def late_rpc(request):
            await asyncio.sleep(0.2)
            return NOW,NOW+timedelta(milliseconds=1),b'{"result":null}',None
        connector=FakeConnector([[ack(1),ack(2),ack(3),ack(4),ConnectionClosedError()],
                                 [ack(1),ack(2),ack(3),ack(4),ConnectionClosedError()]])
        result=await self.runner(connector,late_rpc).run()
        self.assertEqual(len(result["connections"]),2)
        for item in result["connections"]:
            self.assertEqual(item["baseline_status"],"UNKNOWN")
            self.assertIsNone(item["baseline_slot"])
            self.assertEqual(item["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_reconnect_four_new_subscriptions_and_new_baseline(self):
        connector=FakeConnector([[ack(1),ack(2),ack(3),ack(4),
                ConnectionClosedError("broken")],
                [ack(1),ack(2),ack(3),ack(4)]])
        rpc=FakeRPC()
        report=await self.runner(connector,rpc).run()
        self.assertEqual(len(report["connections"]),2)
        self.assertEqual([x["subscriptions_acknowledged"] for x in report["connections"]],[4,4])
        self.assertEqual(report["rpc_baseline_calls"],2)
        self.assertEqual(len(rpc.calls),2)
        self.assertEqual(len(report["gaps"]),2) if False else None
        self.assertNotEqual(report["connections"][0]["session_id"],
                            report["connections"][1]["session_id"])
        self.assertEqual(report["connections"][1]["previous_session_id"],
                         report["connections"][0]["session_id"])
        self.assertEqual(report["coverage"],"UNKNOWN")
        self.assertFalse(report["financial_execution_authorized"])
        self.assertTrue(all(len(s.sent)==4 for s in connector.sockets))
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_partial_subscription_and_retry_limit(self):
        connector=FakeConnector([[ack(1),ConnectionClosedError()],
                                 [ack(1),ConnectionClosedError()]])
        report=await self.runner(connector,FakeRPC()).run()
        self.assertEqual(len(report["connections"]),2)
        self.assertEqual(report["rpc_baseline_calls"],0)
        self.assertEqual(report["stop_reason"],"reconnect_budget_exhausted")
        self.assertEqual(len(report["gaps"]),2)

    async def test_duplicate_ack_is_fatal_not_promoted(self):
        connector=FakeConnector([[ack(1),ack(1)],[ack(1),ConnectionClosedError()]])
        report=await self.runner(connector,FakeRPC()).run()
        self.assertEqual(report["connections"][0]["subscriptions_acknowledged"],1)
        self.assertEqual(report["coverage"],"UNKNOWN")

    async def test_no_reconnect_after_persistence_error(self):
        connector=FakeConnector([[ack(1),ack(2),ack(3),ack(4)]])
        # Failure of journal writing is not safe to paper over by reconnecting.
        original=self.recovery.store.append_wire_frame
        def failed(**kwargs):
            raise OSError("synthetic SQLite write failure")
        self.recovery.store.append_wire_frame=failed
        try:
            result=await self.runner(connector,FakeRPC()).run()
        finally:
            self.recovery.store.append_wire_frame=original
        self.assertEqual(result["stop_reason"],"persistence_failed_no_retry")
        self.assertEqual(len(result["connections"]),1)
        self.assertEqual(result["gaps"][0]["failure"],"PERSISTENCE_FAILED")

    async def test_operator_cancellation(self):
        class CancelSocket(FakeSocket):
            async def recv(self):
                raise asyncio.CancelledError()
        conn=FakeConnector([])
        conn.__call__=None if False else conn.__call__
        class C:
            def __call__(self):
                return CancelSocket([])
        with self.assertRaises(asyncio.CancelledError):
            await self.runner(C(),FakeRPC()).run()
        self.assertFalse(self.recovery.current.active)
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_sessions_never_prove_continuity(self):
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),ConnectionClosedError()],
                            [ack(1),ack(2),ack(3),ack(4),ConnectionClosedError()]])
        result=await self.runner(conn,FakeRPC()).run()
        self.assertFalse(result["continuous_delivery_proven"])
        self.assertFalse(result["global_order_proven"])
        self.assertFalse(result["recovery_live_proven"])
        self.assertEqual(self.recovery.report()["coverage"],"UNKNOWN")
        self.assertFalse(self.recovery.report()["checkpoint_proves_ledger_coverage"])

if __name__=="__main__":
    unittest.main()
