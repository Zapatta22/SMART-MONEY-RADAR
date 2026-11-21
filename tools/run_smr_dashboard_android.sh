#!/data/data/com.termux/files/usr/bin/bash
# Inicia o painel SMR local sem criar ou migrar bancos automaticamente.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v python >/dev/null 2>&1 || {
  echo "ERRO: Python não encontrado. Instale com: pkg install python" >&2
  exit 2
}

DB_PATH="${SMR_DB_PATH:-$ROOT/data/smr_history.sqlite3}"
case "$DB_PATH" in
  /*) ;;
  *) DB_PATH="$ROOT/$DB_PATH" ;;
esac

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERRO: banco SQLite não encontrado: $DB_PATH" >&2
  echo "O script não criará um banco vazio. Configure SMR_DB_PATH para o banco correto." >&2
  exit 2
fi

# Validação estritamente read-only: não cria tabelas nem executa migrações.
python - "$DB_PATH" <<'PY'
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve()
uri = path.as_uri() + "?mode=ro"
required = {
    "activity_events",
    "observed_transactions",
    "processed_signatures",
    "wallet_checkpoints",
    "swap_reconciliation_attempts",
}
try:
    connection = sqlite3.connect(uri, uri=True)
    try:
        present = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()
except sqlite3.Error as exc:
    print(f"ERRO: não foi possível abrir o banco em modo somente leitura: {exc}", file=sys.stderr)
    raise SystemExit(2)

missing = sorted(required - present)
if missing:
    print("ERRO: banco não contém o esquema esperado pelo painel.", file=sys.stderr)
    print("Tabelas ausentes: " + ", ".join(missing), file=sys.stderr)
    print("Nenhuma migração foi executada.", file=sys.stderr)
    raise SystemExit(2)
PY

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export SMR_DB_PATH="$DB_PATH"
export SMR_API_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(32))')"
# Private token file for authenticated local health probes.
STATE="${SMR_DASHBOARD_STATE_DIR:-$HOME/.local/state/smr-dashboard}"
mkdir -p "$STATE"
chmod 700 "$STATE"
if [[ -L "$STATE/health.token" ]]; then
  echo "ERRO: health.token não pode ser link simbólico." >&2
  exit 2
fi
printf '%s\\n' "$SMR_API_TOKEN" > "$STATE/health.token"
chmod 600 "$STATE/health.token"

echo
echo "SMART MONEY RADAR — painel local somente leitura"
echo "Abra no navegador deste mesmo Android: http://127.0.0.1:8765/"
echo "TOKEN TEMPORÁRIO (cole no campo de acesso do painel):"
echo "$SMR_API_TOKEN"
echo
echo "O token vale somente enquanto este processo estiver ativo."
echo "Não compartilhe o token. Para encerrar, pressione Ctrl+C."
echo

exec python -c 'from smart_money_radar.services.dashboard_http import main; main()' "$@"
