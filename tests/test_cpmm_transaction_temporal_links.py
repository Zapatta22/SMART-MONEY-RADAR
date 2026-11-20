"""Real CPMM RPC transactions and conservative account-write separation."""
import json
import unittest
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path

from smart_money_radar.services.cpmm_transaction_account_links import bind_cpmm_transaction_accounts
from smart_money_radar.services.cpmm_transaction_boundary_bridge import compare_cpmm_transaction_boundaries
from smart_money_radar.data_sources.geyser_account_updates import NormalizedAccountUpdate

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
FOLDER=ROOT/"cpmm-interval-471856996-471860762"
CUTOFF=datetime(2026,11,20,21,tzinfo=timezone.utc)
POOL="CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu"
CONFIG="D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2"
HIGH="C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU"
WSOL="8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG"
HIGH_MINT="7ymF66Z6VhgNiwadtVhjTtT6U7iQRpSxeiRrhfufhigh"
WSOL_MINT="So11111111111111111111111111111111111111112"
PREV="Y8ZGmqJCsCS4tWP181bQoxUB2HUr5k5gGJ3VnQxjCcnUk8xd7QWbjxNUXsJSgQ417drRHXTJPSNfDh15VGoN17W"
NEXT="4WuWPyiaKxgTLxBpQvauqJAzbCgyk7gZjjn7vDdVSYeWuNuM8UkeVR1aN6536MA6yg5RGNehgneX65AsDJJSrjET"

class CpmmTransactionLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reports=json.loads((FOLDER/"transactions/manifest.json").read_bytes())["results"]
        cls.reports={x["signature"]:x for x in reports}
        cls.raws={sig:(FOLDER/"transactions"/(sig+".response.raw.json")).read_bytes()
                  for sig in (PREV,NEXT)}
        cls.nullsig="3JSyzXZWsNBxqkqRt4Gbri2B3ZuanWq1z8f8Vgbi6zCNoCKys1xT325UHN9Wrkd4oeJkiSuXdTBWfmqZjsW66Bz4"
        cls.nullraw=(FOLDER/"transactions"/(cls.nullsig+".response.raw.json")).read_bytes()

    def bind(self,signature=PREV,raw=None,**kwargs):
        opts=dict(raw=self.raws[signature] if raw is None else raw,
                  signature=signature,listed_slot=self.reports[signature]["listed_slot"],
                  pool=POOL,config=CONFIG,vault_high=HIGH,vault_wsol=WSOL,
                  high_mint=HIGH_MINT,wsol_mint=WSOL_MINT,
                  available_at=datetime.fromisoformat(self.reports[signature]["available_at"]),
                  cutoff=CUTOFF,source_id="solana-public-mainnet-triton")
        opts.update(kwargs)
        return bind_cpmm_transaction_accounts(**opts)

    def bridge(self,**kwargs):
        opts=dict(previous_raw=self.raws[PREV],next_raw=self.raws[NEXT],
                  previous_signature=PREV,next_signature=NEXT,
                  previous_slot=471860518,next_slot=471860536,
                  pool=POOL,vault_mints={HIGH:HIGH_MINT,WSOL:WSOL_MINT},
                  previous_available_at=datetime.fromisoformat(self.reports[PREV]["available_at"]),
                  next_available_at=datetime.fromisoformat(self.reports[NEXT]["available_at"]),
                  cutoff=CUTOFF)
        opts.update(kwargs)
        return compare_cpmm_transaction_boundaries(**opts)

    def test_real_transaction_vault_balances_and_categorization(self):
        x=self.bind()
        self.assertEqual(x.status,"OBSERVED_TX_BOUNDARY")
        self.assertEqual(len(x.links),4)
        self.assertEqual({a.account_role for a in x.links},{"POOLSTATE","AMMCONFIG","VAULT_HIGH","VAULT_WSOL"})
        vaults={a.account:a for a in x.links}
        self.assertEqual(vaults[HIGH].transaction_delta_raw,420832697460)
        self.assertEqual(vaults[WSOL].transaction_delta_raw,-1411073214)
        self.assertFalse(any(a.account_write_confirmed for a in x.links))
        self.assertEqual(vaults[POOL].status,"PROBABLE_INCOMPLETE")

    def test_second_tx_balance_deltas_are_real(self):
        x=self.bind(signature=NEXT)
        v={z.account:z.transaction_delta_raw for z in x.links}
        self.assertEqual(v[HIGH],130978120008)
        self.assertEqual(v[WSOL],-436023113)
        self.assertFalse(x.write_stream_complete)
        self.assertFalse(x.execution_authorized)

    def test_exact_between_tx_vault_boundary_match(self):
        x=self.bridge()
        self.assertEqual(x.status,"OBSERVED_BOUNDARY_MATCH")
        self.assertEqual(len(x.vaults),2)
        self.assertEqual({a.vault:a.previous_post_raw for a in x.vaults},
                         {HIGH:76688954539225,WSOL:256828166819})
        self.assertEqual({a.vault:a.next_pre_raw for a in x.vaults},
                         {HIGH:76688954539225,WSOL:256828166819})
        self.assertFalse(x.intervening_writes_excluded)
        self.assertFalse(x.state_write_proven)
        self.assertFalse(x.interval_coverage_complete)

    def test_tampered_vault_balance_produces_mismatch_not_proof(self):
        payload=json.loads(self.raws[NEXT])
        payload["result"]["meta"]["preTokenBalances"][1]["uiTokenAmount"]["amount"]="1"
        x=self.bridge(next_raw=json.dumps(payload).encode())
        self.assertIn(x.status,("PARTIAL","CONFLICT"))
        self.assertFalse(x.interval_coverage_complete)

    def test_other_pool_not_attributed(self):
        self.assertEqual(self.bind(pool="other-pool").status,"UNKNOWN")
        self.assertEqual(self.bridge(pool="other-pool").status,"CONFLICT")

    def test_wrong_vault_or_mint_conflicts(self):
        self.assertEqual(self.bind(vault_high="wrong").status,"CONFLICT")
        self.assertEqual(self.bind(high_mint="wrong").status,"CONFLICT")

    def test_signature_mismatch_rejected(self):
        self.assertEqual(self.bind(signature=PREV,listed_slot=471860536).status,"CONFLICT")
        self.assertEqual(self.bridge(previous_signature="wrong").status,"CONFLICT")

    def test_rpc_null_does_not_promote(self):
        x=self.bind(signature=PREV,raw=self.nullraw)
        self.assertEqual(x.status,"UNKNOWN")

    def test_same_slot_never_implies_order(self):
        x=self.bridge(next_slot=471860518)
        self.assertEqual(x.status,"UNKNOWN")
        self.assertFalse(x.intervening_writes_excluded)

    def test_after_cutoff_fails_closed(self):
        x=self.bind(cutoff=datetime(2026,11,20,20,tzinfo=timezone.utc))
        self.assertEqual(x.status,"CONFLICT")
        self.assertEqual(self.bridge(cutoff=datetime(2026,11,20,20,tzinfo=timezone.utc)).status,"CONFLICT")

    def test_unverified_gyser_write_claim_cannot_upgrade(self):
        u=NormalizedAccountUpdate(pubkey=HIGH,slot=471860518,write_version=7,
           txn_signature=PREV,lamports=2039280,owner="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
           executable=False,rent_epoch=0,data=b"synthetic",stream_id="demo",stream_sequence=1,
           source="unverified")
        x=self.bind(account_updates=(u,))
        self.assertFalse(any(a.account_write_confirmed for a in x.links))
        self.assertIn("provider_write_provenance_unattested",
                      next(a for a in x.links if a.account==HIGH).reason_codes)

    def test_no_real_gyser_writes_available(self):
        self.assertTrue(all("geyser_account_write_missing" in a.reason_codes
                            for a in self.bind().links))

    def test_deterministic_replay(self):
        self.assertEqual(self.bind(),self.bind())
        self.assertEqual(self.bridge(),self.bridge())

if __name__=="__main__":
    unittest.main()
