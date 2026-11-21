"""Offline CM74 soak evidence gate; never grants live or financial authorization."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def verify(workspace):
    workspace = Path(workspace)
    report = json.loads((workspace / "report.json").read_text())
    issues = []
    if report.get("schema_version") != 1 or report.get("scope") != "EMPTY_ARCHIVE_OFFLINE":
        issues.append("unexpected report schema or scope")
    if report.get("outcome") != "COMPLETED":
        issues.append("offline soak not completed")
    if report.get("sqlite_integrity") != ["ok"]:
        issues.append("reported SQLite integrity not ok")
    supervisor = report.get("supervisor", {})
    if supervisor.get("lease") != "STOPPED":
        issues.append("supervisor did not stop cleanly")
    if supervisor.get("live_authorized") is not False or supervisor.get("execution_enabled") is not False:
        issues.append("unexpected financial or live authorization")
    tasks = supervisor.get("radars", {})
    if set(tasks) != {"launch", "smart_money"}:
        issues.append("missing independent radar progress")
    else:
        for name, task in tasks.items():
            if type(task.get("cycles")) is not int or task["cycles"] < 1:
                issues.append(f"{name} has no completed offline cycles")
            if task.get("status") != "READY" or type(task.get("failures")) is not int or task["failures"] != 0:
                issues.append(f"{name} final state is not healthy")
    elapsed = report.get("elapsed_seconds")
    duration = report.get("target_duration_seconds")
    if (type(elapsed) not in (int, float) or type(duration) not in (int, float)
            or not 0 < duration <= elapsed or elapsed == float("inf")):
        issues.append("offline soak target duration not reached")
    if report.get("physical_android_verified") is not False or report.get("autonomy_24h_verified") is not False:
        issues.append("untrusted physical/autonomy verification claim")
    progress = workspace / "progress.jsonl"
    if not progress.is_file():
        issues.append("missing progress journal")
    else:
        entries = [json.loads(line) for line in progress.read_text().splitlines() if line.strip()]
        if not entries or entries[0].get("event") != "started" or entries[-1].get("event") != "finished":
            issues.append("incomplete progress journal")
        else:
            first, last = entries[0], entries[-1]
            if first.get("scope") != report.get("scope"):
                issues.append("journal scope disagrees with report")
            if last.get("outcome") != report.get("outcome"):
                issues.append("journal outcome disagrees with report")
            if last.get("lease") != supervisor.get("lease"):
                issues.append("journal lease disagrees with report")
            if last.get("radars") != tasks:
                issues.append("journal radar checkpoints disagree with report")
            elapsed = [entry.get("elapsed_seconds") for entry in entries]
            if any(type(value) not in (int, float) or value < 0 for value in elapsed):
                issues.append("invalid journal elapsed time")
            elif any(a > b for a, b in zip(elapsed, elapsed[1:])):
                issues.append("journal elapsed time regressed")
    db = workspace / "offline-soak.sqlite"
    if not db.is_file():
        issues.append("missing offline SQLite archive")
    else:
        with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                issues.append("SQLite integrity check failed")
            try:
                lease = conn.execute(
                    "SELECT generation,owner,heartbeat,expires,status,payload_sha "
                    "FROM cm36_supervisor_lease WHERE singleton=1"
                ).fetchone()
                if lease is None:
                    issues.append("missing persisted supervisor lease")
                else:
                    generation, owner, heartbeat, expires, state, digest = lease
                    lease_payload = json.dumps(
                        [generation, owner, heartbeat, expires, state],
                        sort_keys=True, separators=(",", ":"),
                    )
                    if hashlib.sha256(lease_payload.encode()).hexdigest() != digest:
                        issues.append("persisted supervisor lease hash mismatch")
                    if state != "STOPPED" or generation != supervisor.get("generation"):
                        issues.append("persisted supervisor lease disagrees with report")
                rows = conn.execute("SELECT radar,payload,payload_sha FROM cm36_supervisor_tasks").fetchall()
                persisted = {}
                for radar, payload, digest in rows:
                    if hashlib.sha256(payload.encode()).hexdigest() != digest:
                        issues.append(f"{radar} persisted checkpoint hash mismatch")
                    task = json.loads(payload)
                    if task.get("radar") != radar:
                        issues.append(f"{radar} persisted checkpoint identity mismatch")
                    if radar in persisted:
                        issues.append(f"{radar} duplicate persisted checkpoint")
                    persisted[radar] = task
                if set(persisted) != {"launch", "smart_money"}:
                    issues.append("missing persisted radar checkpoints")
                else:
                    for name in persisted:
                        if persisted[name].get("cycles") != tasks.get(name, {}).get("cycles"):
                            issues.append(f"{name} persisted cycles disagree with final report")
                        if persisted[name].get("status") != tasks.get(name, {}).get("status"):
                            issues.append(f"{name} persisted status disagrees with final report")
                        if persisted[name].get("failures") != tasks.get(name, {}).get("failures"):
                            issues.append(f"{name} persisted failures disagree with final report")
            except (sqlite3.Error, ValueError, TypeError):
                issues.append("invalid persisted radar checkpoints")
    return {"accepted_offline": not issues, "physical_android_verified": False,
            "autonomy_24h_verified": False, "live_authorized": False,
            "execution_enabled": False, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.workspace)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, sqlite3.Error) as exc:
        result = {"accepted_offline": False, "physical_android_verified": False,
                  "autonomy_24h_verified": False, "live_authorized": False,
                  "execution_enabled": False, "issues": [type(exc).__name__]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["accepted_offline"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
