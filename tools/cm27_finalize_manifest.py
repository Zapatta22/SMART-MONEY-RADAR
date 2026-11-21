"""CM27 failure/termination artifact. Python stdlib only, no RPC or orders."""
from __future__ import annotations
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import json,sqlite3,sys

def finalize(out:Path,pinned_source:str,lock:Path,script:Path):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    manifest=out/"manifest.json"
    raw_manifest=None
    try:
        raw_manifest=json.loads(manifest.read_text()) if manifest.exists() else None
    except (ValueError,OSError,UnicodeError):
        raw_manifest=None
    status_path=out/"capture_exit_code.txt"
    code=status_path.read_text().strip() if status_path.exists() else "MISSING"
    db=out/"geyser-raw.sqlite"
    integrity="ABSENT"
    if db.exists():
        try:
            con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=2)
            try:integrity=str(con.execute("PRAGMA integrity_check").fetchone()[0])
            finally:con.close()
        except (sqlite3.Error,ValueError,OSError) as exc:
            integrity="ERROR_"+type(exc).__name__
    complete=(code=="0" and integrity=="ok" and isinstance(raw_manifest,dict)
              and raw_manifest.get("runtime")=="real_solana_public_rpc_websocket"
              and raw_manifest.get("financial_execution_authorized") is False
              and raw_manifest.get("coverage")=="UNKNOWN")
    stamp=datetime.now(timezone.utc).isoformat()
    receipt={
        "schema":"smr.cm27.termination.v2",
        "recorded_at":stamp,
        "status":"COMPLETED_CAPTURE_WITH_UNPROVEN_COVERAGE" if complete else "FAILED_OR_INCOMPLETE",
        "source_commit":pinned_source,
        "capture_exit_code":code,
        "sqlite_integrity":integrity,
        "manifest_completed":bool(complete),
        "coverage":"UNKNOWN",
        "real_execution_authorized":False,
        "live_homologation":False,
        "requirements_sha256":sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None,
        "capture_script_sha256":sha256(script.read_bytes()).hexdigest() if script.is_file() else None,
        "sqlite_sha256":sha256(db.read_bytes()).hexdigest() if db.is_file() else None,
    }
    if not complete:
        # Preserve any partial producer manifest separately; never overwrite it
        # to mask failure, and never claim a missing SQLite as a successful run.
        if raw_manifest is not None:
            (out/"partial-manifest.json").write_text(json.dumps(raw_manifest,sort_keys=True,indent=2)+"\n")
        manifest.write_text(json.dumps({
            "schema":"smr.cm27.incomplete.v2","status":"FAILED_OR_INCOMPLETE",
            "recorded_at":stamp,"source_commit":pinned_source,
            "coverage":"UNKNOWN","financial_execution_authorized":False,
            "capture_exit_code":code,"sqlite_integrity":integrity,
        },sort_keys=True,indent=2)+"\n")
    tmp=out/"termination.json.partial"
    tmp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    tmp.replace(out/"termination.json")
    return receipt

if __name__=="__main__":
    if len(sys.argv)!=5:
        raise SystemExit("usage: cm27_finalize_manifest.py OUT SOURCE_SHA LOCK SCRIPT")
    result=finalize(Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3]),Path(sys.argv[4]))
    print("CM27_AUDIT_STATUS="+result["status"],flush=True)
