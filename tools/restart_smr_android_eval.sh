#!/usr/bin/env bash
# Reuse exactly one existing evaluation installation; never create or migrate.
set -euo pipefail
umask 077
if (($# > 1)); then echo "Uso: bash tools/restart_smr_android_eval.sh [diretorio-da-avaliacao]" >&2; exit 2; fi
base="${1:-}"
if [[ -z "$base" ]]; then
  shopt -s nullglob
  candidates=()
  for d in "$HOME"/smr-eval.*; do
    if [[ -d "$d/code" && -f "$d/evaluation.sqlite" && -x "$d/venv/bin/python" ]]; then candidates+=("$d"); fi
  done
  if (( ${#candidates[@]} != 1 )); then
    echo "Nenhuma ou várias avaliações encontradas. Informe explicitamente o diretório existente." >&2
    exit 2
  fi
  base="${candidates[0]}"
fi
base="$(cd "$base" && pwd -P)"
[[ -f "$base/evaluation.sqlite" && ! -L "$base/evaluation.sqlite" && -f "$base/code/tools/run_smr_dashboard_android.sh" && -f "$base/venv/bin/activate" ]] || { echo "Avaliação incompleta; nenhum arquivo foi criado." >&2; exit 2; }
source "$base/venv/bin/activate"
export SMR_DB_PATH="$base/evaluation.sqlite"
unset SMR_API_TOKEN
exec bash "$base/code/tools/run_smr_dashboard_android.sh" --host 127.0.0.1 --port 8765
