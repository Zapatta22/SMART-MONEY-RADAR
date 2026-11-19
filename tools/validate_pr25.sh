#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

EXPECTED_BRANCH="feat/damm-v2-transaction-pipeline"
CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
  echo "ERRO: branch atual '$CURRENT_BRANCH'; esperado '$EXPECTED_BRANCH'."
  exit 2
fi

echo "==> Sincronizando a branch do PR #25"
git pull --ff-only origin "$EXPECTED_BRANCH"

echo
echo "==> Executando a suíte COMPLETA de testes (uma única rodada)"
PYTHONPATH=src python -m unittest discover -s tests -v

echo
echo "==> Compilando src/ e tests/"
python -m compileall -q src tests

echo
echo "VALIDAÇÃO COMPLETA: unittest e compileall concluídos com sucesso."
