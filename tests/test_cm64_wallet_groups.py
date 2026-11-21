import unittest,sqlite3
from datetime import datetime,timezone,timedelta
import test_cm54_causal_economics as fixture
from smart_money_radar.services.cm38j_wallet_groups import persist_groups

class Groups(unittest.TestCase):
    def setUp(self):
        fixture.CausalEconomics.setUp(self)
    def test_persist_replay_and_immutable(self):
        end=datetime.now(timezone.utc)
        a=persist_groups(self.store,wallets=(self.wallet,"other"),cutoff=end)
        b=persist_groups(self.store,wallets=("other",self.wallet),cutoff=end)
        self.assertEqual(a,b)
        self.assertEqual(a["independent_wallets"],0)
        self.assertTrue(a["evidence"])
        with self.store._connection_scope() as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("DELETE FROM cm38j_wallet_groups")
        self.assertEqual(self.cap.snapshot("virtual"),self.before)
    def test_temporal(self):
        a=persist_groups(self.store,wallets=(self.wallet,),cutoff=self.at-timedelta(seconds=1))
        self.assertEqual(a["evidence"],[])
        with self.assertRaises(ValueError):
            persist_groups(self.store,wallets=(self.wallet,),cutoff=datetime.now(timezone.utc)+timedelta(days=1))
