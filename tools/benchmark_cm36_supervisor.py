"""Bounded Linux/Termux-compatible offline supervisor resource measurement.

Uses a temporary SQLite database, empty archive, accelerated scheduler clock.
Reports actual wall/CPU/RSS/storage; not 24-hour or network homologation.
"""
import json
import resource
import tempfile
import time
from datetime import datetime,timezone
from pathlib import Path
from smart_money_radar.storage.event_store import SQLiteEventStore
from smart_money_radar.services.persistent_supervisor import PersistentSupervisor,SupervisorPolicy
from smart_money_radar.services.operational_controls import LocalOperationalControls

def main():
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/"smr.sqlite";store=SQLiteEventStore(path)
        key=b"benchmark-local-only"*2
        clock=[time.time()]
        ctl=LocalOperationalControls(store,operator_capability=key)
        for r in ("launch","smart_money"):
            ctl.apply(capability=key,event_id="start-"+r,action="START",actor="benchmark",
                reason="offline empty archive benchmark",radar=r,at=datetime.fromtimestamp(clock[0],timezone.utc))
        supervisor=PersistentSupervisor(store,policy=SupervisorPolicy(interval_seconds=1),clock=lambda:clock[0])
        supervisor.acquire()
        def size():return sum(p.stat().st_size for p in Path(d).glob("smr.sqlite*"))
        before=size();wall=time.perf_counter();cpu=time.process_time()
        for _ in range(100):
            supervisor.cycle();clock[0]+=1
        supervisor.stop()
        metrics={"scope":"EMPTY_ARCHIVE_OFFLINE","cycles":100,"radar_cycles":200,
            "wall_seconds":time.perf_counter()-wall,"cpu_seconds":time.process_time()-cpu,
            "process_peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "storage_before_bytes":before,"storage_after_bytes":size(),
            "sqlite_integrity":store.integrity_check(),"autonomy_24h_verified":False}
        store.close()
        print("CM36_BENCHMARK "+json.dumps(metrics,sort_keys=True))
        if metrics["sqlite_integrity"]!=["ok"]:raise SystemExit(1)
if __name__=="__main__":main()
