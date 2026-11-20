"""CLI acceptance checks for opt-in protected local paper replay."""
import base64
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from smart_money_radar.cli import main


class StrictPaperCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scenario = self.root / "scenario.json"
        self.evidence = self.root / "evidence.json"
        self.scenario.write_text(json.dumps({
            "config": {
                "initial_cash": "1000", "max_entry_cash": "100",
                "max_exposure": "0.5"
            },
            "ticks": [
                {"at": "2026-11-19T00:00:00+00:00", "price": "10",
                 "volume": "100", "signal": "BUY", "entry_allowed": True,
                 "quote_id": "q0", "bid": "10", "ask": "10", "bid_size": "200", "ask_size": "200", "market_at": "2026-11-19T00:00:00+00:00"},
                {"at": "2026-11-19T00:01:00+00:00", "price": "10.1",
                 "volume": "100", "entry_allowed": True, "quote_id": "q1",
                 "bid": "10.1", "ask": "10.1", "bid_size": "200", "ask_size": "200",
                 "market_at": "2026-11-19T00:01:00+00:00"},
            ],
        }), encoding="utf-8")
        self.payload = {
            "pool": "pool-a",
            "risk_limits": {
                "max_position_fraction": "0.2",
                "max_daily_loss_fraction": "0.05",
                "max_slippage_bps": "100",
                "min_liquidity_quote": "1000",
            },
            "risk_by_quote": {},
            "evidence_by_quote": {},
        }

    def observed_record(self, i, at):
        tick = json.loads(self.scenario.read_text())["ticks"][i]
        quote = {key: tick[key] for key in ("quote_id", "price", "volume", "bid", "ask", "bid_size", "ask_size")}
        quote.update(pool="pool-a", observed_at=at, available_at=at)
        capture = json.dumps(quote).encode()
        return {
            "evidence_id": f"e{i}", "pool": "pool-a",
            "observed_at": at, "available_at": at,
            "source": "OBSERVED_MARKET_QUOTE", "is_observed_quote": True,
            "raw_capture_base64": base64.b64encode(capture).decode(),
            "raw_capture_sha256": hashlib.sha256(capture).hexdigest(),
        }

    def run_cli(self, *options):
        self.evidence.write_text(json.dumps(self.payload), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["paper-replay", str(self.scenario),
                  "--strict-evidence", str(self.evidence), *options])
        return json.loads(out.getvalue())

    def test_missing_evidence_does_not_fill_either_mode(self):
        with self.assertRaisesRegex(SystemExit, "lacuna de evidência"):
            self.run_cli()

    def test_missing_risk_blocks_verified_buy(self):
        start = "2026-11-19T00:00:00+00:00"
        next_at = "2026-11-19T00:01:00+00:00"
        self.payload["evidence_by_quote"] = {
            "q0": [self.observed_record(0, start)], "q1": [self.observed_record(1, next_at)],
        }
        with self.assertRaisesRegex(SystemExit, "lacuna de risco"):
            self.run_cli()

    def test_valid_strict_evidence_and_risk_allow_immediate_fill(self):
        for i, at in enumerate(("2026-11-19T00:00:00+00:00",
                                "2026-11-19T00:01:00+00:00")):
            self.payload["evidence_by_quote"][f"q{i}"] = [self.observed_record(i, at)]
            self.payload["risk_by_quote"][f"q{i}"] = {
                "equity": "1000", "proposed_notional": "100",
                "daily_realized_pnl": "0", "estimated_slippage_bps": "10",
                "verified_liquidity_quote": "2000",
                "emergency_halt": False, "evidence_verified": True,
            }
        report = self.run_cli()
        self.assertEqual(report["strict_evidence"]["verified_ticks"], 2)
        self.assertEqual(report["strict_evidence"]["rejected_risk_ticks"], 0)
        self.assertEqual(report["immediate"]["fills"][0]["side"], "BUY")
        cutoff = self.run_cli("--as-of", "2026-11-19T00:00:00+00:00")
        self.assertEqual(cutoff["strict_evidence"]["verified_ticks"], 1)
        self.assertEqual(cutoff["immediate"]["fills"], [])
        self.assertEqual(cutoff["strict_evidence"]["excluded_after_cutoff"], 1)
        original = self.scenario.read_text()
        future_bad = json.loads(original)
        future_bad["ticks"][1]["price"] = "invalid"
        self.scenario.write_text(json.dumps(future_bad))
        self.payload["risk_by_quote"]["q1"] = {"equity": "invalid"}
        rerun = self.run_cli("--as-of", "2026-11-19T00:00:00+00:00")
        for section in ("immediate", "confirmed", "strict_evidence"):
            self.assertEqual(cutoff[section], rerun[section])
        self.scenario.write_text(original)
        self.payload["risk_by_quote"]["q1"] = self.payload["risk_by_quote"]["q0"].copy()
        self.payload["evidence_by_quote"]["q1"][0]["raw_capture_sha256"] = "0" * 64
        with self.assertRaisesRegex(SystemExit, "evidência inválida no histórico protegido"):
            self.run_cli()

    def test_emergency_halt_blocks_immediate_fill(self):
        for i, at in enumerate(("2026-11-19T00:00:00+00:00",
                                "2026-11-19T00:01:00+00:00")):
            self.payload["evidence_by_quote"][f"q{i}"] = [self.observed_record(i, at)]
            self.payload["risk_by_quote"][f"q{i}"] = {
                "equity": "1000", "proposed_notional": "100",
                "daily_realized_pnl": "0", "estimated_slippage_bps": "10",
                "verified_liquidity_quote": "2000",
                "emergency_halt": True, "evidence_verified": True,
            }
        report = self.run_cli()
        self.assertEqual(report["strict_evidence"]["rejected_risk_ticks"], 2)
        self.assertEqual(report["immediate"]["fills"], [])
    def test_archive_with_strict_mode_rejected(self):
        self.evidence.write_text(json.dumps(self.payload), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "ainda não suporta"):
            main(["paper-replay", str(self.scenario), "--strict-evidence",
                  str(self.evidence), "--archive", str(self.root / "data.sqlite")])


if __name__ == "__main__":
    unittest.main()
