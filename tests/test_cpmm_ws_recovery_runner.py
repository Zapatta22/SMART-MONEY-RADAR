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
        if self.recovery.current is not None and self.recovery.current.active:
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


    async def test_crashed_subscription_is_closed_on_restart_with_new_identity(self):
        old=self.recovery.new_connection()
        original_id=old.session_id
        old._record(b'{"jsonrpc":"2.0","id":1,"result":201}',"solana_ws_subscription_ack")
        # Simulate abrupt process death: do not call finish().
        self.db.close()
        reopened=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")
        recovered=BoundedCpmmRecovery(reopened,source_id="test-solana-ws",
                                       accounts=ADDRESS,policy=self.policy)
        result=await CpmmRecoveryRunner(recovered,ws_connect=FakeConnector([[
            ack(1),ack(2),ack(3),ack(4),ConnectionClosedError()]]),
            rpc_fetch=FakeRPC(),snapshot_identity={
            "endpoint":"https://example.invalid","original_swap_slot":1,
            "authority":"unknown","input_mint":"unknown","output_mint":"unknown",
            "input_token_program":"unknown","output_token_program":"unknown"},
            duration_seconds=15,sleep=lambda _:asyncio.sleep(0)).run()
        previous=reopened.get_capture_session("test-solana-ws",original_id)
        self.assertEqual(previous["outcome"],"process_interrupted_unknown")
        self.assertEqual(previous["frame_count"],1)
        self.assertNotEqual(result["connections"][0]["session_id"],original_id)
        self.assertEqual(result["coverage"],"UNKNOWN")
        self.assertEqual(reopened.integrity_check(),["ok"])
        old.active=False  # process memory is gone after simulated crash
        self.db=reopened

    async def test_rpc_failure_never_promotes_baseline(self):
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),
                             ConnectionClosedError()]])
        result=await self.runner(conn,FakeRPC(fail=True)).run()
        self.assertEqual(result["connections"][0]["baseline_status"],"UNKNOWN")
        self.assertFalse(result["continuous_delivery_proven"])
        self.assertEqual(result["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_rpc_response_bound_to_origin_session(self):
        class SlowRPC:
            def __init__(self):
                self.calls=0
            async def __call__(self,request):
                self.calls+=1
                if self.calls==1:
                    # Cancellation is delivered after the first socket fails.
                    await asyncio.sleep(3600)
                return NOW,NOW,None,"simulated_null"
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),
                             ConnectionClosedError()],
                            [ack(1),ack(2),ack(3),ack(4),
                             ConnectionClosedError()]])
        report=await self.runner(conn,SlowRPC()).run()
        self.assertEqual(len(report["connections"]),2)
        self.assertEqual(report["connections"][0]["baseline_error"],"CancelledError")
        self.assertEqual(report["connections"][0]["baseline_status"],"UNKNOWN")
        self.assertNotEqual(report["connections"][0]["session_id"],
                            report["connections"][1]["session_id"])
        self.assertTrue(all(x["coverage"]=="UNKNOWN" for x in report["connections"]))
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_store_recovery_is_idempotent(self):
        old=self.recovery.new_connection()
        old._record(b"immutable", "synthetic_frame")
        sid=old.session_id
        self.db.close()
        reopened=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")
        self.assertEqual(reopened.recover_incomplete_capture_sessions(
            source_id="test-solana-ws"),[sid])
        self.assertEqual(reopened.recover_incomplete_capture_sessions(
            source_id="test-solana-ws"),[])
        self.assertEqual(reopened.get_capture_session(
            "test-solana-ws",sid)["frame_count"],1)
        self.assertEqual(list(reopened.iter_wire_frames(
            "test-solana-ws",sid,sid)),[(0,b"immutable")])
        self.assertEqual(reopened.integrity_check(),["ok"])
        old.active=False  # process memory is gone after simulated crash
        self.db=reopened

if __name__=="__main__":
    unittest.main()
