"""CM38K immutable sidecar against real existing CM38I decision receipts."""
import json,sqlite3,unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory

from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.services.synthetic_capital import SyntheticCapitalCoordinator,CapitalLimits
from smart_money_radar.services.cm38i_decision_audit import record_blocked_virtual_entry
from smart_money_radar.services.cm38k_fifo_reconstruction import (
    EconomicOperation,reconstruct_fifo,
)
from smart_money_radar.services.cm38k_decision_links import (
    link_fifo_to_blocked_decision,audit_fifo_decision_link,
)
from smart_money_radar.storage.event_store import SQLiteEventStore

class Cm38kDecisionLinks(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.path=Path(t.name)/"audit.sqlite"
        self.db=SQLiteEventStore(self.path);self.addCleanup(self.db.close)
        self.at=datetime.now(timezone.utc)-timedelta(minutes=1)
        self.sig="1"*64
        raw=json.dumps({"jsonrpc":"2.0","result":{"slot":42,
            "transaction":{"signatures":[self.sig],"message":{"instructions":[]}},
            "meta":{"err":None}}}).encode()
        self.eid=RpcObservationJournal(self.db).append(
            radar="smart_money",signature=self.sig,
            source_id="helius-wallet-rpc",endpoint_host="rpc.invalid",
            raw_payload=raw,observed_at=self.at,available_at=self.at,
            expected_slot=42,commitment_requested="confirmed")
        SyntheticCapitalCoordinator(self.db).create(
            account_id="virtual",initial=D("100"),currency="USDC",
            radars=("smart_money",),limits=CapitalLimits(*([D(".8")]*8)))
        self.before=SyntheticCapitalCoordinator(self.db).snapshot("virtual")
        self.cutoff=self.at+timedelta(seconds=10)
        self.decision=record_blocked_virtual_entry(self.db,
            request_id="request",account_id="virtual",radar="smart_money",
            strategy="confirmed",evidence_id=self.eid,
            decision_at=self.cutoff,requested_notional=D("10"))
    def fifo(self):
        op=EconomicOperation(operation_id="buy",wallet="wallet",
            token="TOKEN",kind="BUY",quantity=D("2"),occurred_at=self.at,
            available_at=self.at,source_id="helius-wallet-rpc",
            evidence_id=self.eid,raw_sha256="a"*64,
            quote_mint="USDC",quote_amount=D("20"),
            independently_attested=False,history_complete=False)
        return reconstruct_fifo((op,),wallet="wallet",token="TOKEN",
                                quote_mint="USDC",as_of=self.cutoff)

    def test_idempotency_read_only_recovery_and_blocked_capital(self):
        f=self.fifo()
        first=link_fifo_to_blocked_decision(self.db,request_id="request",receipt=f)
        again=link_fifo_to_blocked_decision(self.db,request_id="request",receipt=f)
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(again["idempotent_replay"])
        self.assertEqual(first["link_id"],again["link_id"])
        read=SQLiteEventStore(self.path,read_only=True)
        try:
            receipt=audit_fifo_decision_link(read,"request")
            self.assertEqual(receipt["economic_sha256"],f["sha256"])
            self.assertFalse(receipt["prospective_authorized"])
        finally: read.close()
        self.assertEqual(SyntheticCapitalCoordinator(self.db).snapshot("virtual"),self.before)

    def test_modified_fifo_receipt_cannot_link(self):
        f=self.fifo();f["realized_pnl"]="100000"
        with self.assertRaisesRegex(ValueError,"integrity"):
            link_fifo_to_blocked_decision(self.db,request_id="request",receipt=f)

    def test_differing_replay_does_not_replace_decision(self):
        f=self.fifo()
        link_fifo_to_blocked_decision(self.db,request_id="request",receipt=f)
        f2=dict(f);f2["as_of"]=(self.cutoff-timedelta(seconds=1)).isoformat()
        from smart_money_radar.services.cm38k_fifo_reconstruction import _hash
        f2["sha256"]=_hash({k:v for k,v in f2.items() if k!="sha256"})
        with self.assertRaisesRegex(ValueError,"divergent"):
            link_fifo_to_blocked_decision(self.db,request_id="request",receipt=f2)
        self.assertEqual(audit_fifo_decision_link(self.db,"request")["economic_sha256"],f["sha256"])

    def test_future_fifo_cutoff_rejected_and_rollback(self):
        f=self.fifo();f["as_of"]=(self.cutoff+timedelta(seconds=1)).isoformat()
        from smart_money_radar.services.cm38k_fifo_reconstruction import _hash
        f["sha256"]=_hash({k:v for k,v in f.items() if k!="sha256"})
        with self.assertRaisesRegex(ValueError,"future"):
            link_fifo_to_blocked_decision(self.db,request_id="request",receipt=f)
        self.assertIsNone(audit_fifo_decision_link(self.db,"request"))

    def test_mutation_blocked_by_immutable_trigger(self):
        link_fifo_to_blocked_decision(self.db,request_id="request",receipt=self.fifo())
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db._connection_scope() as conn,conn:
                conn.execute("UPDATE cm38k_economic_decision_links SET economic_payload='{}'")
        self.assertIsNotNone(audit_fifo_decision_link(self.db,"request"))

if __name__=="__main__":
    unittest.main()
