#!/usr/bin/env bash
# CM37 evaluation, deliberately detached, version-pinned, loopback-only.
# Does not read credentials, trade, modify existing checkout or migrate a DB.
set -euo pipefail
umask 077
PIN="671646c11a2aff479f1cf758583b177552be8d23"
REPO="https://github.com/Zapatta22/SMART-MONEY-RADAR.git"
command -v git >/dev/null || { echo "Instale primeiro: pkg install git python"; exit 2; }
command -v python >/dev/null || { echo "Instale primeiro: pkg install git python"; exit 2; }
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
python -m pip install "$BASE/code"
cd "$BASE/code"
# Never adopt a preexisting SQLite file as a writable evaluation target.
# If the operator supplies SMR_EVAL_SOURCE_DB, validate and copy it using the
# SQLite backup API (including committed WAL content) from a read-only handle.
# Otherwise initialize a new empty evaluation file, not a production database.
python - "$BASE/evaluation.sqlite" <<'PY'
from pathlib import Path
import os
import sqlite3
import sys
from smart_money_radar.storage.event_store import SQLiteEventStore
dest=Path(sys.argv[1])
if dest.exists():
    raise SystemExit("O destino de avaliação já existe.")
source=os.environ.get("SMR_EVAL_SOURCE_DB")
if source:
    path=Path(source).expanduser().resolve(strict=True)
    if not path.is_file():
        raise SystemExit("Banco de origem inválido.")
    original=SQLiteEventStore(path,read_only=True)
    original.close()
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as src:
        with sqlite3.connect(dest) as dst:
            src.backup(dst)
else:
    empty=SQLiteEventStore(dest)
    empty.close()
validated=SQLiteEventStore(dest,read_only=True)
if validated.integrity_check()!=["ok"]:
    raise SystemExit("Banco de avaliação não passou na integridade.")
validated.close()
print("Banco de avaliação verificado; origem preservada.")
PY
export SMR_DB_PATH="$BASE/evaluation.sqlite"
echo "Abra neste Android: http://127.0.0.1:8765/"
echo "Para encerrar, Ctrl+C. Os arquivos isolados permanecem em $BASE."
exec bash tools/run_smr_dashboard_android.sh
