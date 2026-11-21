"""Two observed Solana CPMM four-account captures, adversarial comparison and SQLite."""
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path

from smart_money_radar.services.prospective_cpmm_history import (
    capture_from_raw,compare_captures,
)
from smart_money_radar.storage.cpmm_prospective_history import SQLiteCpmmProspectiveHistory

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
CUTOFF=datetime(2026,11,20,21,tzinfo=timezone.utc)
SLOTS=(471856996,471860762)


class RealCpmmHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=(ROOT/(SIG+".raw.json")).read_bytes()
        cls.old_manifest=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
        cls.bundles=[]
        for slot in SLOTS:
            folder=ROOT/("prospective-slot-"+str(slot))
            cls.bundles.append((
                (folder/"manifest.json").read_bytes(),
                (folder/"request.raw.json").read_bytes(),
                (folder/"response.raw.json").read_bytes(),
            ))

    def capture(self,index=0,**kwargs):
        m,q,r=self.bundles[index]
        x=dict(manifest_raw=m,request_raw=q,response_raw=r,
               original_transaction_raw=self.old,
               original_manifest=self.old_manifest,
               cutoff=CUTOFF,source_id="solana-public-mainnet-triton")
        x.update(kwargs)
        return capture_from_raw(**x)

    def compare(self,first=None,second=None,cutoff=CUTOFF):
        return compare_captures(first or self.capture(0),
                                second or self.capture(1),cutoff=cutoff)

    def test_real_slots_and_immutable_capture_ids(self):
        a,b=self.capture(0),self.capture(1)
        self.assertEqual((a.observation.slot,b.observation.slot),SLOTS)
        self.assertEqual(len(a.capture_id),64)
        self.assertNotEqual(a.capture_id,b.capture_id)
        self.assertEqual(a.capture_id,self.capture(0).capture_id)
        self.assertEqual(b.capture_id,self.capture(1).capture_id)

    def test_real_poolstate_changes_and_ammconfig_stable(self):
        x=self.compare()
        self.assertEqual(x.coverage,"PARTIAL")
        self.assertEqual(x.slot_delta,3766)
        self.assertTrue(x.poolstate_changed)
        self.assertFalse(x.ammconfig_changed)
        self.assertTrue(x.vault_input_changed)
        self.assertTrue(x.vault_output_changed)
        self.assertFalse(x.trade_fee_rate_changed)
        self.assertFalse(x.creator_fee_rate_changed)
        self.assertIn("slot_gap",x.reason_codes)

    def test_observed_exact_reserve_variations(self):
        x=self.compare()
        self.assertEqual(x.effective_input_delta_raw,316182281573)
        self.assertEqual(x.effective_output_delta_raw,-1052736738)
        self.assertEqual(x.vault_input_delta_raw,316403005899)
        self.assertEqual(x.vault_output_delta_raw,-1051096327)
        self.assertEqual(len(x.fee_counter_deltas_raw),6)
        # Fee-counter deltas must equal gross-vault minus effective-reserve
        # deltas. Token0 / token1 order can differ from input/output direction.
        a,b=self.capture(0).observation,self.capture(1).observation
        input_fee_change=(b.input_vault_raw-b.effective_input_raw) - (a.input_vault_raw-a.effective_input_raw)
        output_fee_change=(b.output_vault_raw-b.effective_output_raw) - (a.output_vault_raw-a.effective_output_raw)
        sums=(sum(x.fee_counter_deltas_raw[i] for i in (0,2,4)),
              sum(x.fee_counter_deltas_raw[i] for i in (1,3,5)))
        self.assertCountEqual(sums,(input_fee_change,output_fee_change))
        self.assertEqual(input_fee_change,220724326)
        self.assertEqual(output_fee_change,1640411)

    def test_two_real_snapshots_do_not_prove_event_continuity(self):
        x=self.compare()
        self.assertFalse(x.events_between_snapshots_complete)
        self.assertFalse(x.independently_authenticated)
        self.assertFalse(x.historical_original_swap_state_proven)
        self.assertFalse(x.economic_execution_authorized)

    def test_equal_slot_is_unknown(self):
        x=self.compare(second=self.capture(0))
        self.assertEqual(x.coverage,"UNKNOWN")
        self.assertIn("same_slot_no_proven_transition",x.reason_codes)

    def test_reversed_slots_are_conflicted(self):
        x=self.compare(first=self.capture(1),second=self.capture(0))
        self.assertEqual(x.coverage,"CONFLICT")
        self.assertIn("reversed_slots",x.reason_codes)

    def test_raw_tampering_rejected(self):
        m,q,r=self.bundles[0]
        with self.assertRaisesRegex(ValueError,"SHA da resposta"):
            self.capture(0,response_raw=r+b" ")

    def test_response_after_cutoff_rejected(self):
        t=datetime(2026,11,20,19,40,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,"cutoff"):
            self.capture(1,cutoff=t)
        x=self.compare(cutoff=t)
        self.assertEqual(x.coverage,"CONFLICT")
        self.assertIn("evidence_after_cutoff",x.reason_codes)

    def test_pool_identity_conflict(self):
        newer=self.capture(1)
        altered=replace(newer,observation=replace(
            newer.observation,pool="different_pool"))
        self.assertEqual(self.compare(second=altered).coverage,"CONFLICT")

    def test_vault_identity_in_request_rejected(self):
        m,q,r=self.bundles[0]
        q=json.loads(q)
        q["params"][0][2]="different_vault"
        qb=json.dumps(q).encode()
        mb=json.loads(m)
        mb["request_sha256"]=hashlib.sha256(qb).hexdigest()
        with self.assertRaisesRegex(ValueError,"manifesto e resposta|captura incompleta"):
            self.capture(0,manifest_raw=json.dumps(mb).encode(),request_raw=qb)

    def test_config_identity_changed_between_snapshots(self):
        x=self.capture(1)
        forged=replace(x,observation=replace(x.observation,amm_config="other"))
        self.assertEqual(self.compare(second=forged).coverage,"CONFLICT")

    def test_missing_account_is_rejected(self):
        m,q,r=self.bundles[0]
        obj=json.loads(r)
        obj["result"]["value"][2]=None
        raw=json.dumps(obj).encode()
        mb=json.loads(m)
        mb["response_sha256"]=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):
            self.capture(0,manifest_raw=json.dumps(mb).encode(),response_raw=raw)

    def test_provider_is_not_independently_verified(self):
        x=self.compare()
        self.assertFalse(x.independently_authenticated)
        self.assertIn("rpc_source_not_independently_attested",x.reason_codes)

    def test_determinism(self):
        self.assertEqual(self.compare(),self.compare())

    def test_sqlite_append_idempotent_and_reopen(self):
        a,b=self.capture(0),self.capture(1)
        x=self.compare(a,b)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"evidence.db"
            db=SQLiteCpmmProspectiveHistory(path)
            self.assertTrue(db.append_capture(a,manifest_raw=self.bundles[0][0]))
            self.assertTrue(db.append_capture(b,manifest_raw=self.bundles[1][0],
                                              prior_capture_id=a.capture_id,
                                              coverage="PARTIAL"))
            self.assertFalse(db.append_capture(a,manifest_raw=self.bundles[0][0]))
            self.assertTrue(db.append_delta(x))
            self.assertFalse(db.append_delta(x))
            self.assertEqual(db.integrity_check(),["ok"])
            db.close()
            db=SQLiteCpmmProspectiveHistory(path)
            self.assertEqual(db.get_capture(a.capture_id)["slot"],SLOTS[0])
            self.assertEqual(db.get_capture(b.capture_id)["prior_capture_id"],a.capture_id)
            self.assertEqual(db.get_delta(a.capture_id,b.capture_id)["slot_delta"],3766)
            db.close()

    def test_sqlite_rejects_duplicate_id_with_modified_raw(self):
        a=self.capture(0)
        with tempfile.TemporaryDirectory() as d:
            db=SQLiteCpmmProspectiveHistory(Path(d)/"evidence.sqlite")
            db.append_capture(a,manifest_raw=self.bundles[0][0])
            with self.assertRaisesRegex(ValueError,"conflito"):
                db.append_capture(a,manifest_raw=self.bundles[0][0]+b" ")
            db.close()

    def test_sqlite_rejects_reversed_order(self):
        a,b=self.capture(0),self.capture(1)
        with tempfile.TemporaryDirectory() as d:
            db=SQLiteCpmmProspectiveHistory(Path(d)/"evidence.sqlite")
            db.append_capture(b,manifest_raw=self.bundles[1][0])
            with self.assertRaises(ValueError):
                db.append_capture(a,manifest_raw=self.bundles[0][0],
                                  prior_capture_id=b.capture_id)
            db.close()



    def test_cm69_reconstruct_archived_capture_and_cutoff(self):
        a = self.capture(0)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.sqlite"
            db = SQLiteCpmmProspectiveHistory(path)
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            db.close()
            db = SQLiteCpmmProspectiveHistory(path)
            args = dict(original_transaction_raw=self.old,
                        original_manifest=self.old_manifest, cutoff=CUTOFF)
            self.assertEqual(db.reconstruct_capture(a.capture_id, **args), a)
            self.assertIsNone(db.reconstruct_capture("missing", **args))
            args["cutoff"] = a.observation.available_at - timedelta(seconds=1)
            with self.assertRaises(ValueError):
                db.reconstruct_capture(a.capture_id, **args)
            db.close()

    def test_cm69_reconstruct_rejects_metadata_conflict(self):
        a = self.capture(0)
        with tempfile.TemporaryDirectory() as d:
            db = SQLiteCpmmProspectiveHistory(Path(d) / "evidence.sqlite")
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            with db.connection:
                db.connection.execute("UPDATE prospective_cpmm_captures SET slot=slot+1")
            with self.assertRaisesRegex(ValueError, "metadata conflict"):
                db.reconstruct_capture(a.capture_id, original_transaction_raw=self.old,
                                       original_manifest=self.old_manifest, cutoff=CUTOFF)
            db.close()



    def test_cm69_launch_receipt_links_local_reserves_only(self):
        from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
        a = self.capture(0)
        acc = next(x.accounts for x in decode_raydium_cpmm_swaps(json.loads(self.old))
                   if x.accounts.pool_state == a.observation.pool)
        with tempfile.TemporaryDirectory() as d:
            db = SQLiteCpmmProspectiveHistory(Path(d) / "evidence.sqlite")
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            args = dict(pool=a.observation.pool, token_mint=acc.input_token_mint,
                        quote_mint=acc.output_token_mint, at=CUTOFF, strategy="immediate",
                        cpmm_history=db, capture_id=a.capture_id,
                        original_transaction_raw=self.old, original_manifest=self.old_manifest)
            receipt = launch_metric_receipts(**args)
            archive = receipt["economic_qualification"]["account_archive"]
            self.assertEqual(archive["status"], "LOCAL_PROSPECTIVE_BYTES_LINKED")
            self.assertEqual(archive["quote_reserve_raw"], str(a.observation.effective_output_raw))
            self.assertFalse(receipt["operational_authorized"])
            self.assertFalse(archive["historical_pre_swap_proven"])
            self.assertEqual(receipt["economic_qualification"]["quality"], "UNKNOWN")
            self.assertEqual(receipt, launch_metric_receipts(**args))
            args["quote_mint"] = "wrong"
            bad = launch_metric_receipts(**args)
            self.assertIn("cpmm_account_archive_conflict", bad["safety_blocks"])
            db.close()


if __name__=="__main__":
    unittest.main()
