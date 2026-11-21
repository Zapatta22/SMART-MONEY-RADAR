"""CM35: real SQLite producers and point-in-time candidate discovery."""
import json
import sqlite3
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from smart_money_radar.domain.models import SwapObservation,SwapClassification,SwapEvidence,build_swap_operation_id
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.services.wallet_discovery import WalletDiscoveryPolicy,discover_wallets,persist_wallet_snapshot,read_wallet_snapshots,qualified_consensus_at
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.dashboard_read import DashboardReadService
T=datetime(2026,11,21,tzinfo=timezone.utc)
def policy(**kw):
    return WalletDiscoveryPolicy(**dict(dict(quote_mints=("quote",),min_transactions=2),**kw))
class CM35Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"smr.sqlite"
        self.store=SQLiteEventStore(self.db);self.addCleanup(self.store.close)
    def receipt(self,wallet="w",sig="sig",offset=0,side="BUY",opindex=0,raw_sig=None):
        at=T+timedelta(seconds=offset)
        raw={"slot":7,"transaction":{"signatures":[raw_sig or sig],
            "message":{"accountKeys":[wallet],"header":{"numRequiredSignatures":1}}},
            "meta":{"err":None}}
        self.store.save_observation(wallet,sig,raw,[],parse_status="no_events",parser_version="1",advance_checkpoint=False)
        with self.store._connection_scope() as conn,conn:
            conn.execute("UPDATE observed_transactions SET slot=?,chain=?,observed_at=? WHERE wallet_address=? AND signature=?",
                (7,"solana",(at-timedelta(seconds=1)).isoformat(),wallet,sig))
        op=build_swap_operation_id("solana",sig,opindex)
        a,b=("quote","base") if side=="BUY" else ("base","quote")
        obs=SwapObservation(op,"solana",wallet,sig,a,b,D("10"),D("2"),at-timedelta(seconds=2),"1")
        cls=SwapClassification(op,side,D(".95"),"fixture")
        ev=SwapEvidence(op,"dex",None,opindex,evidence=("pool_state:pool",))
        self.store.save_swap_bundle(obs,cls,ev)
        with patch("smart_money_radar.storage.event_store.datetime",wraps=datetime) as clock:
            clock.now.return_value=at
            self.store.mark_processed(wallet,sig,replay_bundles=(SwapDomainBundle(obs,cls,ev),))
    def test_automatic_candidate_without_manual_list_and_unknown_economics(self):
        self.receipt(sig="a");self.receipt(sig="b",offset=1)
        report=discover_wallets(self.store,as_of=T+timedelta(seconds=1),policy=policy())
        p,=report["profiles"]
        self.assertEqual(p["wallet"],"w")
        self.assertEqual(p["status"],"OBSERVED")
        self.assertEqual(p["buy_count"],2)
        self.assertEqual(p["local_distinct_transactions"],2)
        self.assertIsNone(p["realized_pnl"])
        self.assertIsNone(p["win_rate"])
        self.assertFalse(p["eligible_for_consensus"])
        self.assertEqual(report,discover_wallets(self.store,as_of=T+timedelta(seconds=1),policy=policy()))
    def test_future_receipt_does_not_change_earlier_decision(self):
        self.receipt(sig="a")
        before=discover_wallets(self.store,as_of=T,policy=policy())
        self.receipt(wallet="future",sig="b",offset=60)
        self.assertEqual(before,discover_wallets(self.store,as_of=T,policy=policy()))
    def test_manual_candidate_and_dynamic_reclassification(self):
        first=discover_wallets(self.store,as_of=T,policy=policy(manual_wallets=("w",)))
        self.assertEqual(first["profiles"][0]["status"],"CANDIDATE")
        self.receipt()
        second=discover_wallets(self.store,as_of=T,policy=policy(manual_wallets=("w",)))
        self.assertEqual(second["profiles"][0]["status"],"OBSERVED")
        self.assertEqual(set(second["profiles"][0]["origins"]),{"ARCHIVED_SWAP_RECEIPT","MANUAL_COMPLEMENT"})
    def test_raw_identity_conflict_blocks(self):
        self.receipt(raw_sig="wrong")
        p,=discover_wallets(self.store,as_of=T,policy=policy())["profiles"]
        self.assertEqual(p["status"],"BLOCKED");self.assertIsNone(p["score"])
    def test_shared_signature_never_creates_consensus(self):
        self.receipt(wallet="a",sig="shared",opindex=0)
        self.receipt(wallet="b",sig="shared",opindex=1)
        r=discover_wallets(self.store,as_of=T,policy=policy())
        self.assertEqual(len(r["profiles"]),2)
        self.assertTrue(all(p["status"]=="DISQUALIFIED" for p in r["profiles"]))
        self.assertTrue(all(p["local_distinct_transactions"]==0 for p in r["profiles"]))
        got=qualified_consensus_at(self.store,as_of=T,policy=policy(),program="dex",pool="pool",
            base_mint="base",quote_mint="quote",window=timedelta(minutes=5),
            max_publication_delay=timedelta(minutes=5),min_confidence=D(".8"))
        self.assertEqual(got["consensus"]["direction"],"INSUFFICIENT")
        self.assertEqual(got["qualified_wallets"],[])
    def test_persist_restart_dashboard_and_corruption(self):
        self.receipt()
        a=persist_wallet_snapshot(self.store,as_of=T,policy=policy())
        self.assertEqual(a,persist_wallet_snapshot(self.store,as_of=T,policy=policy()))
        self.store.close()
        reader=SQLiteEventStore(self.db,read_only=True);self.addCleanup(reader.close)
        self.assertEqual(read_wallet_snapshots(reader),[a])
        data=DashboardReadService(reader).get_overview()
        self.assertEqual(data["wallet_discovery"],[a])
        self.assertEqual(data["radar_events"]["launch"],[])
        with self.assertRaises(ValueError):persist_wallet_snapshot(reader,as_of=T,policy=policy())
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cm35_wallet_profiles SET payload='{}'")
        self.assertEqual(read_wallet_snapshots(reader)[0]["status"],"CONFLICTED")
    def test_same_signature_multiple_operations_counts_once(self):
        self.receipt(sig="a",opindex=0);self.receipt(sig="a",opindex=1)
        p,=discover_wallets(self.store,as_of=T,policy=policy())["profiles"]
        self.assertEqual(p["local_distinct_transactions"],1)
    def test_bounded_archive_and_explicit_exclusion(self):
        self.receipt(sig="a");self.receipt(sig="b",offset=1)
        r=discover_wallets(self.store,as_of=T+timedelta(seconds=1),policy=policy(max_receipts=1))
        self.assertTrue(r["truncated"]);self.assertIsNone(r["profiles"][0]["score"])
        p,=discover_wallets(self.store,as_of=T+timedelta(seconds=1),policy=policy(excluded_accounts=("w",)))["profiles"]
        self.assertEqual(p["status"],"DISQUALIFIED");self.assertFalse(p["eligible_for_consensus"])
