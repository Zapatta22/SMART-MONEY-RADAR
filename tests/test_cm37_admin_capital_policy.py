"""CM37G receipt-bound capital policy, independent synthetic accounts."""
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from smart_money_radar.services.admin_evaluation import IsolatedAdminEvaluation

class AdminCapitalPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.e=IsolatedAdminEvaluation(Path(tmp.name)/"new",password="offline-admin-test-password",clock=lambda:1000.)
        self.addCleanup(self.e.close)
        session=self.e.login("offline-admin-test-password")
        self.token,self.csrf=session["session"],session["csrf"]
        self.limits={k:"0.5" for k in ("total_exposure","per_radar","per_strategy","per_token","per_pool","per_wallet","max_daily_loss","max_drawdown")}
    def confirm(self,action,policy):
        return self.e.confirm(self.token,self.csrf,action=action,policy=policy)
    def execute(self,action,policy,nonce,request_id):
        return self.e.execute(self.token,self.csrf,action=action,policy=policy,confirmation=nonce,request_id=request_id)
    def create(self,radar):
        return {"account_id":radar,"initial":"100","currency":"USDC","radars":[radar],"limits":self.limits}
    def test_create_independent_accounts_and_receipts(self):
        for r in ("launch","smart_money"):
            p=self.create(r);action="CAPITAL_CREATE";rid="capital-create-"+r
            n=self.confirm(action,p);out=self.execute(action,p,n,rid)
            self.assertTrue(out["executed"])
            self.assertEqual(out["state"]["allowed_radars"],[r])
            self.assertEqual(self.e.outcome(rid)["status"],"APPLIED")
            with self.assertRaises(PermissionError):self.execute(action,p,n,rid)
    def test_changed_payload_requires_new_confirmation(self):
        p=self.create("launch");n=self.confirm("CAPITAL_CREATE",p)
        modified=dict(p,initial="999")
        with self.assertRaises(PermissionError):self.execute("CAPITAL_CREATE",modified,n,"modified-request-001")
        self.assertTrue(self.execute("CAPITAL_CREATE",p,n,"correct-request-001")["executed"])
    def test_invalid_value_never_creates_account(self):
        p=self.create("launch");p["initial"]="NaN"
        n=self.confirm("CAPITAL_CREATE",p)
        self.assertFalse(self.execute("CAPITAL_CREATE",p,n,"invalid-request-001")["executed"])
        self.assertEqual(self.e.outcome("invalid-request-001")["status"],"NO_COMMITTED_TRANSITION")
    def test_full_policy_update_is_audited(self):
        p=self.create("launch");self.execute("CAPITAL_CREATE",p,self.confirm("CAPITAL_CREATE",p),"create-launch-0001")
        policy={"account_id":"launch","limits":self.limits,
            "config":{"initial_cash":"20","max_entry_cash":"5","max_exposure":"0.5","fee_bps":"10",
                "slippage_bps":"20","stop_loss":"0.1","take_profit":"0.2","max_entry_deviation_bps":None,"allow_partial_fills":True},
            "entry_risk":{"max_position_fraction":"0.2","max_daily_loss_fraction":"0.1","max_slippage_bps":"100","min_liquidity_quote":"1"}}
        result=self.execute("CAPITAL_POLICY",policy,self.confirm("CAPITAL_POLICY",policy),"policy-launch-0001")
        self.assertTrue(result["executed"]);self.assertEqual(result["state"]["equity"],"100")
        self.assertEqual(self.e.outcome("policy-launch-0001")["status"],"APPLIED")
