"""CM36D: terminal expiry at transport boundaries, without network."""
import asyncio
import unittest
from smart_money_radar.storage.collector_authority import AuthorityLost
from smart_money_radar.services.wallet_monitor import WalletMonitor
from smart_money_radar.services.launch_live_monitor import LaunchLiveMonitor
from smart_money_radar.domain.models import Wallet
from smart_money_radar.settings import HeliusSettings


class ExpiringStore:
    def __init__(self): self.valid=True
    def assert_collector_authority(self,radar=None):
        if not self.valid: raise AuthorityLost("expired")


class TerminalTransport(unittest.IsolatedAsyncioTestCase):
    async def test_wallet_monitor_does_not_reconnect_after_expired_backoff(self):
        store=ExpiringStore()
        monitor=WalletMonitor(HeliusSettings(api_key="offline"),object(),store)
        attempts=[]
        async def disconnected(*args):
            attempts.append(1)
            raise ConnectionError("fixture")
        async def sleep(*args):
            store.valid=False
            return False
        monitor._listen_once=disconnected
        monitor._wait_or_stop=sleep
        with self.assertRaises(AuthorityLost):
            await monitor.run_forever([Wallet("wallet")],asyncio.Event())
        self.assertEqual(len(attempts),1)

    async def test_launch_monitor_does_not_reconnect_after_expired_backoff(self):
        store=ExpiringStore()
        class Backfill: pass
        backfill=Backfill()
        backfill.store=store
        monitor=LaunchLiveMonitor("wss://example.invalid",backfill,["wallet"])
        attempts=[]
        async def disconnected(*args):
            attempts.append(1)
            raise ConnectionError("fixture")
        async def sleep(*args):
            store.valid=False
        monitor._listen=disconnected
        monitor._sleep_or_stop=sleep
        with self.assertRaises(AuthorityLost):
            await monitor.run(asyncio.Event())
        self.assertEqual(len(attempts),1)


    async def test_pending_io_cancelled_and_joined_after_revocation(self):
        from smart_money_radar.storage.collector_authority import await_authorized
        store=ExpiringStore()
        store._force_authority_poll=True
        entered=asyncio.Event()
        cleaned=asyncio.Event()
        async def pending():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        task=asyncio.create_task(await_authorized(store,"launch",pending,poll_seconds=.005))
        await entered.wait()
        store.valid=False
        with self.assertRaises(AuthorityLost):
            await asyncio.wait_for(task,1)
        self.assertTrue(cleaned.is_set())

    async def test_revoked_handle_never_starts_io(self):
        from smart_money_radar.storage.collector_authority import await_authorized
        store=ExpiringStore()
        store.valid=False
        called=[]
        async def operation(): called.append(True)
        with self.assertRaises(AuthorityLost):
            await await_authorized(store,"smart_money",operation)
        self.assertEqual(called,[])

    async def test_operator_cancellation_joins_pending_task(self):
        from smart_money_radar.storage.collector_authority import await_authorized
        store=ExpiringStore();store._force_authority_poll=True
        entered=asyncio.Event();cleaned=asyncio.Event()
        async def pending():
            entered.set()
            try: await asyncio.Event().wait()
            finally: cleaned.set()
        t=asyncio.create_task(await_authorized(store,"launch",pending))
        await entered.wait();t.cancel()
        with self.assertRaises(asyncio.CancelledError): await t
        self.assertTrue(cleaned.is_set())


    async def test_thread_rpc_result_discarded_after_authority_revocation(self):
        import threading
        from smart_money_radar.storage.collector_authority import await_authorized
        store=ExpiringStore();store._force_authority_poll=True
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        published=[]
        def rpc():
            entered.set()
            try:
                if not release.wait(3): raise RuntimeError("test release timeout")
                return {"late":"reply"}
            finally: finished.set()
        async def collect():
            reply=await await_authorized(store,"launch",lambda:asyncio.to_thread(rpc),poll_seconds=.005)
            published.append(reply)
        task=asyncio.create_task(collect())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,1))
            store.valid=False
            with self.assertRaises(AuthorityLost):
                await asyncio.wait_for(task,1)
            self.assertEqual(published,[])
        finally:
            release.set()
        self.assertTrue(await asyncio.to_thread(finished.wait,1))
        self.assertEqual(published,[])
