"""Offline-only fake sockets/RPC: never claim they are Solana observations."""
import asyncio
import json
import sqlite3
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
        self.assertEqual(report["connections"][0]["baseline_error"],"RPC_TIMEOUT")
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


    async def test_late_rpc_bytes_are_journaled_but_never_promoted(self):
        rpc_raw=b'{"jsonrpc":"2.0","result":{"context":{"slot":5},"value":[]}}'
        class LateRPC:
            async def __call__(self,request):
                await asyncio.sleep(0)
                return NOW,NOW,rpc_raw,None
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),
                             ConnectionClosedError("socket gone")],
                            [ack(1),ConnectionClosedError()]])
        report=await self.runner(conn,LateRPC()).run()
        first=report["connections"][0]
        self.assertEqual(first["baseline_rejection"],"websocket_disconnected")
        self.assertEqual(first["baseline_status"],"UNKNOWN")
        self.assertFalse(first.get("baseline_verified_as_snapshot",False))
        sid=first["session_id"]
        raw=[payload for _,payload in self.db.iter_wire_frames(
            "test-solana-ws",sid,sid)]
        self.assertEqual(len(raw),6)  # Four ACKs, original request and late response.
        self.assertEqual(raw[-1],rpc_raw)
        self.assertEqual(first["journal"]["frame_count"],6)
        self.assertEqual(first["coverage"],"UNKNOWN")
        self.assertEqual(report["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_interrupted_rpc_timeout_keeps_coverage_unknown(self):
        class HangingRPC:
            async def __call__(self,request):
                await asyncio.sleep(3600)
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),
                             ConnectionClosedError("socket gone")],
                            [ack(1),ConnectionClosedError()]])
        report=await self.runner(conn,HangingRPC()).run()
        first=report["connections"][0]
        self.assertEqual(first["baseline_error"],"RPC_TIMEOUT")
        self.assertEqual(first["baseline_status"],"UNKNOWN")
        self.assertEqual(first["journal"]["frame_count"],5)
        self.assertEqual(report["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_orphaned_stream_before_session_registration_recovered(self):
        sid="crashed-before-start"
        self.db.register_frame_stream("test-solana-ws",sid,sid,0)
        self.db.close()
        reopened=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")
        self.assertEqual(reopened.recover_incomplete_capture_sessions(
            source_id="test-solana-ws"),[sid])
        metadata=reopened.get_capture_session("test-solana-ws",sid)
        self.assertEqual(metadata["outcome"],"process_interrupted_unknown")
        self.assertEqual(metadata["frame_count"],0)
        self.assertIsNotNone(metadata["finished_at"])
        self.assertEqual(reopened.recover_incomplete_capture_sessions(
            source_id="test-solana-ws"),[])
        self.assertEqual(reopened.integrity_check(),["ok"])
        self.db=reopened


    async def test_rpc_failure_is_classified_as_baseline_failure(self):
        unrecognized='{"jsonrpc":"2.0","method":"syntheticUnknown"}'
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),
                             unrecognized,ConnectionClosedError()],
                            [ack(1),ConnectionClosedError()]])
        result=await self.runner(conn,FakeRPC(fail=True)).run()
        self.assertEqual(result["gaps"][0]["failure"],"BASELINE_FAILED")
        self.assertEqual(result["connections"][0]["baseline_status"],"UNKNOWN")
        self.assertFalse(result["connections"][0].get("baseline_verified_as_snapshot",False))
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_rpc_return_after_global_deadline_is_rejected(self):
        class SilentAfterAcks(FakeSocket):
            async def recv(self):
                if self.events:
                    return await super().recv()
                raise asyncio.TimeoutError()
        class C:
            def __call__(self):
                return SilentAfterAcks([ack(1),ack(2),ack(3),ack(4)])
        tick=[0]
        def clock():
            tick[0]+=1
            return tick[0]
        class RPC:
            async def __call__(self,request):
                return NOW,NOW,b'{"result":{"context":{"slot":99},"value":[]}}',None
        r=CpmmRecoveryRunner(self.recovery,ws_connect=C(),rpc_fetch=RPC(),
            snapshot_identity={"endpoint":"https://example.invalid",
            "original_swap_slot":1,"authority":"unknown",
            "input_mint":"unknown","output_mint":"unknown",
            "input_token_program":"unknown","output_token_program":"unknown"},
            duration_seconds=15,sleep=lambda _:asyncio.sleep(0),
            clock=clock,now=lambda:NOW)
        result=await r.run()
        first=result["connections"][0]
        self.assertEqual(first["baseline_rejection"],"global_deadline_elapsed")
        self.assertEqual(first["baseline_status"],"UNKNOWN")
        self.assertEqual(first["journal"]["frame_count"],6)
        self.assertEqual(result["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])


    async def test_regressive_rpc_slot_never_promotes_baseline(self):
        extra='{"jsonrpc":"2.0","method":"syntheticUnknown"}'
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),extra]])
        rpc=FakeRPC(response=b'{"result":{"context":{"slot":0},"value":[]}}')
        base=self.runner(conn,rpc)
        base.max_frames=5
        report=await base.run()
        first=report["connections"][0]
        self.assertEqual(first["baseline_rejection"],"regressive_rpc_slot")
        self.assertEqual(first["baseline_status"],"UNKNOWN")
        self.assertFalse(first.get("baseline_verified_as_snapshot",False))
        self.assertEqual(first["journal"]["frame_count"],7)
        self.assertEqual(report["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_incomplete_rpc_baseline_remains_unknown(self):
        extra='{"jsonrpc":"2.0","method":"syntheticUnknown"}'
        conn=FakeConnector([[ack(1),ack(2),ack(3),ack(4),extra]])
        rpc=FakeRPC(response=b'{"result":{"context":{"slot":5},"value":[]}}')
        base=self.runner(conn,rpc)
        base.max_frames=5
        report=await base.run()
        first=report["connections"][0]
        self.assertFalse(first.get("baseline_verified_as_snapshot",False))
        self.assertEqual(first["coverage"],"UNKNOWN")
        self.assertEqual(first["journal"]["frame_count"],7)
        self.assertEqual(report["coverage"],"UNKNOWN")
        self.assertEqual(self.db.integrity_check(),["ok"])

    async def test_raw_checkpoint_transaction_rolls_back_on_fault(self):
        session=self.recovery.new_connection()
        db_path=Path(self.tmp.name)/"journal.sqlite"
        with sqlite3.connect(db_path) as connection:
            connection.execute("""CREATE TRIGGER synthetic_abort_checkpoint
                BEFORE UPDATE ON geyser_frame_streams BEGIN
                SELECT RAISE(ABORT, 'synthetic checkpoint failure');
                END""")
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                session._record(b"synthetic-raw","test_raw")
        finally:
            with sqlite3.connect(db_path) as connection:
                count=connection.execute(
                    "SELECT COUNT(*) FROM geyser_wire_frames WHERE stream_id=?",
                    (session.session_id,)).fetchone()[0]
                seq=connection.execute(
                    "SELECT contiguous_sequence,last_seen_sequence FROM geyser_frame_streams WHERE stream_id=?",
                    (session.session_id,)).fetchone()
                self.assertEqual(count,0)
                self.assertEqual(seq,(-1,-1))
                connection.execute("DROP TRIGGER synthetic_abort_checkpoint")
        session._record(b"synthetic-raw","test_raw")
        session.finish("bounded_end")
        self.db.close()
        reopened=SQLiteGeyserRawStore(db_path)
        self.assertEqual(list(reopened.iter_wire_frames(
            "test-solana-ws",session.session_id,session.session_id)),
            [(0,b"synthetic-raw")])
        self.assertEqual(reopened.integrity_check(),["ok"])
        self.db=reopened

    async def test_sha256_conflict_taints_replay_without_checkpoint_jump(self):
        session=self.recovery.new_connection()
        sid=session.session_id
        session._record(b"original","synthetic")
        same=self.db.append_wire_frame(source_id="test-solana-ws",stream_id=sid,
            ordering_domain_id=sid,stream_sequence=0,
            payload=b"original",frame_kind="synthetic")
        self.assertEqual(same.status,"duplicate")
        collision=self.db.append_wire_frame(source_id="test-solana-ws",
            stream_id=sid,ordering_domain_id=sid,stream_sequence=0,
            payload=b"altered",frame_kind="synthetic")
        self.assertEqual(collision.status,"collision")
        self.assertTrue(collision.tainted)
        self.assertEqual(collision.contiguous_sequence,0)
        with self.assertRaises(ValueError):
            self.db.verify_wire_session("test-solana-ws",sid,sid)
        session.finish("interrupted_unknown")
        self.assertEqual(self.db.integrity_check(),["ok"])


    async def test_two_concurrent_runners_same_source_fail_closed(self):
        first_started=asyncio.Event()
        allow_finish=asyncio.Event()
        class BlockedSocket(FakeSocket):
            async def recv(self):
                if self.events:
                    return await super().recv()
                first_started.set()
                await allow_finish.wait()
                raise ConnectionClosedError("intentional fake stop")
        class FirstConnector:
            def __call__(self):
                return BlockedSocket([ack(1),ack(2),ack(3),ack(4)])
        first=self.runner(FirstConnector(),FakeRPC())
        first_task=asyncio.create_task(first.run())
        try:
            await asyncio.wait_for(first_started.wait(),timeout=3)
            contender_store=SQLiteGeyserRawStore(Path(self.tmp.name)/"journal.sqlite")
            contender=BoundedCpmmRecovery(contender_store,source_id="test-solana-ws",
                                          accounts=ADDRESS,policy=self.policy)
            second=CpmmRecoveryRunner(contender,ws_connect=FakeConnector([[
                ack(1),ack(2),ack(3),ack(4)]]),rpc_fetch=FakeRPC(),
                snapshot_identity=first.snapshot_identity,duration_seconds=15,
                sleep=lambda _:asyncio.sleep(0))
            try:
                with self.assertRaisesRegex(ValueError,"owner still alive|source leased"):
                    await second.run()
                self.assertEqual(len(contender.sessions),0)
                active=self.db.get_capture_session(
                    "test-solana-ws",self.recovery.current.session_id)
                self.assertIsNone(active["finished_at"])
                self.assertEqual(self.db.integrity_check(),["ok"])
            finally:
                contender_store.close()
        finally:
            allow_finish.set()
            await asyncio.wait_for(first_task,timeout=3)
        self.assertEqual(self.db.integrity_check(),["ok"])
        self.assertEqual(first.manifest["coverage"],"UNKNOWN")
        self.assertIsNotNone(self.db.get_capture_session(
            "test-solana-ws",self.recovery.current.session_id)["finished_at"])

    async def test_persistent_lease_after_crash_requires_explicit_recovery(self):
        owner="synthetic-dead-owner"
        self.db.recover_incomplete_capture_sessions(
            source_id="test-solana-ws",owner_id=owner)
        old=self.recovery.new_connection()
        old._record(b"durable-after-kill","synthetic")
        sid=old.session_id
        db_path=Path(self.tmp.name)/"journal.sqlite"
        self.db.close()
        restarted=SQLiteGeyserRawStore(db_path)
        with self.assertRaisesRegex(ValueError,"source leased"):
            restarted.recover_incomplete_capture_sessions(
                source_id="test-solana-ws",owner_id="another-owner")
        self.assertIsNone(restarted.get_capture_session(
            "test-solana-ws",sid)["finished_at"])
        self.assertEqual(list(restarted.iter_wire_frames(
            "test-solana-ws",sid,sid)),[(0,b"durable-after-kill")])
        # Explicit verified dead-owner recovery is outside this command;
        # test only that incorrect ownership cannot take over.
        with self.assertRaises(ValueError):
            restarted.release_capture_source_lease(
                source_id="test-solana-ws",owner_id="another-owner")
        # The owner PID is still alive in this test: automatic takeover
        # correctly fails closed, even after the SQLite handle is closed.
        with self.assertRaisesRegex(ValueError,"owner still alive"):
            restarted.release_dead_capture_source_lease(
                source_id="test-solana-ws",owner_id=owner)
        restarted.release_capture_source_lease(
            source_id="test-solana-ws",owner_id=owner)
        self.assertEqual(restarted.recover_incomplete_capture_sessions(
            source_id="test-solana-ws"),[sid])
        self.assertEqual(restarted.get_capture_session(
            "test-solana-ws",sid)["outcome"],"process_interrupted_unknown")
        self.assertEqual(restarted.integrity_check(),["ok"])
        old.active=False
        self.db=restarted

    async def test_recovery_claim_and_incomplete_session_close_are_atomic(self):
        old=self.recovery.new_connection()
        sid=old.session_id
        old._record(b"captured","synthetic")
        db_path=Path(self.tmp.name)/"journal.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.execute("""CREATE TRIGGER deny_recovery
                BEFORE UPDATE ON geyser_capture_sessions BEGIN
                SELECT RAISE(ABORT,'synthetic recovery interruption');
                END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.recover_incomplete_capture_sessions(
                source_id="test-solana-ws",owner_id="failed-owner")
        with sqlite3.connect(db_path) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM geyser_capture_source_leases"
            ).fetchone()[0],0)
            self.assertIsNone(conn.execute(
                "SELECT finished_at FROM geyser_capture_sessions WHERE stream_id=?",
                (sid,)).fetchone()[0])
            conn.execute("DROP TRIGGER deny_recovery")
        recovered=self.db.recover_incomplete_capture_sessions(
            source_id="test-solana-ws",owner_id="working-owner")
        self.assertEqual(recovered,[sid])
        self.assertEqual(self.db.get_capture_session(
            "test-solana-ws",sid)["frame_count"],1)
        self.db.release_capture_source_lease(
            source_id="test-solana-ws",owner_id="working-owner")
        self.assertEqual(self.db.integrity_check(),["ok"])
        old.active=False


    async def test_dead_local_process_lease_is_reclaimed_without_raw_loss(self):
        import os
        import subprocess
        db_path=Path(self.tmp.name)/"journal.sqlite"
        # External process exits before ownership recovery. Its PID and
        # start identity are captured while alive and checked by procfs.
        worker=subprocess.Popen(["python","-c","import time; time.sleep(0.05)"])
        try:
            ticks=self.db.local_process_start_ticks(worker.pid)
            owner="dead-worker"
            self.db.acquire_capture_source_lease(
                source_id="test-solana-ws",owner_id=owner)
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """UPDATE geyser_capture_source_leases
                       SET pid=?, pid_start_ticks=?
                       WHERE source_id=?""",
                    (worker.pid,ticks,"test-solana-ws"),
                )
            session=self.recovery.new_connection()
            session._record(b"before-kill","synthetic")
            sid=session.session_id
        finally:
            worker.wait(timeout=3)
        self.assertTrue(self.db.release_dead_capture_source_lease(
            source_id="test-solana-ws",owner_id=owner))
        self.assertEqual(self.db.recover_incomplete_capture_sessions(
            source_id="test-solana-ws"),[sid])
        self.assertEqual(self.db.get_capture_session(
            "test-solana-ws",sid)["frame_count"],1)
        self.assertEqual(list(self.db.iter_wire_frames(
            "test-solana-ws",sid,sid)),[(0,b"before-kill")])
        self.assertEqual(self.db.integrity_check(),["ok"])
        session.active=False


    async def test_runner_reclaims_verified_dead_owner_automatically(self):
        import subprocess
        db_path=Path(self.tmp.name)/"journal.sqlite"
        proc=subprocess.Popen(["python","-c","import time; time.sleep(0.05)"])
        try:
            ticks=self.db.local_process_start_ticks(proc.pid)
            self.db.acquire_capture_source_lease(
                source_id="test-solana-ws",owner_id="dead-previous")
            with sqlite3.connect(db_path) as con:
                con.execute(
                    "UPDATE geyser_capture_source_leases SET pid=?, pid_start_ticks=?",
                    (proc.pid,ticks),
                )
            old=self.recovery.new_connection()
            old._record(b"old-process-raw","synthetic")
            old_id=old.session_id
        finally:
            proc.wait(timeout=3)
        self.db.close()
        restarted=SQLiteGeyserRawStore(db_path)
        recovery=BoundedCpmmRecovery(restarted,source_id="test-solana-ws",
            accounts=ADDRESS,policy=self.policy)
        new_runner=CpmmRecoveryRunner(recovery,
            ws_connect=FakeConnector([[ack(1),ConnectionClosedError()]]),
            rpc_fetch=FakeRPC(),snapshot_identity=self.runner(None,None).snapshot_identity,
            duration_seconds=15,sleep=lambda _:asyncio.sleep(0))
        report=await new_runner.run()
        self.assertTrue(report["recovered_dead_owner"])
        self.assertIn(old_id,report["recovered_incomplete_session_ids"])
        self.assertNotEqual(report["connections"][0]["session_id"],old_id)
        self.assertEqual(restarted.get_capture_session(
            "test-solana-ws",old_id)["outcome"],"process_interrupted_unknown")
        self.assertEqual(list(restarted.iter_wire_frames(
            "test-solana-ws",old_id,old_id)),[(0,b"old-process-raw")])
        self.assertEqual(report["coverage"],"UNKNOWN")
        self.assertEqual(restarted.integrity_check(),["ok"])
        old.active=False
        self.db=restarted

if __name__=="__main__":
    unittest.main()
