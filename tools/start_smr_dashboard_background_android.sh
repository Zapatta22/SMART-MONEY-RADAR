#!/usr/bin/env bash
# CM74: lifecycle helper for the loopback, read-only Android dashboard.
# Does not create/migrate SQLite databases or enable trading.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DB="${SMR_DB_PATH:-}"
if [[ -z "$DB" || ! -f "$DB" ]]; then
  echo "ERRO: informe SMR_DB_PATH com o caminho de um SQLite existente." >&2
  exit 2
fi
DB="$(cd "$(dirname "$DB")" && pwd)/$(basename "$DB")"
STATE="${SMR_DASHBOARD_STATE_DIR:-$HOME/.local/state/smr-dashboard}"
mkdir -p "$STATE"
chmod 700 "$STATE"
LOG="$STATE/dashboard.log"
PIDFILE="$STATE/dashboard.pid"
URL="http://127.0.0.1:8765/"
if command -v curl >/dev/null 2>&1 && curl --silent --max-time 2 --output /dev/null --fail "$URL"; then
  echo "Painel já responde em $URL. Nenhuma nova instância foi iniciada."
  exit 0
fi
if [[ -f "$PIDFILE" ]]; then
  oldpid="$(cat "$PIDFILE")"
  if [[ "$oldpid" =~ ^[0-9]+$ ]] && kill -0 "$oldpid" 2>/dev/null; then
    echo "ERRO: processo $oldpid ainda ativo, mas painel não responde. Inspecione $LOG" >&2
    exit 3
  fi
  rm -f "$PIDFILE"
fi
command -v curl >/dev/null 2>&1 || { echo "ERRO: curl não encontrado" >&2; exit 2; }
if command -v termux-wake-lock >/dev/null 2>&1; then termux-wake-lock || true; fi
nohup env SMR_DB_PATH="$DB" bash "$ROOT/tools/run_smr_dashboard_android.sh" \
  --host 127.0.0.1 --port 8765 >"$LOG" 2>&1 </dev/null &
pid=$!
printf '%s\n' "$pid" > "$PIDFILE"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl --silent --max-time 2 --output /dev/null --fail "$URL"; then
    echo "Painel disponível em $URL (PID $pid)."
    echo "Token privado no arquivo $LOG; não compartilhe seu conteúdo."
    echo "Execução em segundo plano; persistência após reinício do Android não garantida."
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 1
done
echo "ERRO: painel não respondeu. Inspecione o log privado: $LOG" >&2
exit 1
