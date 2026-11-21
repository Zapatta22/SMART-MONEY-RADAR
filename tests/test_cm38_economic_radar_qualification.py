"""CM38E/F reuse existing economics; CM39 fails closed with real capital store."""
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path

from smart_money_radar.services.economic_radar_qualification import qualify_launch_at,qualify_smart_money_at
from smart_money_radar.services.opportunity_classifier import OpportunityEvidence
from smart_money_radar.services.wallet_consensus import WalletConsensusReport
from smart_money_radar.services.wallet_discovery import WalletDiscoveryPolicy
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator,CapitalLimits
from smart_money_radar.services.prospective_paper_plan import plan_prospective_paper
from smart_money_radar.storage.event_store import SQLiteEventStore

class EconomicRadarQualifiers(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=SQLiteEventStore(Path(tmp.name)/"evaluation.sqlite")
        self.addCleanup(self.store.close)
        self.at=datetime.now(timezone.utc)-timedelta(seconds=60)
    def fake_launch(self,*,mandatory_blocks=()):
        base=OpportunityEvidence(token_mint="token",chain="solana",pool="pool",
            as_of=self.at,source_id="claimed-trusted-source",
            source_status="VERIFIED",history_coverage="COMPLETE",
            token_safety="VERIFIED",liquidity_quote=Decimal("100000"),
            volume_quote=Decimal("100000"),liquidity_verified=True,volume_verified=True,
            price_confirmation=True,volume_confirmation=True,
            mandatory_blocks=mandatory_blocks,wallet_independence_verified=True)
        consensus=WalletConsensusReport("BUY",4,10,(),(),True,False,())
        return qualify_launch_at(self.store,signature="1"*64,base=base,consensus=consensus,
            quote_mint="wsol",safety=None,liquidity=None,swaps=())
    def test_launch_untrusted_inputs_do_not_promote_opportunity(self):
        result=self.fake_launch()
        self.assertEqual(result["classification"].verdict,"UNKNOWN")
        self.assertEqual(result["classification"].data_quality,"UNKNOWN")
        self.assertEqual(dict(result["modes"]),{"immediate":"BLOCKED","confirmed":"BLOCKED"})
        self.assertIn("mint_freeze_token2022_safety_missing",result["reasons"])
        self.assertFalse(result["prospective_paper_authorized"])
    def test_launch_mandatory_risk_remains_rejection(self):
        result=self.fake_launch(mandatory_blocks=("mint_authority_active",))
        self.assertEqual(result["classification"].verdict,"REJECTED")
        self.assertIn("mint_authority_active",result["reasons"])
    def test_smart_money_candidates_never_invent_profits(self):
        policy=WalletDiscoveryPolicy(manual_wallets=("candidate",))
        report=qualify_smart_money_at(self.store,as_of=self.at,policy=policy)
        (p,)=report["profiles"]
        self.assertIsNone(p["realized_pnl"])
        self.assertIsNone(p["win_rate"])
        self.assertEqual(p["rpc_linked_operations"],0)
        self.assertFalse(p["eligible_for_consensus"])
        self.assertEqual(report["qualified_wallets"],[])
    def test_future_cutoff_for_both_radars_is_denied(self):
        future=datetime.now(timezone.utc)+timedelta(days=1)
        with self.assertRaises(ValueError):
            qualify_smart_money_at(self.store,as_of=future)
        with self.assertRaises(ValueError):
            plan_prospective_paper(self.store,account_id="missing",radar="launch",
                as_of=future,source_assessment={"radar":"launch"},radar_qualification={"radar":"launch"})
    def test_cm39_plan_preserves_real_synthetic_journal(self):
        limits=CapitalLimits(*([Decimal("1")]*8))
        SyntheticCapitalCoordinator(self.store).create(account_id="virtual-launch",initial=Decimal("100"),
            currency="USDC",radars=("launch",),limits=limits)
        before=SyntheticCapitalCoordinator(self.store).snapshot("virtual-launch")
        plan=plan_prospective_paper(self.store,account_id="virtual-launch",radar="launch",
            as_of=self.at,source_assessment={"radar":"launch","provider_authenticated":True,
              "independently_finalized":True,"prospective_paper_authorized":True},
            radar_qualification={"radar":"launch","qualified":True})
        self.assertFalse(plan["prospective_authorized"])
        self.assertEqual(plan["eligible_ticks"],0)
        self.assertFalse(plan["ledger_mutated"])
        self.assertEqual(SyntheticCapitalCoordinator(self.store).snapshot("virtual-launch"),before)
        with self.assertRaises(ValueError):
            plan_prospective_paper(self.store,account_id="virtual-launch",radar="smart_money",
                as_of=self.at,source_assessment={"radar":"smart_money"},
                radar_qualification={"radar":"smart_money"})

    def test_linked_wallet_receipt_still_cannot_invent_pnl(self):
        from smart_money_radar.domain.models import SwapObservation,SwapClassification,SwapEvidence,build_swap_operation_id
        from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
        from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
        from unittest.mock import patch
        import json
        wallet="wallet-a";signature="1"*64
        tx={"slot":42,"transaction":{"signatures":[signature],"message":{
            "instructions":[],"accountKeys":[wallet],"header":{"numRequiredSignatures":1}}},
            "meta":{"err":None}}
        raw=json.dumps({"jsonrpc":"2.0","result":tx}).encode()
        eid=RpcObservationJournal(self.store).append(radar="smart_money",signature=signature,
            source_id="helius-wallet-rpc",endpoint_host="public-rpc.invalid",
            raw_payload=raw,observed_at=self.at,available_at=self.at,
            expected_slot=42,commitment_requested="confirmed")
        self.store.save_observation(wallet,signature,tx,[],parse_status="ok",
                                    advance_checkpoint=False)
        with self.store._connection_scope() as conn,conn:
            conn.execute("""UPDATE observed_transactions SET slot=42,chain='solana',observed_at=?
                            WHERE wallet_address=? AND signature=?""",
                        (self.at.isoformat(),wallet,signature))
        opid=build_swap_operation_id("solana",signature,0)
        obs=SwapObservation(opid,"solana",wallet,signature,"quote","base",
                            Decimal("10"),Decimal("2"),self.at,"1")
        classification=SwapClassification(opid,"BUY",Decimal(".95"),"fixture")
        evidence=SwapEvidence(opid,"dex",None,0,evidence=("pool_state:pool",))
        self.store.save_swap_bundle(obs,classification,evidence)
        self.store.mark_processed(wallet,signature,replay_bundles=(
            SwapDomainBundle(obs,classification,evidence),),evidence_id=eid)
        report=qualify_smart_money_at(self.store,as_of=datetime.now(timezone.utc),
            policy=WalletDiscoveryPolicy(quote_mints=("quote",),min_transactions=2))
        (profile,)=report["profiles"]
        self.assertEqual(profile["rpc_linked_operations"],1)
        self.assertEqual(profile["rpc_unlinked_operations"],0)
        self.assertFalse(profile["qualified"])
        self.assertIsNone(profile["realized_pnl"])
        self.assertIsNone(profile["win_rate"])
    def test_invalid_rpc_source_does_not_advance_wallet_checkpoint(self):
        import json
        from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
        wallet="wallet-a";signature="1"*64
        tx={"slot":42,"transaction":{"signatures":[signature],"message":{"instructions":[]}},"meta":{"err":None}}
        raw=json.dumps({"jsonrpc":"2.0","result":tx}).encode()
        eid=RpcObservationJournal(self.store).append(radar="smart_money",signature=signature,
            source_id="different-untrusted-source",endpoint_host="provider.invalid",
            raw_payload=raw,observed_at=self.at,available_at=self.at,
            expected_slot=42,commitment_requested="confirmed")
        self.store.save_observation(wallet,signature,tx,[],parse_status="ok",advance_checkpoint=False)
        with self.assertRaises(ValueError):
            self.store.mark_processed(wallet,signature,evidence_id=eid)
        self.assertIsNone(self.store.get_checkpoint(wallet))
