import base64
import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from smart_money_radar.domain.paper_evidence_replay import replay_with_evidence, replay_with_required_risk
from smart_money_radar.domain.paper_entry_risk_policy import EntryRiskLimits, EntryRiskSnapshot
from smart_money_radar.domain.paper_replay import PaperConfig, ReplayTick


class EvidenceReplayTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 19, tzinfo=timezone.utc)
        self.config = PaperConfig(
            initial_cash=Decimal("1000"), max_entry_cash=Decimal("100"),
            max_exposure=Decimal("0.5"),
        )

    def tick(self, minute, signal="NONE"):
        price = Decimal("10") + Decimal(minute) / 10
        return ReplayTick(
            at=self.start + timedelta(minutes=minute),
            market_at=self.start + timedelta(minutes=minute),
            price=price,
            volume=Decimal(100 + minute * 10),
            bid=price, ask=price, ask_size=Decimal(200),
            signal=signal, entry_allowed=True, quote_id=f"q{minute}",
        )

    def evidence(self, minute, *, source="OBSERVED_MARKET_QUOTE",
                 available_minute=None, tick=None):
        tick = self.tick(minute) if tick is None else tick
        observed = (tick.market_at or tick.at).isoformat()
        available = (tick.at if available_minute is None else self.tick(available_minute).at).isoformat()
        raw = json.dumps({
            "quote_id": tick.quote_id, "pool": "pool-a",
            "observed_at": observed, "available_at": available,
            "price": str(tick.price), "volume": str(tick.volume),
            **{name: str(value) if (value := getattr(tick, name)) is not None else None
               for name in ("bid", "ask", "bid_size", "ask_size")},
        }).encode()
        return [{
            "evidence_id": f"e{minute}", "pool": "pool-a",
            "observed_at": observed, "available_at": available,
            "source": source, "is_observed_quote": source == "OBSERVED_MARKET_QUOTE",
            "raw_capture_base64": base64.b64encode(raw).decode(),
            "raw_capture_sha256": hashlib.sha256(raw).hexdigest(),
        }]

    def replay(self, evidence, **kwargs):
        ticks = [self.tick(0, "BUY"), self.tick(1), self.tick(2), self.tick(3)]
        return replay_with_evidence(
            ticks, evidence, config=self.config, expected_pool="pool-a", **kwargs,
        )

    def test_both_modes_can_trade_on_verified_observations(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        result = self.replay(records)
        self.assertTrue(any(f.side == "BUY" for f in result["immediate"].fills))
        self.assertTrue(any(f.side == "BUY" for f in result["confirmed"].fills))

    def test_missing_evidence_blocks_both_modes(self):
        result = self.replay({})
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_future_and_model_evidence_cannot_be_used_as_observed(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        records["q0"] = self.evidence(0, available_minute=2)
        result = self.replay(records)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)
        records["q0"] = self.evidence(0, source="MODEL_ESTIMATE_NOT_OBSERVED")
        result = self.replay(records)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_unverified_future_price_cannot_fill_pending_buy(self):
        records = {"q0": self.evidence(0), "q2": self.evidence(2),
                   "q3": self.evidence(3)}
        result = self.replay(records)
        fills = result["immediate"].fills
        self.assertTrue(fills)
        self.assertEqual(fills[0].filled_at, self.start + timedelta(minutes=2))
        self.assertEqual(result["rejected_evidence_ticks"], 1)

    def test_unverified_price_cannot_trigger_exit_or_valuation(self):
        records = {"q0": self.evidence(0), "q1": self.evidence(1)}
        result = self.replay(records)
        self.assertEqual(result["verified_ticks"], 2)
        self.assertEqual(result["rejected_evidence_ticks"], 2)
        self.assertEqual(result["immediate"].final_equity,
                         self.config.initial_cash - Decimal("100")
                         + result["immediate"].open_quantity * Decimal("10.1"))

    def test_as_of_cutoff_preserves_only_available_history(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        result = self.replay(records, as_of=self.start + timedelta(minutes=1))
        self.assertEqual(result["verified_ticks"], 2)
        self.assertEqual(result["excluded_after_cutoff"], 2)
        self.assertEqual(result["immediate"].fills[0].filled_at,
                         self.start + timedelta(minutes=1))

    def test_as_of_rejects_naive_datetime(self):
        with self.assertRaisesRegex(ValueError, "as_of"):
            self.replay({}, as_of=datetime(2026, 11, 19))

    def test_shared_risk_policy_blocks_both_modes(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        blocked = EntryRiskSnapshot(
            Decimal("1000"), Decimal("100"), Decimal("0"),
            Decimal("20"), Decimal("2000"), True, True,
        )
        risk = {f"q{i}": blocked for i in range(4)}
        result = self.replay(records, risk_limits=limits, risk_by_quote=risk)
        self.assertEqual(result["rejected_risk_ticks"], 4)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_missing_risk_snapshot_blocks_entry(self):
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        result = self.replay(records, risk_limits=limits, risk_by_quote={})
        self.assertEqual(result["rejected_risk_ticks"], 4)
        self.assertFalse(result["immediate"].fills)
        self.assertFalse(result["confirmed"].fills)

    def test_strict_entry_point_requires_risk_configuration(self):
        ticks = [self.tick(0, "BUY"), self.tick(1)]
        records = {f"q{i}": self.evidence(i) for i in range(2)}
        with self.assertRaisesRegex(ValueError, "política de risco obrigatória"):
            replay_with_required_risk(
                ticks, records, config=self.config, expected_pool="pool-a",
                risk_limits=None, risk_by_quote={},
            )
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        with self.assertRaisesRegex(ValueError, "snapshots de risco obrigatórios"):
            replay_with_required_risk(
                ticks, records, config=self.config, expected_pool="pool-a",
                risk_limits=limits, risk_by_quote=None,
            )

    def test_strict_entry_point_requires_observed_quote(self):
        ticks = [self.tick(0, "BUY"), self.tick(1)]
        records = {f"q{i}": self.evidence(i, source="MODEL_ESTIMATE_NOT_OBSERVED")
                   for i in range(2)}
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        risk = EntryRiskSnapshot(Decimal("1000"), Decimal("100"), Decimal("0"),
                                 Decimal("20"), Decimal("2000"), False, True)
        with self.assertRaisesRegex(ValueError, "evidência inválida"):
            replay_with_required_risk(
                ticks, records, config=self.config, expected_pool="pool-a",
                risk_limits=limits, risk_by_quote={"q0": risk, "q1": risk},
            )

    def test_strict_rejects_invalid_middle_evidence_before_replay(self):
        ticks = [self.tick(i, "BUY" if i == 0 else "NONE") for i in range(4)]
        records = {f"q{i}": self.evidence(i) for i in range(4)}
        records["q1"] = self.evidence(1, available_minute=3)
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        risk = EntryRiskSnapshot(Decimal("1000"), Decimal("100"), Decimal("0"),
                                 Decimal("20"), Decimal("2000"), False, True)
        with self.assertRaisesRegex(ValueError, "evidência inválida"):
            replay_with_required_risk(
                ticks, records, config=self.config, expected_pool="pool-a",
                risk_limits=limits, risk_by_quote={f"q{i}": risk for i in range(4)},
            )

    def test_strict_rejects_model_quote_before_replay(self):
        ticks = [self.tick(i) for i in range(2)]
        records = {f"q{i}": self.evidence(i) for i in range(2)}
        records["q1"] = self.evidence(1, source="MODEL_ESTIMATE_NOT_OBSERVED")
        limits = EntryRiskLimits(Decimal("0.2"), Decimal("0.05"),
                                 Decimal("100"), Decimal("1000"))
        risk = EntryRiskSnapshot(Decimal("1000"), Decimal("100"), Decimal("0"),
                                 Decimal("20"), Decimal("2000"), False, True)
        with self.assertRaisesRegex(ValueError, "evidência inválida"):
            replay_with_required_risk(
                ticks, records, config=self.config, expected_pool="pool-a",
                risk_limits=limits, risk_by_quote={f"q{i}": risk for i in range(2)},
            )

    def strict(self, ticks, *, snapshot=None, limits=None, as_of=None):
        snapshot = snapshot or EntryRiskSnapshot(
            Decimal("1000"), Decimal("1"), Decimal("0"),
            Decimal("0"), Decimal("2000"), False, True,
        )
        limits = limits or EntryRiskLimits(Decimal("0.2"), Decimal("0.02"),
                                           Decimal("100"), Decimal("50"))
        records = {tick.quote_id: self.evidence(i, tick=tick) for i, tick in enumerate(ticks)
                   if as_of is None or tick.at <= as_of}
        return replay_with_required_risk(
            ticks, records, config=self.config, expected_pool="pool-a",
            risk_limits=limits, risk_by_quote={key: snapshot for key in records}, as_of=as_of,
        )

    def test_shared_actual_fill_risk_rejects_position_slippage_and_liquidity(self):
        ticks = [self.tick(0, "BUY"), self.tick(1), self.tick(2)]
        for limits, reason in (
            (EntryRiskLimits(Decimal(".05"), Decimal(".05"), Decimal(200), Decimal(50)),
             "position_limit"),
            (EntryRiskLimits(Decimal(".20"), Decimal(".05"), Decimal(50), Decimal(50)),
             "slippage_limit"),
        ):
            result = self.strict(ticks, limits=limits)
            for mode in ("immediate", "confirmed"):
                self.assertFalse(result[mode].fills)
                self.assertEqual(result[mode].decisions[-1].reason, reason)
        snapshot = EntryRiskSnapshot(Decimal(1000), Decimal(1), Decimal(0),
                                     Decimal(0), Decimal(75), False, True)
        result = self.strict(ticks, snapshot=snapshot)
        for mode in ("immediate", "confirmed"):
            self.assertFalse(result[mode].fills)
            self.assertEqual(result[mode].decisions[-1].reason, "insufficient_order_liquidity")

    def test_strict_fill_rejects_missing_bid_ask_or_depth(self):
        for missing in ({"ask_size": None}, {"bid": None, "ask": None}):
            with self.subTest(fields=missing):
                ticks = [self.tick(0, "BUY"), replace(self.tick(1), **missing),
                         replace(self.tick(2), **missing)]
                result = self.strict(ticks)
                for mode in ("immediate", "confirmed"):
                    self.assertFalse(result[mode].fills)
                    self.assertEqual(result[mode].decisions[-1].reason, "quote_depth_missing")

    def test_strict_fill_uses_actual_depth_not_declared_liquidity(self):
        ticks = [self.tick(0, "BUY"), replace(self.tick(1), ask_size=Decimal(11)),
                 replace(self.tick(2), ask_size=Decimal(11))]
        limits = EntryRiskLimits(Decimal(".20"), Decimal(".05"), Decimal(100), Decimal(200))
        result = self.strict(ticks, limits=limits)
        for mode in ("immediate", "confirmed"):
            self.assertFalse(result[mode].fills)
            self.assertEqual(result[mode].decisions[-1].reason, "liquidity_limit")

    def test_strict_uses_supplied_emergency_halt_for_open_position(self):
        ticks = [self.tick(0, "BUY"), self.tick(1), self.tick(2),
                 replace(self.tick(3), entry_allowed=False), self.tick(4)]
        records = {tick.quote_id: self.evidence(i, tick=tick) for i, tick in enumerate(ticks)}
        limits = EntryRiskLimits(Decimal(".20"), Decimal(".05"), Decimal(100), Decimal(50))
        active = EntryRiskSnapshot(Decimal(1000), Decimal(1), Decimal(0),
                                   Decimal(0), Decimal(2000), False, True)
        snapshots = {key: active for key in records}
        snapshots["q3"] = replace(active, emergency_halt=True)
        result = replay_with_required_risk(
            ticks, records, config=self.config, expected_pool="pool-a",
            risk_limits=limits, risk_by_quote=snapshots,
        )
        for mode in ("immediate", "confirmed"):
            self.assertEqual([fill.side for fill in result[mode].fills], ["BUY", "SELL"])
            self.assertEqual(result[mode].fills[-1].reason, "kill_switch")

    def test_daily_loss_uses_actual_closed_pnl_and_resets_at_utc_midnight(self):
        ticks = [self.tick(0, "BUY"), self.tick(1), self.tick(2),
                 replace(self.tick(3, "SELL"), price=Decimal(8), bid=Decimal(8), ask=Decimal(8)),
                 replace(self.tick(4), price=Decimal(8), bid=Decimal(8), ask=Decimal(8)),
                 self.tick(5, "BUY"), self.tick(6), self.tick(7)]
        result = self.strict(ticks)
        for mode in ("immediate", "confirmed"):
            self.assertEqual([fill.side for fill in result[mode].fills], ["BUY", "SELL"])
            self.assertEqual(result[mode].decisions[-1].reason, "daily_loss_limit")
        next_day = ticks[:5] + [
            replace(tick, at=tick.at + timedelta(days=1), market_at=tick.market_at + timedelta(days=1))
            for tick in ticks[5:]
        ]
        result = self.strict(next_day)
        for mode in ("immediate", "confirmed"):
            self.assertEqual([fill.side for fill in result[mode].fills], ["BUY", "SELL", "BUY"])

    def test_strict_cutoff_ignores_missing_future_records(self):
        ticks = [self.tick(0, "BUY"), self.tick(1), self.tick(2)]
        result = self.strict(ticks, as_of=ticks[1].at)
        self.assertEqual(result["excluded_after_cutoff"], 1)
        self.assertEqual(result["verified_ticks"], 2)
        self.assertEqual(len(result["immediate"].fills), 1)

    def test_model_mode_explicitly_non_executable(self):
        records = {f"q{i}": self.evidence(i, source="MODEL_ESTIMATE_NOT_OBSERVED")
                   for i in range(4)}
        result = self.replay(records, require_observed_quote=False)
        self.assertEqual(result["evidence_policy"], "MODEL_ALLOWED_PAPER_ONLY")
        self.assertTrue(result["immediate"].fills)


if __name__ == "__main__":
    unittest.main()
