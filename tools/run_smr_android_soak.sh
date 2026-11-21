#!/data/data/com.termux/files/usr/bin/bash
# Run the bounded offline SMR supervisor soak on an existing Termux installation.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
command -v python >/dev/null 2>&1 || {
  echo "ERRO: Python não encontrado no Termux." >&2
  exit 2
}
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -u "$ROOT/tools/smr_android_soak.py" "$@"
