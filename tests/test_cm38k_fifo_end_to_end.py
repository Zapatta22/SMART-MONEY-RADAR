"""Offline economic fixture through existing Event Store and original RPC journal."""
from datetime import datetime, timezone
from decimal import Decimal
import unittest
import test_cm38_economic_child_links as child
from smart_money_radar.services.cm38k_persisted_fifo import persist_fifo_swap
from smart_money_radar.services.cm38k_fifo_reconstruction import verify_fifo_receipt

class PersistedEconomicFixture(unittest.TestCase):
    def setUp(self):
        # Reuse existing setup and bundle persistence, not its unrelated tests.
        child.EconomicChildEvidenceLinks.setUp(self)
        self.tx["transaction"]["message"].update(
            accountKeys=[self.wallet], header={"numRequiredSignatures":1})
        self.tx["blockTime"]=int(self.at.timestamp())
        def balance(mint, amount, index):
            return {"owner":self.wallet,"mint":mint,"accountIndex":index,
                    "uiTokenAmount":{"amount":str(amount),"decimals":0}}
        self.tx["meta"].update(fee=5000,
            preTokenBalances=[balance("quote",20,1),balance("base",0,2)],
            postTokenBalances=[balance("quote",10,1),balance("base",2,2)])
        self.eid=child.EconomicChildEvidenceLinks.capture(self,radar="smart_money",source="helius-wallet-rpc")
        self.op,bundle=child.EconomicChildEvidenceLinks.add_swap(self)
        with self.store._connection_scope() as c,c:
            c.execute("UPDATE observed_transactions SET chain=?, observed_at=? WHERE wallet_address=? AND signature=?",
                      ("solana",self.at.isoformat(),self.wallet,self.signature))
        self.store.mark_processed(self.wallet,self.signature,replay_bundles=(bundle,),evidence_id=self.eid)
        self.cutoff=datetime.now(timezone.utc)

    def receipt(self):
        return persist_fifo_swap(self.store,operation_id=self.op,as_of=self.cutoff)

    def test_buy_net_quantity_and_unknown_cost(self):
        result=self.receipt()
        verify_fifo_receipt(result)
        self.assertEqual(result["status"],"NOT_COMPUTABLE")
        self.assertEqual(Decimal(result["lots"][0]["remaining"]),Decimal(2))
        self.assertIsNone(result["lots"][0]["cost_remaining"])
        self.assertEqual(result["persisted_swap"]["wallet_debit"],"10")
        self.assertEqual(result["persisted_swap"]["network_fee_lamports"],5000)
        self.assertEqual(result["lineage"][0]["evidence_id"],self.eid)
        self.assertEqual(self.receipt(),result)

    def test_raw_tampered(self):
        with self.store._connection_scope() as c,c:
            c.execute("UPDATE cm38_rpc_observations SET raw=? WHERE evidence_id=?",
                      (b'{}', self.eid))
        with self.assertRaises(ValueError):
            self.receipt()

    def test_quantity_conflict(self):
        with self.store._connection_scope() as c,c:
            c.execute("UPDATE swap_replay_archive SET input_amount='11' WHERE operation_id=?",(self.op,))
        with self.assertRaises(ValueError):
            self.receipt()

    def test_reopen_deterministic(self):
        first=self.receipt()
        from smart_money_radar.storage.event_store import SQLiteEventStore
        with self.store._connection_scope() as c:
            path=c.execute("PRAGMA database_list").fetchone()[2]
        self.store.close()
        reopened=SQLiteEventStore(path)
        try:
            self.assertEqual(persist_fifo_swap(reopened,operation_id=self.op,as_of=self.cutoff),first)
            with reopened._connection_scope() as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM cm38k_persisted_fifo").fetchone()[0],1)
        finally:
            reopened.close()


    def test_partial_sale_persisted_wallet(self):
        from datetime import timedelta
        from smart_money_radar.domain.models import SwapObservation, SwapClassification, SwapEvidence, build_swap_operation_id
        from smart_money_radar.domain.swap_bundle_builder import SwapDomainBundle
        from smart_money_radar.storage.event_store import SwapReconciliationRecord
        from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
        from smart_money_radar.services.cm38k_persisted_fifo import reconstruct_persisted_wallet
        import json
        sig="1"*63+"2"
        at=self.at+timedelta(seconds=1)
        tx=json.loads(json.dumps(self.tx))
        tx["slot"]=43
        tx["blockTime"]=int(at.timestamp())
        tx["transaction"]["signatures"]=[sig]
        for balance,amount in zip(tx["meta"]["preTokenBalances"],(10,2)):
            balance["uiTokenAmount"]["amount"]=str(amount)
        for balance,amount in zip(tx["meta"]["postTokenBalances"],(17,1)):
            balance["uiTokenAmount"]["amount"]=str(amount)
        eid=RpcObservationJournal(self.store).append(radar="smart_money",signature=sig,
            source_id="helius-wallet-rpc",endpoint_host="public-endpoint.invalid",
            raw_payload=json.dumps({"result":tx}).encode(),observed_at=at,available_at=at,
            expected_slot=43,commitment_requested="confirmed")
        self.store.save_observation(self.wallet,sig,tx,[],parse_status="ok",advance_checkpoint=False)
        with self.store._connection_scope() as c,c:
            c.execute("UPDATE observed_transactions SET slot=43,chain='solana',observed_at=? WHERE wallet_address=? AND signature=?",
                      (at.isoformat(),self.wallet,sig))
        oid=build_swap_operation_id("solana",sig,0)
        obs=SwapObservation(oid,"solana",self.wallet,sig,"base","quote",Decimal(1),Decimal(7),at,"1")
        cls=SwapClassification(oid,"SELL",Decimal(".95"),"fixture")
        ev=SwapEvidence(oid,"dex",None,0,evidence=("pool_state:pool",))
        self.store.save_swap_bundle(obs,cls,ev)
        self.store.save_swap_reconciliation_attempt(self.wallet,sig,
            [SwapReconciliationRecord(oid,0,None,(),"MATCHED","fixture")])
        self.store.mark_processed(self.wallet,sig,replay_bundles=(SwapDomainBundle(obs,cls,ev),),evidence_id=eid)
        args=dict(wallet=self.wallet,token="base",quote_mint="quote",as_of=datetime.now(timezone.utc))
        result=reconstruct_persisted_wallet(self.store,**args)
        verify_fifo_receipt(result)
        self.assertEqual(Decimal(result["lots"][0]["remaining"]),Decimal(1))
        self.assertEqual(Decimal(result["observed_operations"][1]["net_quote_amount"]),Decimal(7))
        self.assertIsNone(result["realized_pnl"])
        self.assertEqual(result["status"],"NOT_COMPUTABLE")
        self.assertEqual(reconstruct_persisted_wallet(self.store,**args),result)
