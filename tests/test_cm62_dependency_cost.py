import unittest
from smart_money_radar.services.wallet_consensus import shared_evidence_groups
from smart_money_radar.services.cm38k_persisted_fifo import network_fee_breakdown

class DependencyAndCost(unittest.TestCase):
    def test_transitive_shared_signatures(self):
        members=[("a",("x",)),("b",("x","y")),("c",("y",)),("d",("z",))]
        self.assertEqual(shared_evidence_groups(members),(("a","b","c"),("d",)))
        self.assertEqual(shared_evidence_groups(members[::-1]),shared_evidence_groups(members))
    def test_no_evidence_is_not_shared(self):
        self.assertEqual(shared_evidence_groups([("a",()),("b",())]),(("a",),("b",)))
    def test_fee_total_not_added_twice(self):
        result=network_fee_breakdown({"meta":{"fee":9000,"priorityFee":4000}})
        self.assertEqual(result["total_lamports"],9000)
        self.assertIsNone(result["priority_lamports"])
        self.assertEqual(network_fee_breakdown({"meta":{"fee":True}})["status"],"NOT_COMPUTABLE")
