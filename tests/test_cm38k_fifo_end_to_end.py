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
