"""CM44: economic receipt integrity, scoped Launch adapters and blocked CM39."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from smart_money_radar.services.cm38j_metric_provenance import (
    describe_metric, qualify_metric_set,
)
from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
from smart_money_radar.services.market_volume_audit import SwapVolumeEvidence

class TestCm44EconomicIntegration(unittest.TestCase):
    def setUp(self):
        self.at = datetime.now(timezone.utc) - timedelta(seconds=45)
        self.start = self.at - timedelta(minutes=5)

    def metric(self, **overrides):
        args = dict(name="liquidity", value=None, start=self.start, end=self.at,
                    available_at=self.at, decision_at=self.at, quality="UNKNOWN",
                    unavailable_reason="unverified")
        args.update(overrides)
        return describe_metric(**args)

    def test_unknown_cannot_be_promoted_by_tampering(self):
        metric = self.metric()
        metric["quality"] = "VERIFIED"
        metric["value"] = "100000"
        with self.assertRaisesRegex(ValueError,"integrity"):
            qualify_metric_set(radar="launch",metrics=[metric])

    def test_duplicate_metric_rejected(self):
        m = self.metric()
        with self.assertRaisesRegex(ValueError,"duplicate"):
            qualify_metric_set(radar="launch", metrics=[m,m])

    def test_model_estimate_must_not_be_declared_verified(self):
        with self.assertRaisesRegex(ValueError,"model estimate"):
            self.metric(value=Decimal("2"),unavailable_reason=None,
                        source_id="test",evidence_ids=("a"*64,),
                        quality="VERIFIED",kind="MODEL_ESTIMATE")

    def test_cross_radar_scope_cannot_be_relabelled(self):
        with self.assertRaises(ValueError):
            self.metric(radar="smart_money")

    def test_launch_without_sources_tracks_all_missing_metrics(self):
        report = launch_metric_receipts(token_mint="TOKEN",pool="POOL",
            quote_mint="USDC",at=self.at,strategy="immediate")
        self.assertEqual(len(report["metrics"]),9)
        self.assertIsNone(report["observed_reserve_quote"])
        self.assertIsNone(report["observed_volume_quote"])
        self.assertFalse(report["metric_audit"]["qualified"])
        self.assertFalse(report["prospective_paper_authorized"])
        self.assertEqual(report["modes"]["confirmed"],"BLOCKED")

    def test_confirmed_strategy_keeps_independent_scope(self):
        report = launch_metric_receipts(token_mint="TOKEN",pool="POOL",
            quote_mint="USDC",at=self.at,strategy="confirmed")
        self.assertEqual(report["strategy"],"confirmed")
        self.assertEqual(report["metrics"][0]["strategy"],"confirmed")

    def test_other_pool_swap_cannot_prove_volume(self):
        payload=b"record"
        swap=SwapVolumeEvidence("a"*64,"sig","rpc","OTHER","TOKEN","USDC",
            1,self.at,self.at,"finalized",Decimal("10"),"BUY",
            payload,sha256(payload).hexdigest())
        with self.assertRaisesRegex(ValueError,"escopo"):
            launch_metric_receipts(token_mint="TOKEN",pool="POOL",
                quote_mint="USDC",at=self.at,strategy="immediate",
                swaps=(swap,))

    def test_future_swap_cannot_enter_historical_volume(self):
        payload=b"record"
        swap=SwapVolumeEvidence("a"*64,"sig","rpc","POOL","TOKEN","USDC",
            1,self.at,self.at+timedelta(seconds=1),"finalized",
            Decimal("10"),"BUY",payload,sha256(payload).hexdigest())
        with self.assertRaisesRegex(ValueError,"futuros"):
            launch_metric_receipts(token_mint="TOKEN",pool="POOL",
                quote_mint="USDC",at=self.at,strategy="immediate",
                swaps=(swap,))

    def test_malformed_impact_input_fails(self):
        with self.assertRaises(ValueError):
            launch_metric_receipts(token_mint="TOKEN",pool="POOL",
                quote_mint="USDC",at=self.at,strategy="immediate",
                amount_in=Decimal("-1"))

if __name__ == "__main__":
    unittest.main()
