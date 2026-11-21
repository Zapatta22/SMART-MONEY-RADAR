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

    def __post_init__(self):
        if (not self.database_path or self.database_path == ":memory:"
                or type(self.generation) is not int or self.generation < 1
                or not self.owner or self.radar not in ("launch","smart_money")
                or not callable(self.clock)):
            raise ValueError("invalid collector authority")


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
        if row is None:
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
        if controls["emergency_halt"] or controls["radars"][authority.radar] != "RUNNING":
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
