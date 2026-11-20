"""Real archived Solana pool signatures/transactions; adversarial and SQLite tests."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from smart_money_radar.services.prospective_cpmm_history import capture_from_raw,compare_captures
from smart_money_radar.services.cpmm_interval_transaction_audit import reconcile_interval_transactions
from smart_money_radar.storage.cpmm_prospective_history import SQLiteCpmmProspectiveHistory
from smart_money_radar.storage.cpmm_interval_evidence import append_interval_audit,get_interval_audit,init_interval_schema

ROOT=Path(__file__).resolve().parents[1]/"data/evidence/mainnet/2026-11-20"
INTERVAL=ROOT/"cpmm-interval-471856996-471860762"
SIG="23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM"
CUTOFF=datetime(2026,11,20,21,tzinfo=timezone.utc)

class RealIntervalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        first=json.loads((ROOT/"first-proof.manifest.json").read_bytes())
        tx=(ROOT/(SIG+".raw.json")).read_bytes()
        cls.captures=[]
        cls.manifest_raws=[]
        for slot in (471856996,471860762):
            folder=ROOT/("prospective-slot-"+str(slot))
            m=(folder/"manifest.json").read_bytes()
            cls.manifest_raws.append(m)
            cls.captures.append(capture_from_raw(
                manifest_raw=m,request_raw=(folder/"request.raw.json").read_bytes(),
                response_raw=(folder/"response.raw.json").read_bytes(),
                original_transaction_raw=tx,original_manifest=first,
                cutoff=CUTOFF,source_id="solana-public-mainnet-triton"))
        cls.delta=compare_captures(*cls.captures,cutoff=CUTOFF)
        cls.listing_manifest=json.loads((INTERVAL/"manifest.json").read_bytes())
        cls.listing_raw=(INTERVAL/"response.raw.json").read_bytes()
        cls.tx_manifest=json.loads((INTERVAL/"transactions/manifest.json").read_bytes())
        cls.tx_raws={x["signature"]:(INTERVAL/"transactions"/(x["signature"]+".response.raw.json")).read_bytes()
                     for x in cls.tx_manifest["results"] if x.get("response_sha256")}

    def run_audit(self,**changes):
        opts=dict(first=self.captures[0],second=self.captures[1],
                  delta=self.delta,listing_manifest=self.listing_manifest,
                  listing_raw=self.listing_raw,tx_manifest=self.tx_manifest,
                  tx_responses=self.tx_raws,cutoff=CUTOFF)
        opts.update(changes)
        return reconcile_interval_transactions(**opts)

    def test_real_three_signatures_and_two_observed(self):
        summary,rows=self.run_audit()
        self.assertEqual(summary.listed_count,3)
        self.assertEqual(summary.verified_transactions,2)
        self.assertEqual(summary.unresolved_transactions,1)
        self.assertEqual(summary.slot_range,(471856996,471860762))
        self.assertEqual(summary.coverage,"PARTIAL")
        self.assertEqual([(r.listed_slot,r.status) for r in rows],
                         [(471857488,"UNKNOWN"),(471860518,"OBSERVED"),(471860536,"OBSERVED")])

    def test_real_pool_instruction_not_merely_account_key(self):
        s,events=self.run_audit()
        self.assertEqual(s.pool_instruction_verified,2)
        self.assertTrue(all(e.pool_instruction_verified for e in events if e.status=="OBSERVED"))

    def test_partial_listing_and_write_stream_no_complete(self):
        a,_=self.run_audit()
        self.assertIn("pagination_not_proven_exhausted",a.reasons)
        self.assertIn("account_writes_not_recorded",a.reasons)
        self.assertFalse(a.account_write_stream_complete)
        self.assertFalse(a.transaction_order_proven)
        self.assertFalse(a.operation_authorized)
        self.assertIsNone(a.economic_residual_high_raw)
        self.assertIsNone(a.economic_residual_wsol_lamports)

    def test_duplicate_signature_rejected(self):
        x=json.loads(json.dumps(self.tx_manifest))
        x["results"][1]["signature"]=x["results"][0]["signature"]
        with self.assertRaisesRegex(ValueError,"duplicada"):
            self.run_audit(tx_manifest=x)

    def test_mismatching_slot_from_rpc_fails_closed(self):
        key=next(iter(self.tx_raws))
        x=json.loads(self.tx_raws[key])
        x["result"]["slot"]+=1
        edited=json.dumps(x).encode()
        t=json.loads(json.dumps(self.tx_manifest))
        next(row for row in t["results"] if row["signature"]==key)["response_sha256"]=sha256(edited).hexdigest()
        s,rows=self.run_audit(tx_responses={**self.tx_raws,key:edited},tx_manifest=t)
        self.assertEqual(s.coverage,"CONFLICT")
        self.assertTrue(any("transaction_identity_or_success_conflict" in row.reasons for row in rows))

    def test_wrong_pool_scope_is_rejected(self):
        a=dict(self.listing_manifest,pool="different-pool")
        with self.assertRaisesRegex(ValueError,"intervalo"):
            self.run_audit(listing_manifest=a)

    def test_tampered_raw_is_conflict(self):
        key=next(iter(self.tx_raws))
        s,items=self.run_audit(tx_responses={**self.tx_raws,key:self.tx_raws[key]+b" "})
        self.assertEqual(s.coverage,"CONFLICT")
        self.assertTrue(any("transaction_raw_sha_conflict" in x.reasons for x in items))

    def test_missing_transaction_is_unknown_not_covered(self):
        key=next(iter(self.tx_raws))
        sub=dict(self.tx_raws)
        del sub[key]
        s,items=self.run_audit(tx_responses=sub)
        self.assertEqual(s.coverage,"PARTIAL")
        self.assertEqual(s.verified_transactions,1)
        self.assertEqual(s.unresolved_transactions,2)

    def test_later_cutoff_is_rejected_as_conflict(self):
        s,items=self.run_audit(cutoff=datetime(2026,11,20,19,55,tzinfo=timezone.utc))
        self.assertEqual(s.coverage,"CONFLICT")
        self.assertIn("transaction_conflict",s.reasons)

    def test_invalid_pagination_manifest_stays_partial(self):
        m=dict(self.listing_manifest,pagination_exhausted=True,page_full=False)
        s,_=self.run_audit(listing_manifest=m)
        self.assertEqual(s.coverage,"PARTIAL")
        self.assertIn("listing_not_proven_complete",s.reasons)

    def test_order_within_same_slot_never_inferred(self):
        s,items=self.run_audit()
        self.assertIsNone(items[1].transaction_index)
        self.assertFalse(s.transaction_order_proven)

    def test_deterministic_real_replay(self):
        self.assertEqual(self.run_audit(),self.run_audit())

    def test_sqlite_atomic_checkpoint_and_recovery(self):
        s,items=self.run_audit()
        with tempfile.TemporaryDirectory() as folder:
            db=SQLiteCpmmProspectiveHistory(Path(folder)/"smr.sqlite")
            for i,capture in enumerate(self.captures):
                db.append_capture(capture,manifest_raw=self.manifest_raws[i],
                                  prior_capture_id=self.captures[0].capture_id if i else None,
                                  coverage="PARTIAL" if i else "OBSERVED")
            init_interval_schema(db.connection)
            kw=dict(first_capture_id=self.captures[0].capture_id,
                    second_capture_id=self.captures[1].capture_id,
                    source_id="solana-public-mainnet-triton",
                    listing_raw=self.listing_raw,listing_manifest=self.listing_manifest,
                    transaction_raws=self.tx_raws,transactions=items,summary=s)
            with self.assertRaisesRegex(RuntimeError,"interruption"):
                append_interval_audit(db.connection,**kw,fail_before_commit=True)
            self.assertIsNone(get_interval_audit(db.connection,
                self.captures[0].capture_id,self.captures[1].capture_id))
            self.assertTrue(append_interval_audit(db.connection,**kw))
            self.assertFalse(append_interval_audit(db.connection,**kw))
            self.assertEqual(get_interval_audit(db.connection,
                self.captures[0].capture_id,self.captures[1].capture_id)["coverage"],"PARTIAL")
            self.assertEqual(db.integrity_check(),["ok"])
            db.close()

    def test_sqlite_stored_raw_tamper_detected(self):
        s,items=self.run_audit()
        with tempfile.TemporaryDirectory() as folder:
            db=SQLiteCpmmProspectiveHistory(Path(folder)/"smr.sqlite")
            db.append_capture(self.captures[0],manifest_raw=self.manifest_raws[0])
            db.append_capture(self.captures[1],manifest_raw=self.manifest_raws[1],
                prior_capture_id=self.captures[0].capture_id,coverage="PARTIAL")
            init_interval_schema(db.connection)
            kwargs=dict(first_capture_id=self.captures[0].capture_id,
                    second_capture_id=self.captures[1].capture_id,
                    source_id="solana-public-mainnet-triton",
                    listing_raw=self.listing_raw,listing_manifest=self.listing_manifest,
                    transaction_raws=self.tx_raws,transactions=items,summary=s)
            append_interval_audit(db.connection,**kwargs)
            db.connection.execute("UPDATE cpmm_interval_evidence SET raw_payload=? "
                                  "WHERE evidence_kind='LISTING'",(b"tampered",))
            db.connection.commit()
            with self.assertRaisesRegex(ValueError,"corrupted RAW"):
                get_interval_audit(db.connection,self.captures[0].capture_id,
                                   self.captures[1].capture_id)
            db.close()


if __name__=="__main__":unittest.main()
