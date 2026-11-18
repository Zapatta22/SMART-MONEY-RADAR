#!/data/data/com.termux/files/usr/bin/bash
# Fluxo Android/Termux: preflight, coleta retomável e auditoria estrutural.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v python >/dev/null 2>&1 || { echo "ERRO: instale Python no Termux: pkg install python"; exit 2; }
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export SMR_SOLANA_RPC_URL="${SMR_SOLANA_RPC_URL:-https://api.mainnet-beta.solana.com}"
echo "SMR Android — somente leitura; endpoint público Solana; nenhum envio de transação."
python tools/check_solana_rpc.py
python tools/collect_solana_candidates.py \
  --candidate-file data/fixtures/candidates/solana_mainnet_candidates.json \
  --output data/fixtures/raw
python tools/audit_solana_fixtures.py data/fixtures/raw
echo "Fluxo concluído. As fixtures ainda exigem revisão semântica e anonimização antes de aprovação."
