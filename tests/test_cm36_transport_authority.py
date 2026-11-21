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
