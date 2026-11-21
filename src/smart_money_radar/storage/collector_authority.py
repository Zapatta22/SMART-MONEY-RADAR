"""CM36: same-transaction generation fence for managed collector writes."""
from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Callable
import hashlib
import json
import sqlite3
import time


class AuthorityLost(RuntimeError):
    """Terminal for a collector; never retry as a transport error."""


@dataclass(frozen=True)
class CollectorAuthority:
    database_path: str
    generation: int
    owner: str
    radar: str
    clock: Callable[[], float] = time.time
    control_revision: int = -1

    def __post_init__(self):
        if (not self.database_path or self.database_path == ":memory:"
                or type(self.generation) is not int or self.generation < 1
                or not self.owner or self.radar not in ("launch","smart_money")
                or not callable(self.clock)):
            raise ValueError("invalid collector authority")


def collector_control_revision(connection, radar):
    """Revision of the validated journal for the selected radar."""
    row=connection.execute(
        "SELECT MAX(seq) FROM cm34_operational_journal "
        "WHERE json_extract(payload,'$.radar')=? "
        "AND json_extract(payload,'$.action') IN ('START','PAUSE','RADAR_FAULT','RADAR_RECOVERED')",
        (radar,)).fetchone()
    return -1 if row[0] is None else row[0]


def verify_collector_authority(connection, authority, radar=None):
    if not connection.in_transaction:
        raise AuthorityLost("collector fence requires transaction")
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm36_supervisor_lease'"
        ).fetchone()
        row = connection.execute(
            "SELECT generation,owner,heartbeat,expires,status,payload_sha "
            "FROM cm36_supervisor_lease WHERE singleton=1"
        ).fetchone() if exists else None
        managed = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm36_managed_marker'"
        ).fetchone()
        if row is None:
            if managed:
                raise AuthorityLost("managed supervisor lease missing")
            if authority is None:
                return  # standalone archive, not supervisor-authorized
            raise AuthorityLost("missing managed generation")
        if not isinstance(authority, CollectorAuthority):
            raise AuthorityLost("managed database requires collector authority")
        if radar is not None and authority.radar != radar:
            raise AuthorityLost("collector radar mismatch")
        actual = next(x[2] for x in connection.execute("PRAGMA database_list") if x[1]=="main")
        if not actual or not Path(actual).samefile(authority.database_path):
            raise AuthorityLost("collector database mismatch")
        generation, owner, heartbeat, expires, status, digest = tuple(row)
        encoded = json.dumps([generation,owner,heartbeat,expires,status],
                             sort_keys=True,separators=(",",":"),allow_nan=False)
        now = authority.clock()
        if (hashlib.sha256(encoded.encode()).hexdigest() != digest
                or type(generation) is not int or generation != authority.generation
                or owner != authority.owner or status != "ACTIVE"
                or type(now) not in (float,int) or not isfinite(now)
                or not isfinite(heartbeat) or not isfinite(expires)
                or not heartbeat <= now < expires):
            raise AuthorityLost("collector generation expired, stopped or replaced")
        from smart_money_radar.services.operational_controls import read_control_state
        controls = read_control_state(connection)
        if (controls["emergency_halt"] or controls["radars"][authority.radar] != "RUNNING"
                or collector_control_revision(connection, authority.radar) != authority.control_revision):
            raise AuthorityLost("collector paused or emergency halted")
    except AuthorityLost:
        raise
    except (sqlite3.Error,ValueError,TypeError,KeyError,OSError,StopIteration) as exc:
        raise AuthorityLost("collector authority verification failed") from exc


@contextmanager
def collector_write(connection, authority, radar=None):
    """Entry and pre-commit fences; a stale write is rolled back entirely."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        verify_collector_authority(connection, authority, radar)
        yield
        verify_collector_authority(connection, authority, radar)


def check_collector(store, radar=None):
    """Network-boundary check, not a substitute for the transactional fence."""
    method=getattr(store,"assert_collector_authority",None)
    if method is not None:
        method(radar)


async def await_authorized(store, radar, operation, *, poll_seconds=0.25):
    """Race bounded authority checks against pending I/O.

    operation is a factory, so an expired handle never starts the I/O.
    On authority loss or caller cancellation, cancel and join the asyncio
    task. Thread-backed RPC may finish in its worker; its result is discarded
    and all writes still require the transactional generation fence.
    """
    import asyncio
    check_collector(store,radar)
    if getattr(store,"_collector_authority",None) is None and not getattr(store,"_force_authority_poll",False):
        result=await operation()
        check_collector(store,radar)
        return result
    task=asyncio.ensure_future(operation())
    try:
        while True:
            done,_=await asyncio.wait((task,),timeout=poll_seconds)
            check_collector(store,radar)
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task,return_exceptions=True)


def bind_projection(store, authority):
    """Bind a preinitialized file-backed projection/recovery store."""
    if not isinstance(authority,CollectorAuthority) or not Path(store.database_path).samefile(authority.database_path):
        raise AuthorityLost("projection database mismatch")
    if getattr(store,"_collector_authority",None) is not None:
        raise AuthorityLost("a bound projection handle cannot be rebound")
    bound=object.__new__(type(store))
    bound.__dict__=store.__dict__.copy()
    bound._collector_authority=authority
    return bound


def managed_schema_guard(connection):
    """Managed schemas must be prepared before the first supervisor lease.

    Existing tables may be validated by a bound operation; reconstructing a
    schema through an unbound constructor is not an operational writer.
    """
    exists=connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cm36_supervisor_lease'"
    ).fetchone()
    if exists and connection.execute("SELECT 1 FROM cm36_supervisor_lease").fetchone():
        return True
    return False
