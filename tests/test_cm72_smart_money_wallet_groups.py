from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

import test_cm38_economic_child_links as fixtures
from smart_money_radar.services.wallet_discovery import WalletDiscoveryPolicy, qualified_consensus_at


class SmartMoneyWalletGroupAuditTests(unittest.TestCase):
    def setUp(self):
        fixtures.EconomicChildEvidenceLinks.setUp(self)
        self.other_wallet = "other-public-wallet"
        self.wallets = (self.wallet, self.other_wallet)
        self.tx["transaction"]["message"]["accountKeys"] = list(self.wallets)
        self.evidence_id = fixtures.EconomicChildEvidenceLinks.capture(
            self, radar="smart_money", source="helius-wallet-rpc",
        )
        for wallet in self.wallets:
            self.store.save_observation(
                wallet, self.signature, self.tx, [], parse_status="ok", advance_checkpoint=False,
            )
            self.store.mark_processed(wallet, self.signature, evidence_id=self.evidence_id)
        self.cutoff = datetime.now(timezone.utc)

    def get_consensus(self, *, cutoff=None, limit=256):
        return qualified_consensus_at(
            self.store, as_of=cutoff or self.cutoff,
            policy=WalletDiscoveryPolicy(manual_wallets=self.wallets, max_receipts=limit),
            program="dex", pool="pool", base_mint="base", quote_mint="quote",
            window=timedelta(minutes=5), max_publication_delay=timedelta(minutes=1),
            min_confidence=Decimal(".8"),
        )

    def test_causal_shared_signature_is_observational_and_read_only(self):
        result = self.get_consensus()
        audit = result["wallet_group_audit"]
        self.assertEqual(audit["status"], "LOCAL_EVIDENCE_LINKED")
        self.assertEqual(audit["receipt"]["groups"], [sorted(self.wallets)])
        self.assertEqual(
            {item["evidence_id"] for item in audit["receipt"]["evidence"]},
            {self.evidence_id},
        )
        self.assertIn("archived_wallet_group_dependency", result["consensus"]["reasons"])
        self.assertEqual(result["qualified_wallets"], [])
        self.assertEqual(audit["independent_wallets"], 0)
        self.assertFalse(audit["operational_authorized"])
        self.assertFalse(result["consensus"]["actionable"])
        self.assertEqual(result, self.get_consensus())
        with self.store._connection_scope() as conn:
            self.assertIsNone(conn.execute(
                "SELECT name FROM sqlite_master WHERE name = 'cm38j_wallet_groups'",
            ).fetchone())

    def test_links_after_cutoff_and_overflow_publish_no_partial_group(self):
        earlier = self.get_consensus(cutoff=self.at)["wallet_group_audit"]
        self.assertEqual(earlier["reason"], "wallet_group_evidence_missing")
        bounded = self.get_consensus(limit=1)["wallet_group_audit"]
        self.assertEqual(bounded["reason"], "wallet_group_evidence_limit")
        self.assertEqual(bounded["status"], "UNKNOWN")
        self.assertIsNone(bounded["receipt"])

    def test_conflicting_archive_index_prevents_group_publication(self):
        with self.store._connection_scope() as conn, conn:
            conn.execute(
                "UPDATE cm38_rpc_observations SET radar = 'launch' WHERE evidence_id = ?",
                (self.evidence_id,),
            )
        result = self.get_consensus()
        audit = result["wallet_group_audit"]
        self.assertEqual(audit["status"], "CONFLICTED")
        self.assertIsNone(audit["receipt"])
        self.assertIn("wallet_group_evidence_conflict", result["consensus"]["reasons"])
        self.assertFalse(result["operational_authorized"])
