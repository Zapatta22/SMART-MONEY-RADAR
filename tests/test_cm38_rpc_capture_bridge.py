"""CM38B: exercise actual Helius transport capture with injected bytes."""
import unittest,json,tempfile
from pathlib import Path
from datetime import datetime,timezone
from smart_money_radar.data_sources.helius import HeliusDataSource
from smart_money_radar.services.rpc_capture_bridge import collect_transaction_with_evidence
from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.storage.event_store import SQLiteEventStore
from types import SimpleNamespace

class Response:
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return self.raw

class CaptureBridge(unittest.IsolatedAsyncioTestCase):
    async def test_raw_bytes_and_confirmed_commitment_preserved(self):
        sig="1"*64
        raw=json.dumps({"jsonrpc":"2.0","result":{"slot":42,"transaction":{"signatures":[sig],"message":{"instructions":[]}},"meta":{"err":None}}}, indent=2).encode()
        requests=[]
        def opener(req,timeout):
            requests.append(json.loads(req.data));return Response(raw)
        settings=SimpleNamespace(http_url="https://example.invalid/?api-key=fixture",request_timeout_seconds=1)
        rpc=HeliusDataSource(settings,opener=opener)
        with tempfile.TemporaryDirectory() as tmp:
            store=SQLiteEventStore(Path(tmp)/"db.sqlite")
            try:
                result=await collect_transaction_with_evidence(store,rpc,radar="smart_money",signature=sig,source_id="fixture",commitment="confirmed",legacy=None)
                self.assertEqual(result["slot"],42)
                self.assertEqual(requests[0]["params"][1]["commitment"],"confirmed")
                with store._connection_scope() as conn:
                    meta,stored=conn.execute("SELECT metadata,raw FROM cm38_rpc_observations").fetchone()
                self.assertEqual(stored,raw)
                self.assertEqual(json.loads(meta)["commitment_requested"],"confirmed")
                self.assertNotIn("api-key",meta)
                report=RpcObservationJournal(store).assess(radar="smart_money",signature=sig,cutoff=datetime.now(timezone.utc))
                self.assertFalse(report["independently_finalized"])
            finally:store.close()
    async def test_legacy_adapter_does_not_manufacture_raw(self):
        class Legacy:pass
        async def legacy():return {"slot":1}
        with tempfile.TemporaryDirectory() as tmp:
            store=SQLiteEventStore(Path(tmp)/"db.sqlite")
            try:
                result=await collect_transaction_with_evidence(store,Legacy(),radar="launch",signature="legacy",source_id="fixture",commitment="finalized",legacy=legacy)
                self.assertEqual(result,{"slot":1})
                with store._connection_scope() as conn:
                    self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='cm38_rpc_observations'").fetchone())
            finally:store.close()
