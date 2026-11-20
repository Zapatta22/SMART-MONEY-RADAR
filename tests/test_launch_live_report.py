"""Independent offline acceptance tests for secret-free real-validation manifests."""
import hashlib
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from smart_money_radar.cli import main
from smart_money_radar.services.launch_live_monitor import LaunchLiveMetrics
from smart_money_radar.services.launch_live_report import save_launch_live_report


class SolanaLiveReportTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "evidence" / "live-validation.json"
        self.metrics = LaunchLiveMetrics(
            sessions=1, reconnects=1, notifications=0,
            reconciliations=1, recovered_deliveries=0,
            incomplete_reconciliations=0,
            last_reconciliation_seconds=0.15,
        )
        self.now = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)

    def write(self, *, integrity=None, source="public-node-1"):
        return save_launch_live_report(
            self.output, source_id=source, cluster="mainnet",
            addresses=("public-address",), started_at=self.now,
            ended_at=self.now, metrics=self.metrics,
            rpc_cursors={"public-address": None},
            sqlite_integrity=["ok"] if integrity is None else integrity,
        )

    def test_manifest_has_unknown_coverage_and_no_raw_source_or_secrets(self):
        manifest = self.write(source="secret-like-source")
        saved = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(saved, manifest)
        self.assertEqual(saved["schema"], "smr.solana_live_observation.v1")
        self.assertEqual(saved["coverage"], "UNKNOWN")
        self.assertEqual(saved["provenance"],
                         "RPC_PROVIDER_ASSERTED_NOT_INDEPENDENTLY_ATTESTED")
        self.assertIsNone(saved["metrics"]["notification_to_finalized_p95_ms"])
        self.assertEqual(
            saved["source_id_sha256"],
            hashlib.sha256(b"secret-like-source").hexdigest(),
        )
        raw_file = self.output.read_text(encoding="utf-8")
        self.assertNotIn("secret-like-source", raw_file)
        self.assertNotIn("api-key=", raw_file)
        self.assertIn("operator_opt_in", raw_file)

    def test_report_refuses_bad_database_and_keeps_prior_manifest(self):
        self.write()
        prior = self.output.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "integridade SQLite"):
            self.write(integrity=["database disk image is malformed"])
        self.assertEqual(self.output.read_bytes(), prior)
        self.assertEqual(list(self.output.parent.glob("*.tmp")), [])

    def test_report_rejects_non_json_destination(self):
        with self.assertRaises(ValueError):
            save_launch_live_report(
                Path(self.output.parent) / "unsafe.txt",
                source_id="source", cluster="mainnet", addresses=("a",),
                started_at=self.now, ended_at=self.now,
                metrics=self.metrics, rpc_cursors={}, sqlite_integrity=["ok"],
            )

    def test_cli_requires_bounded_duration_for_artifact_export(self):
        with self.assertRaises(SystemExit) as raised:
            main(["launch-live", "public-address", "--source-id", "source",
                  "--metrics-json", str(self.output)])
        self.assertIn("--metrics-json exige", str(raised.exception))

    def test_invalid_duration_rejected_before_external_access(self):
        with self.assertRaises(SystemExit) as raised:
            main(["launch-live", "public-address", "--source-id", "source",
                  "--duration-seconds", "0"])
        self.assertIn("--duration-seconds", str(raised.exception))

    def test_network_remains_opt_in(self):
        with patch.dict(os.environ, {"SMR_ALLOW_NETWORK": "false", "HELIUS_API_KEY": ""}):
            with self.assertRaises(SystemExit) as raised:
                main(["launch-live", "public-address", "--source-id", "source",
                      "--duration-seconds", "1",
                      "--metrics-json", str(self.output)])
        self.assertIn("Acesso à rede desativado", str(raised.exception))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
