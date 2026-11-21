"""CM53 fee arithmetic and conservative provenance tests."""
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from smart_money_radar.services.cm38k_persisted_fifo import additional_network_cost, WSOL, fifo_metric_receipts
from smart_money_radar.services.cm38k_fifo_reconstruction import EconomicOperation, reconstruct_fifo

class CostAccounting(unittest.TestCase):
    def test_separate_network_cost(self):
        tx={"transaction":{"message":{"accountKeys":["w"]}},"meta":{"fee":5000,
            "preBalances":[10000],"postBalances":[5000],
            "preTokenBalances":[{"mint":WSOL,"owner":"w"}],
            "postTokenBalances":[{"mint":WSOL,"owner":"w"}]}}
        self.assertEqual(additional_network_cost(tx,"w",WSOL),Decimal("0.000005"))
        self.assertIsNone(additional_network_cost(tx,"w","USDC"))
        tx["meta"]["postBalances"]=[4999]
        self.assertIsNone(additional_network_cost(tx,"w",WSOL))
        self.assertEqual(additional_network_cost(tx,"other","USDC"),Decimal(0))

    def test_controlled_successive_buys_partial_sale(self):
        at=datetime.now(timezone.utc)-timedelta(minutes=1)
        def op(i,kind,qty,amount,fee,attested):
            t=at+timedelta(seconds=i)
            return EconomicOperation(str(i),"w","token",kind,Decimal(qty),t,t,
                "synthetic-fixture",str(i)*64,"a"*64,quote_mint="quote",
                quote_amount=Decimal(amount),fee_mint="quote",fee_amount=Decimal(fee),
                independently_attested=attested,history_complete=attested)
        args=dict(wallet="w",token="token",quote_mint="quote",as_of=at+timedelta(seconds=4))
        def fixture(attested):
            return [op(1,"BUY","2","10","1",attested),
                    op(2,"BUY","2","14","2",attested),
                    op(3,"SELL","3","24","1",attested)]
        # Synthetic assumptions exercise arithmetic only, never real performance.
        result=reconstruct_fifo(fixture(True),**args)
        self.assertEqual(Decimal(result["realized_pnl"]),Decimal(4))
        self.assertEqual(Decimal(result["lots"][0]["remaining"]),Decimal(1))
        self.assertEqual(Decimal(result["lots"][0]["cost_remaining"]),Decimal(8))
        unknown=reconstruct_fifo(fixture(False),**args)
        self.assertIsNone(unknown["realized_pnl"])
        for metric in fifo_metric_receipts(unknown):
            self.assertIsNone(metric["value"])
            self.assertEqual(metric["source_integrity_sha256"],unknown["sha256"])
            self.assertFalse(metric["prospective_paper_authorized"])
