#!/usr/bin/env bash
# CM37 evaluation, deliberately detached, version-pinned, loopback-only.
# Does not read credentials, trade, modify existing checkout or migrate a DB.
set -euo pipefail
umask 077
PIN="764e04a8d86de88511911de4e968672876c25ef2"
REPO="https://github.com/Zapatta22/SMART-MONEY-RADAR.git"
command -v git >/dev/null || { echo "Instale primeiro: pkg install git python"; exit 2; }
command -v python >/dev/null || { echo "Instale primeiro: pkg install git python curl"; exit 2; }
command -v curl >/dev/null || { echo "Instale primeiro: pkg install git python curl"; exit 2; }
if [[ $# -ne 0 ]]; then echo "Este instalador não aceita opções de rede." >&2; exit 2; fi
python -c 'import sys,sqlite3; assert sys.version_info >= (3,11), "Python 3.11+ necessário"'
BASE="$(mktemp -d "${HOME}/smr-eval.XXXXXXXX")"
echo "Avaliação isolada em: $BASE"
git init -q "$BASE/code"
git -C "$BASE/code" remote add origin "$REPO"
git -C "$BASE/code" fetch --depth 1 origin "$PIN"
git -C "$BASE/code" checkout --detach FETCH_HEAD
test "$(git -C "$BASE/code" rev-parse HEAD)" = "$PIN"
python -m venv "$BASE/venv"
source "$BASE/venv/bin/activate"
python -m pip install --disable-pip-version-check "$BASE/code"
python -c 'import sqlite3,websockets,google.protobuf; print("Dependências verificadas")'
cd "$BASE/code"
# Never adopt a preexisting SQLite file as a writable evaluation target.
# If the operator supplies SMR_EVAL_SOURCE_DB, validate and copy it using the
# SQLite backup API (including committed WAL content) from a read-only handle.
# Otherwise initialize a new empty evaluation file, not a production database.
python - "$BASE/evaluation.sqlite" <<'PY'
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
PY
export SMR_DB_PATH="$BASE/evaluation.sqlite"
echo "Abra neste Android: http://127.0.0.1:8765/"
echo "Para encerrar, Ctrl+C. Os arquivos isolados permanecem em $BASE."
exec bash tools/run_smr_dashboard_android.sh --host 127.0.0.1 --port 8765
