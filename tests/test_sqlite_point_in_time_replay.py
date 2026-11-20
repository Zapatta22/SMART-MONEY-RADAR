"""SQLite archive replay: available_at gates, idempotency, gaps and restart."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from smart_money_radar.domain.models import (
    SwapClassification, SwapEvidence, SwapObservation, build_swap_operation_id,
)
from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
from smart_money_radar.services.sqlite_market_history import archived_volume_at
from smart_money_radar.services.historical_opportunity_replay import reconstruct_opportunity_at
from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
from smart_money_radar.services.wallet_consensus import WalletConsensusReport
from smart_money_radar.storage.event_store import SQLiteEventStore


START=datetime(2026,1,1,tzinfo=timezone.utc)


class SQLitePointInTimeReplayTests(unittest.TestCase):
    def setUp(self):
        directory=TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db=Path(directory.name)/"history.sqlite"
        self.store=SQLiteEventStore(self.db)
        self.addCleanup(self.store.close)

    def add(self, signature, occurred, available, *, wallet="tracked"):
        op=build_swap_operation_id("solana",signature,0)
        self.store.save_observation(wallet,signature,{"meta":{"err":None}},[],
                                    parse_status="no_events",parser_version="1",
                                    advance_checkpoint=False)
        observation=SwapObservation(op,"solana",wallet,signature,"quote","base",
                    Decimal("10"),Decimal("2"),START+timedelta(seconds=occurred),"1")
        classification=SwapClassification(op,"BUY",Decimal("0.99"),"fixture")
        evidence=SwapEvidence(op,"program",None,0,evidence=("pool_state:pool",))
        self.store.save_swap_bundle(observation,classification,evidence)
        with patch("smart_money_radar.storage.event_store.datetime",wraps=datetime) as clock:
            clock.now.return_value=START+timedelta(seconds=available)
            self.store.mark_processed(wallet,signature,replay_bundles=(
                SwapDomainBundle(observation,classification,evidence),))
        return op

    def at(self,s):
        return archived_volume_at(
            self.store,wallets=("tracked",),program="program",pool="pool",
            token_mint="base",quote_mint="quote",
            as_of=START+timedelta(seconds=s),window=timedelta(minutes=2))

    def test_no_future_receipt_in_historical_cutoff(self):
        self.add("first",1,2)
        later=self.add("later",2,10)
        early=self.at(5)
        self.assertEqual(early.receipts_seen,2)
        self.assertEqual(early.receipts_in_window,1)
        self.assertIn((later,"not_yet_available"),early.excluded_receipts)
        self.assertIsNone(early.volume.quote_volume)
        self.assertFalse(early.volume.volume_verified)
        after=self.at(12)
        self.assertEqual(after.receipts_in_window,2)
        self.assertEqual(after.historical_coverage,"UNKNOWN")

    def test_replay_is_deterministic_after_database_restart(self):
        self.add("first",1,2)
        before=self.at(3)
        self.store.close()
        reopened=SQLiteEventStore(self.db,read_only=True)
        self.addCleanup(reopened.close)
        after=archived_volume_at(
            reopened,wallets=("tracked",),program="program",pool="pool",
            token_mint="base",quote_mint="quote",
            as_of=START+timedelta(seconds=3),window=timedelta(minutes=2))
        self.assertEqual(before,after)

    def test_missing_evidence_is_unknown_not_zero_observed_volume(self):
        result=self.at(5)
        self.assertEqual(result.receipts_seen,0)
        self.assertIsNone(result.volume.quote_volume)
        self.assertEqual(result.historical_coverage,"UNKNOWN")
        self.assertEqual(result.quote_provenance,"NO_EXECUTABLE_QUOTE")

    def test_scope_excludes_wrong_pool(self):
        self.add("first",1,2)
        result=archived_volume_at(
            self.store,wallets=("tracked",),program="program",pool="other",
            token_mint="base",quote_mint="quote",
            as_of=START+timedelta(seconds=3),window=timedelta(minutes=2))
        self.assertEqual(result.receipts_seen,0)

    def test_history_classification_denies_fake_verified_caller(self):
        self.add("first",1,2)
        at=START+timedelta(seconds=3)
        base=OpportunityEvidence(
            token_mint="base",chain="solana",pool="pool",as_of=at,
            source_id="provider",source_status="VERIFIED",history_coverage="COMPLETE",
            token_safety="VERIFIED",liquidity_quote=Decimal("10000"),
            volume_quote=Decimal("10000"),liquidity_verified=True,
            volume_verified=True,price_confirmation=True,volume_confirmation=True,
            wallet_independence_verified=True)
        consensus=WalletConsensusReport(
            direction="BUY",eligible_wallets=3,supporting_signatures=5,
            rejected_wallets=(),members=(),independence_verified=True,
            actionable=False,reasons=())
        frame=reconstruct_opportunity_at(
            self.store,wallets=("tracked",),program="program",pool="pool",
            token_mint="base",quote_mint="quote",cutoff=at,
            window=timedelta(minutes=2),consensus=consensus,base=base)
        self.assertEqual(frame.assessment.classification.verdict,"UNKNOWN")
        self.assertFalse(frame.operational_authorized)
        self.assertIn("quote_not_authenticated",frame.gaps)
        self.assertEqual(frame.assessment.classification.volume_quote,None)

    def test_reprocessing_does_not_duplicate_receipts(self):
        self.add("first",1,2)
        before=self.at(3)
        self.store.mark_processed("tracked","first")
        self.assertEqual(before,self.at(3))


if __name__=="__main__":
    unittest.main()
