"""Prepare a fresh evaluation SQLite file, reading an optional original read-only."""
import os
import sqlite3
from pathlib import Path
from contextlib import closing
from smart_money_radar.storage.event_store import SQLiteEventStore

def prepare(destination, source=None):
    dest=Path(destination)
    if dest.exists() or dest.is_symlink():
        raise ValueError("evaluation destination already exists")
    if source:
        path=Path(source).expanduser().resolve(strict=True)
        origin=SQLiteEventStore(path,read_only=True)
        try:
            if origin.integrity_check()!=["ok"]:
                raise ValueError("source integrity failure")
        finally:
            origin.close()
        # Exclusive creation: do not overwrite an existing evaluation file.
        fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        os.close(fd)
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as src:
            with closing(sqlite3.connect(dest)) as dst:
                src.backup(dst)
    else:
        fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        os.close(fd)
        empty=SQLiteEventStore(dest)
        empty.close()
    validated=SQLiteEventStore(dest,read_only=True)
    try:
        if validated.integrity_check()!=["ok"]:
            raise ValueError("evaluation integrity failure")
    finally:
        validated.close()
    return dest

if __name__=="__main__":
    import sys
    prepare(sys.argv[1],os.environ.get("SMR_EVAL_SOURCE_DB"))
    print("Banco de avaliação verificado; origem preservada.")
