"""CLI acceptance checks for opt-in protected local paper replay."""
import contextlib
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
                 "quote_id": "q0", "market_at": "2026-11-19T00:00:00+00:00"},
                {"at": "2026-11-19T00:01:00+00:00", "price": "10.1",
                 "volume": "100", "entry_allowed": True, "quote_id": "q1",
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

    def run_cli(self):
        self.evidence.write_text(json.dumps(self.payload), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["paper-replay", str(self.scenario),
                  "--strict-evidence", str(self.evidence)])
        return json.loads(out.getvalue())

    def test_missing_evidence_does_not_fill_either_mode(self):
        report = self.run_cli()
        self.assertEqual(report["strict_evidence"]["verified_ticks"], 0)
        self.assertEqual(report["strict_evidence"]["rejected_evidence_ticks"], 2)
        self.assertEqual(report["immediate"]["fills"], [])
        self.assertEqual(report["confirmed"]["fills"], [])

    def test_missing_risk_blocks_verified_buy(self):
        start = "2026-11-19T00:00:00+00:00"
        next_at = "2026-11-19T00:01:00+00:00"
        self.payload["evidence_by_quote"] = {
            "q0": [{"evidence_id": "e0", "pool": "pool-a",
                    "observed_at": start, "available_at": start,
                    "source": "OBSERVED_MARKET_QUOTE", "is_observed_quote": True}],
            "q1": [{"evidence_id": "e1", "pool": "pool-a",
                    "observed_at": next_at, "available_at": next_at,
                    "source": "OBSERVED_MARKET_QUOTE", "is_observed_quote": True}],
        }
        report = self.run_cli()
        self.assertEqual(report["strict_evidence"]["rejected_risk_ticks"], 2)
        self.assertEqual(report["immediate"]["fills"], [])
        self.assertEqual(report["confirmed"]["fills"], [])

    def test_archive_with_strict_mode_rejected(self):
        self.evidence.write_text(json.dumps(self.payload), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "ainda não suporta"):
            main(["paper-replay", str(self.scenario), "--strict-evidence",
                  str(self.evidence), "--archive", str(self.root / "data.sqlite")])


if __name__ == "__main__":
    unittest.main()
