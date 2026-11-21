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



    def test_cm69_candidate_selection_excludes_future_and_other_pool(self):
        a, b = self.capture(0), self.capture(1)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.sqlite"
            db = SQLiteCpmmProspectiveHistory(path)
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            db.append_capture(b, manifest_raw=self.bundles[1][0],
                              prior_capture_id=a.capture_id, coverage="PARTIAL")
            db.close()
            db = SQLiteCpmmProspectiveHistory(path)
            pool = a.observation.pool
            self.assertEqual(db.candidate_capture_ids(pool=pool, cutoff=CUTOFF),
                             (b.capture_id, a.capture_id))
            self.assertEqual(db.candidate_capture_ids(pool=pool, cutoff=a.observation.available_at),
                             (a.capture_id,))
            self.assertEqual(db.candidate_capture_ids(pool=pool, cutoff=CUTOFF, limit=1),
                             (b.capture_id,))
            self.assertEqual(db.candidate_capture_ids(pool="other", cutoff=CUTOFF), ())
            with self.assertRaises(ValueError):
                db.candidate_capture_ids(pool=pool, cutoff=CUTOFF, limit=0)
            db.close()



    def test_cm69_automatic_receipts_select_causal_head_and_block_conflict(self):
        from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
        a,b = self.capture(0),self.capture(1)
        acc = next(x.accounts for x in decode_raydium_cpmm_swaps(json.loads(self.old))
                   if x.accounts.pool_state == a.observation.pool)
        with tempfile.TemporaryDirectory() as d:
            db = SQLiteCpmmProspectiveHistory(Path(d) / "evidence.sqlite")
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            db.append_capture(b, manifest_raw=self.bundles[1][0],
                              prior_capture_id=a.capture_id, coverage="PARTIAL")
            args = dict(pool=a.observation.pool, token_mint=acc.input_token_mint,
                        quote_mint=acc.output_token_mint, cpmm_history=db,
                        original_transaction_raw=self.old, original_manifest=self.old_manifest)
            for mode in ("immediate", "confirmed"):
                for point, expected in ((a.observation.available_at,a),(CUTOFF,b)):
                    receipt = launch_metric_receipts(**args, at=point, strategy=mode)
                    archive = receipt["economic_qualification"]["account_archive"]
                    self.assertEqual(archive["capture_id"], expected.capture_id)
                    self.assertFalse(receipt["operational_authorized"])
            with db.connection:
                db.connection.execute("UPDATE prospective_cpmm_captures SET coverage='CONFLICT' WHERE capture_id=?", (b.capture_id,))
            bad = launch_metric_receipts(**args, at=CUTOFF, strategy="confirmed")
            self.assertEqual(bad["economic_qualification"]["account_archive"]["status"], "CONFLICTED")
            self.assertIn("cpmm_account_archive_conflict", bad["safety_blocks"])
            db.close()



    def test_cm69_original_binding_restart_and_integrity(self):
        a = self.capture(0)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "evidence.sqlite"
            db = SQLiteCpmmProspectiveHistory(path)
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            self.assertIsNone(db.get_original(a.capture_id))
            args = dict(original_transaction_raw=self.old,
                        original_manifest=self.old_manifest, cutoff=CUTOFF)
            self.assertTrue(db.bind_original(a.capture_id, **args))
            self.assertFalse(db.bind_original(a.capture_id, **args))
            db.close()
            db = SQLiteCpmmProspectiveHistory(path)
            self.assertEqual(db.get_original(a.capture_id), (self.old,self.old_manifest))
            with db.connection:
                db.connection.execute("UPDATE prospective_cpmm_originals SET transaction_raw=?", (self.old+b" ",))
            with self.assertRaisesRegex(ValueError, "hash conflict"):
                db.get_original(a.capture_id)
            db.close()



    def test_cm69_archive_only_receipts_after_restart(self):
        from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
        a = self.capture(0)
        acc = next(x.accounts for x in decode_raydium_cpmm_swaps(json.loads(self.old))
                   if x.accounts.pool_state == a.observation.pool)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "archive.sqlite"
            db = SQLiteCpmmProspectiveHistory(path)
            db.append_capture(a, manifest_raw=self.bundles[0][0])
            db.bind_original(a.capture_id, original_transaction_raw=self.old,
                             original_manifest=self.old_manifest, cutoff=CUTOFF)
            db.close()
            db = SQLiteCpmmProspectiveHistory(path)
            args = dict(pool=a.observation.pool, token_mint=acc.input_token_mint,
                        quote_mint=acc.output_token_mint, cpmm_history=db, at=CUTOFF)
            for mode in ("immediate", "confirmed"):
                receipt = launch_metric_receipts(**args, strategy=mode)
                self.assertEqual(receipt["economic_qualification"]["account_archive"]["capture_id"], a.capture_id)
                from decimal import Decimal, localcontext
                archive=receipt["economic_qualification"]["account_archive"]
                with localcontext() as ctx:
                    ctx.prec=50
                    q=Decimal(archive["quote_reserve_raw"]).scaleb(-archive["quote_decimals"])
                    t=Decimal(archive["token_reserve_raw"]).scaleb(-archive["token_decimals"])
                    self.assertEqual(Decimal(archive["quote_reserve_normalized"]),q)
                    self.assertEqual(Decimal(archive["token_reserve_normalized"]),t)
                    self.assertEqual(Decimal(archive["estimated_spot_quote_per_token"]),q/t)
                    self.assertEqual(Decimal(archive["estimated_pool_value_quote"]),2*q)
                self.assertEqual(archive["decimals_provenance"],"POOL_DECLARED_NOT_MINT_ATTESTED")
                self.assertFalse(archive["operational_authorized"])
                self.assertFalse(receipt["operational_authorized"])
            db.close()


    def test_cm70_atomic_capture_original_rollback_and_restart(self):
        a = self.capture(0)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "atomic.sqlite"
            db = SQLiteCpmmProspectiveHistory(path)
            args = dict(manifest_raw=self.bundles[0][0],
                        original_transaction_raw=self.old,
                        original_manifest=self.old_manifest, cutoff=CUTOFF)
            with self.assertRaises(ValueError):
                db.append_capture_with_original(a, **dict(args, original_transaction_raw=self.old+b" "))
            self.assertIsNone(db.get_capture(a.capture_id))
            self.assertIsNone(db.get_original(a.capture_id))
            self.assertTrue(db.append_capture_with_original(a, **args))
            self.assertFalse(db.append_capture_with_original(a, **args))
            db.close()
            db = SQLiteCpmmProspectiveHistory(path)
            self.assertIsNotNone(db.get_capture(a.capture_id))
            self.assertEqual(db.get_original(a.capture_id), (self.old, self.old_manifest))
            self.assertFalse(db.append_capture_with_original(a, **args))
            db.close()


    def test_cm70_bidirectional_trade_fee_model(self):
        from decimal import Decimal
        from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
        from smart_money_radar.domain.cpmm_reserve_estimator import estimate_exact_input
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps
        a = self.capture(0)
        acc = next(x.accounts for x in decode_raydium_cpmm_swaps(json.loads(self.old))
                   if x.accounts.pool_state == a.observation.pool)
        with tempfile.TemporaryDirectory() as d:
            db = SQLiteCpmmProspectiveHistory(Path(d) / "both.sqlite")
            db.append_capture_with_original(a, manifest_raw=self.bundles[0][0],
                original_transaction_raw=self.old, original_manifest=self.old_manifest, cutoff=CUTOFF)
            for mode in ("immediate", "confirmed"):
                for token, quote in ((acc.input_token_mint, acc.output_token_mint),
                                     (acc.output_token_mint, acc.input_token_mint)):
                    r = launch_metric_receipts(pool=a.observation.pool, token_mint=token,
                        quote_mint=quote, cpmm_history=db, at=CUTOFF, strategy=mode,
                        amount_in=Decimal("1"), sell_amount_in=Decimal("2"))
                    ar = r["economic_qualification"]["account_archive"]
                    q,t = Decimal(ar["quote_reserve_normalized"]),Decimal(ar["token_reserve_normalized"])
                    fee = Decimal(ar["trade_fee_rate"])/100
                    for key,x,y,amount,out in (
                        ("buy_model",q,t,Decimal("1"),"estimated_output_token"),
                        ("sell_model",t,q,Decimal("2"),"estimated_output_quote")):
                        model = estimate_exact_input(pool=a.observation.pool,slot=ar["slot"],
                            reserve_in=x,reserve_out=y,amount_in=amount,fee_bps=fee)
                        self.assertEqual(Decimal(ar[key][out]),model.estimated_output)
                        self.assertEqual(Decimal(ar[key]["fee_inclusive_impact_fraction"]),model.price_impact_fraction)
                        self.assertFalse(ar[key]["creator_fee_included"])
                        self.assertFalse(ar[key]["operational_authorized"])
                    self.assertFalse(r["operational_authorized"])
            db.close()

    def test_cm72_local_liquidity_threshold_requires_fresh_capture(self):
        from decimal import Decimal
        from smart_money_radar.services.cm38j_launch_integration import (
            CPMM_LOCAL_LIQUIDITY_BLOCK, launch_metric_receipts,
        )

        capture, args = self._cm72_liquidity_capture()
        archive = launch_metric_receipts(
            **args, at=capture.observation.available_at, strategy="immediate",
        )["economic_qualification"]["account_archive"]
        reserve = Decimal(archive["quote_reserve_normalized"])
        boundary = capture.observation.observed_at + timedelta(minutes=5)
        cases = (
            ("immediate", boundary, reserve, "LOCAL_MEETS_MINIMUM", False),
            ("confirmed", boundary, reserve * 2, "LOCAL_BELOW_MINIMUM", True),
            ("confirmed", boundary + timedelta(microseconds=1), reserve * 2, "STALE", False),
        )
        for strategy, at, minimum, status, should_block in cases:
            with self.subTest(strategy=strategy, status=status):
                receipt = launch_metric_receipts(
                    **args, at=at, strategy=strategy, min_liquidity_quote=minimum,
                )
                economic = receipt["economic_qualification"]
                check = economic["account_archive"]["liquidity_check"]
                self.assertEqual(check["status"], status)
                self.assertEqual(check["reconciliation"], "DECLARATION_MISSING")
                self.assertFalse(check["independently_authenticated"])
                self.assertEqual(CPMM_LOCAL_LIQUIDITY_BLOCK in receipt["safety_blocks"], should_block)
                self.assertIsNone(receipt["observed_reserve_quote"])
                self.assertEqual(economic["quality"], "UNKNOWN")
                self.assertFalse(economic["operational_authorized"])

    def test_cm72_compares_declared_reserves_and_decimals_only_at_same_slot(self):
        from decimal import Decimal
        from smart_money_radar.services.cm38j_launch_integration import launch_metric_receipts
        from smart_money_radar.services.market_safety_liquidity import (
            LiquiditySnapshot, MarketEvidenceEnvelope,
        )

        capture, args = self._cm72_liquidity_capture()
        obs = capture.observation
        archive = launch_metric_receipts(
            **args, at=obs.available_at, strategy="immediate",
        )["economic_qualification"]["account_archive"]
        raw = b"local declared reserve fixture"
        digest = hashlib.sha256(raw).hexdigest()
        token_reserve = Decimal(archive["token_reserve_normalized"])
        quote_reserve = Decimal(archive["quote_reserve_normalized"])
        cases = (
            (obs.slot, quote_reserve, archive["token_decimals"], "SAME_SLOT_MATCH", []),
            (obs.slot - 1, quote_reserve * 2, archive["token_decimals"], "DIFFERENT_SLOT", []),
            (obs.slot, quote_reserve * 2, archive["token_decimals"], "SAME_SLOT_CONFLICT", ["quote_reserve"]),
            (obs.slot, quote_reserve, archive["token_decimals"] + 1, "SAME_SLOT_CONFLICT", ["token_decimals"]),
        )
        for slot, quote_claim, token_decimals, expected, mismatches in cases:
            with self.subTest(reconciliation=expected, mismatches=mismatches):
                envelope = MarketEvidenceEnvelope(
                    evidence_id="declared-cpmm", source_id="declared-provider",
                    token_mint=args["token_mint"], pool=args["pool"], slot=slot,
                    observed_at=obs.observed_at, available_at=obs.available_at,
                    commitment="finalized", integrity_sha256=digest, raw_payload=raw,
                )
                declared = LiquiditySnapshot(
                    envelope=envelope, quote_mint=args["quote_mint"],
                    quote_reserve=quote_claim, base_reserve=token_reserve,
                    reserve_snapshot={
                        "pool": args["pool"], "slot": slot, "commitment": "finalized",
                        "captured_at": obs.observed_at.isoformat(),
                        "available_at": obs.available_at.isoformat(), "raw_sha256": digest,
                        "reserve_in": quote_claim, "reserve_out": token_reserve,
                        "fee_bps": "25", "input_mint": args["quote_mint"],
                        "output_mint": args["token_mint"],
                        "input_decimals": archive["quote_decimals"],
                        "output_decimals": token_decimals,
                    },
                    verified_raw_reserves=raw, depth_quote=None,
                    depth_audited=False, withdrawal_risk_audited=False,
                )
                receipt = launch_metric_receipts(
                    **args, at=obs.available_at, strategy="confirmed", liquidity=declared,
                    amount_in=Decimal("1"),
                )
                economic = receipt["economic_qualification"]
                linked = economic["account_archive"]
                check = linked["liquidity_check"]
                self.assertEqual(check["reconciliation"], expected)
                self.assertEqual(check["mismatches"], mismatches)
                if mismatches:
                    self.assertEqual(linked["status"], "CONFLICTED")
                    self.assertEqual(receipt["observed_reserve_quality"], "CONFLICTED")
                    self.assertIsNone(receipt["observed_reserve_quote"])
                    self.assertIsNone(receipt["estimated_output"])
                    self.assertNotIn("buy_integer_model", linked)
                    self.assertNotIn("buy_model", linked)
                    self.assertIn("cpmm_account_archive_conflict", receipt["safety_blocks"])
                else:
                    self.assertEqual(linked["status"], "LOCAL_PROSPECTIVE_BYTES_LINKED")
                    self.assertIn("buy_integer_model", linked)
                    self.assertIn("buy_model", linked)
                self.assertFalse(receipt["operational_authorized"])

        future = obs.available_at + timedelta(seconds=1)
        future_claim = replace(
            declared,
            envelope=replace(declared.envelope, available_at=future),
            reserve_snapshot={**declared.reserve_snapshot, "available_at": future.isoformat()},
        )
        with self.assertRaisesRegex(ValueError, "evidência futura"):
            launch_metric_receipts(
                **args, at=obs.available_at, strategy="confirmed", liquidity=future_claim,
            )

    def test_cm72_standalone_qualifier_rejects_fresh_local_shortfall(self):
        from decimal import Decimal
        from smart_money_radar.services.cm38j_launch_integration import CPMM_LOCAL_LIQUIDITY_BLOCK
        from smart_money_radar.services.economic_radar_qualification import qualify_launch_at
        from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
        from smart_money_radar.services.wallet_consensus import WalletConsensusReport
        from smart_money_radar.storage.event_store import SQLiteEventStore

        capture, args = self._cm72_liquidity_capture()
        store = SQLiteEventStore(":memory:")
        self.addCleanup(store.close)
        base = OpportunityEvidence(
            token_mint=args["token_mint"], pool=args["pool"], chain="solana",
            as_of=capture.observation.available_at, source_id=capture.observation.source_id,
            source_status="UNKNOWN", history_coverage="UNKNOWN", token_safety="UNKNOWN",
            liquidity_quote=None, volume_quote=None, liquidity_verified=False,
            volume_verified=False, price_confirmation=None, volume_confirmation=None,
        )
        result = qualify_launch_at(
            store, signature=SIG, base=base,
            consensus=WalletConsensusReport("INSUFFICIENT", 0, 0, (), (), False, False, ()),
            quote_mint=args["quote_mint"], cpmm_history=args["cpmm_history"],
            min_liquidity_quote=Decimal("10") ** 30,
        )
        self.assertEqual(result["classification"].verdict, "REJECTED")
        self.assertEqual(result["classification"].data_quality, "UNKNOWN")
        self.assertIn(CPMM_LOCAL_LIQUIDITY_BLOCK, result["reasons"])
        self.assertEqual(dict(result["modes"]), {"immediate": "BLOCKED", "confirmed": "BLOCKED"})
        self.assertFalse(result["prospective_paper_authorized"])

    def _cm72_liquidity_capture(self):
        from smart_money_radar.data_sources.raydium_cpmm_analyzer import decode_raydium_cpmm_swaps

        capture = self.capture()
        account = next(x.accounts for x in decode_raydium_cpmm_swaps(json.loads(self.old))
                       if x.accounts.pool_state == capture.observation.pool)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        db = SQLiteCpmmProspectiveHistory(Path(folder.name) / "cm72-liquidity.sqlite")
        self.addCleanup(db.close)
        db.append_capture_with_original(
            capture, manifest_raw=self.bundles[0][0], original_transaction_raw=self.old,
            original_manifest=self.old_manifest, cutoff=CUTOFF,
        )
        return capture, {
            "pool": account.pool_state, "token_mint": account.input_token_mint,
            "quote_mint": account.output_token_mint, "cpmm_history": db,
        }


if __name__=="__main__":
    unittest.main()
