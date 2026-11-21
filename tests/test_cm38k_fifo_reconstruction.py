"""CM38K offline FIFO adversarial tests: no real provider or financial actions."""
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D

from smart_money_radar.services.cm38k_fifo_reconstruction import (
    EconomicOperation,reconstruct_fifo,verify_fifo_receipt,
)

class TestCm38kFifo(unittest.TestCase):
    def setUp(self):
        self.at=datetime.now(timezone.utc)-timedelta(minutes=2)
        self.cutoff=self.at+timedelta(seconds=90)
    def op(self,i,kind,quantity,quote=None,**other):
        args=dict(operation_id=str(i),wallet="wallet",token="TOKEN",kind=kind,
                  quantity=D(quantity),occurred_at=self.at+timedelta(seconds=i),
                  available_at=self.at+timedelta(seconds=i),
                  source_id="rpc",evidence_id=("%064x"%(i+1)),raw_sha256="a"*64,
                  quote_mint="USDC" if quote is not None else None,
                  quote_amount=D(quote) if quote is not None else None,
                  independently_attested=True,history_complete=True)
        args.update(other)
        return EconomicOperation(**args)
    def project(self,*ops,**kw):
        return reconstruct_fifo(ops,wallet="wallet",token="TOKEN",
                                quote_mint="USDC",as_of=self.cutoff,**kw)

    def test_successive_buys_partial_sell_fifo(self):
        p=self.project(self.op(1,"BUY","2","20"),self.op(2,"BUY","2","40"),
                       self.op(3,"SELL","3","65"))
        self.assertEqual(p["realized_pnl"],"25")
        self.assertEqual(p["lots"][0]["remaining"],"1")
        self.assertEqual(p["lots"][0]["cost_remaining"],"20")
        self.assertFalse(p["prospective_authorized"])
        self.assertEqual(verify_fifo_receipt(p)["sha256"],p["sha256"])

    def test_oversell_not_computable(self):
        p=self.project(self.op(1,"BUY","1","10"),self.op(2,"SELL","2","40"))
        self.assertEqual(p["status"],"NOT_COMPUTABLE")
        self.assertIsNone(p["realized_pnl"])
        self.assertIn("insufficient_known_inventory",p["reasons"])

    def test_transfer_in_unknown_basis_not_zero(self):
        p=self.project(self.op(1,"TRANSFER_IN","3"))
        self.assertIsNone(p["lots"][0]["cost_remaining"])
        self.assertEqual(p["lots"][0]["cost_status"],"UNKNOWN")
        self.assertEqual(p["status"],"NOT_COMPUTABLE")

    def test_transfer_out_consumes_inventory(self):
        p=self.project(self.op(1,"BUY","2","20"),
                       self.op(2,"TRANSFER_OUT","1"))
        self.assertEqual(p["lots"][0]["remaining"],"1")
        self.assertEqual(p["lots"][0]["cost_remaining"],"10")

    def test_fee_in_quote_decreases_realized_profit(self):
        p=self.project(self.op(1,"BUY","1","10",fee_mint="USDC",fee_amount=D("1")),
                       self.op(2,"SELL","1","20",fee_mint="USDC",fee_amount=D("2")))
        self.assertEqual(p["realized_pnl"],"7")

    def test_fee_other_token_requires_conversion(self):
        p=self.project(self.op(1,"BUY","1","10",fee_mint="SOL",fee_amount=D(".01")),
                       self.op(2,"SELL","1","20"))
        self.assertIsNone(p["realized_pnl"])
        self.assertIn("cross_mint_fee_unconverted",p["reasons"])

    def test_multistep_swap_unreconciled(self):
        p=self.project(self.op(1,"BUY","1","10",step_complete=False))
        self.assertEqual(p["status"],"NOT_COMPUTABLE")
        self.assertIn("multi_step_swap_reconciliation_incomplete",p["reasons"])

    def test_history_incomplete_blocks_profit(self):
        p=self.project(self.op(1,"BUY","1","10",history_complete=False),
                       self.op(2,"SELL","1","20"))
        self.assertIsNone(p["realized_pnl"])
        self.assertIn("historical_coverage_incomplete",p["reasons"])

    def test_duplicate_and_divergent_replay_rejected(self):
        op=self.op(1,"BUY","1","10")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.project(op,op)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.project(op,self.op(1,"SELL","1","20"))

    def test_rebuild_deterministic_and_integrity_checked(self):
        ops=(self.op(1,"BUY","1","10"),self.op(2,"SELL","1","20"))
        first=self.project(*ops)
        self.assertEqual(first,self.project(*reversed(ops)))
        first["realized_pnl"]="1000000"
        with self.assertRaisesRegex(ValueError,"integrity"):
            verify_fifo_receipt(first)

    def test_future_operation_and_quote_rejected(self):
        with self.assertRaisesRegex(ValueError,"future"):
            self.project(self.op(91,"BUY","1","10"))
        with self.assertRaisesRegex(ValueError,"future"):
            self.project(self.op(1,"BUY","1","10"),quotes=({
                "token":"TOKEN","quote_mint":"USDC","price":D("12"),
                "market_at":self.at,"available_at":self.cutoff+timedelta(seconds=1),
                "independently_attested":True},))

    def test_source_unverified_does_not_claim_pnl(self):
        p=self.project(self.op(1,"BUY","1","10",independently_attested=False),
                       self.op(2,"SELL","1","20"))
        self.assertIsNone(p["realized_pnl"])
        self.assertIn("independent_rpc_evidence_unverified",p["reasons"])

    def test_currency_and_wallet_fencing(self):
        with self.assertRaisesRegex(ValueError,"currency"):
            self.project(self.op(1,"BUY","1","10",quote_mint="SOL"))
        with self.assertRaisesRegex(ValueError,"cross-wallet"):
            self.project(self.op(1,"BUY","1","10",wallet="other"))

    def test_unrealized_requires_attested_point_in_time_quote(self):
        buy=self.op(1,"BUY","1","10")
        p=self.project(buy,quotes=({
            "token":"TOKEN","quote_mint":"USDC","price":D("12"),
            "market_at":self.at,"available_at":self.at,
            "independently_attested":False},))
        self.assertIsNone(p["unrealized_pnl"])
        self.assertIn("valuation_quote_unattested",p["reasons"])

if __name__=="__main__":
    unittest.main()
