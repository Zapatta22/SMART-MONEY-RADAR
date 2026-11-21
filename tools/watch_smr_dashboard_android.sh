#!/usr/bin/env bash
# CM74 one-shot watchdog for the local, read-only Android dashboard.
# Designed for invocation by an external scheduler; does not install one.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${SMR_DB_PATH:-}"
if [[ -z "$DB" || ! -f "$DB" ]]; then
  echo "ERRO: SMR_DB_PATH deve apontar para um SQLite existente." >&2
  exit 2
fi
command -v python >/dev/null 2>&1 || { echo "ERRO: python não encontrado." >&2; exit 2; }
URL="http://127.0.0.1:8765/"
if python "$ROOT/tools/check_smr_dashboard_health.py"; then
  echo "Painel local responde; nenhuma ação necessária."
  exit 0
fi
echo "Painel local indisponível; tentando inicialização segura."
exec bash "$ROOT/tools/start_smr_dashboard_background_android.sh"
