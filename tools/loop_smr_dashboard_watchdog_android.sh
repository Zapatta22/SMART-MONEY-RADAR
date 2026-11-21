#!/usr/bin/env bash
# CM74 periodic local dashboard watchdog. Foreground process; no reboot persistence.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERVAL="${SMR_DASHBOARD_WATCH_INTERVAL:-60}"
MAX_FAILURES="${SMR_DASHBOARD_WATCH_MAX_FAILURES:-3}"
if [[ ! "$INTERVAL" =~ ^[0-9]+$ ]] || (( INTERVAL < 15 || INTERVAL > 3600 )); then
  echo "ERRO: intervalo deve estar entre 15 e 3600 segundos." >&2
  exit 2
fi
if [[ ! "$MAX_FAILURES" =~ ^[0-9]+$ ]] || (( MAX_FAILURES < 1 || MAX_FAILURES > 20 )); then
  echo "ERRO: limite de falhas deve estar entre 1 e 20." >&2
  exit 2
fi
if [[ -z "${SMR_DB_PATH:-}" || ! -f "$SMR_DB_PATH" ]]; then
  echo "ERRO: SMR_DB_PATH deve apontar para um banco existente." >&2
  exit 2
fi
command -v flock >/dev/null 2>&1 || { echo "ERRO: flock não encontrado." >&2; exit 2; }
STATE="${SMR_DASHBOARD_STATE_DIR:-$HOME/.local/state/smr-dashboard}"
mkdir -p "$STATE"
chmod 700 "$STATE"
exec 8>"$STATE/watchdog.lock"
if ! flock -n 8; then
  echo "ERRO: watchdog periódico já ativo." >&2
  exit 3
fi
failures=0
while :; do
  if bash "$ROOT/tools/watch_smr_dashboard_android.sh" 8>&-; then
    failures=0
  else
    failures=$((failures + 1))
    echo "AVISO: falha $failures/$MAX_FAILURES na recuperação do painel." >&2
    if (( failures >= MAX_FAILURES )); then
      echo "ERRO: limite de falhas atingido; watchdog encerrado." >&2
      exit 1
    fi
  fi
  sleep "$INTERVAL" 8>&-
done
