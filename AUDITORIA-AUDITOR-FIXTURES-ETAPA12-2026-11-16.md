# Auditoria — Etapa 12: verificador offline de fixtures
Data: 2026-11-16

## Entrega
- `src/smart_money_radar/data_sources/fixture_audit.py`: auditor puro/offline para pares manifesto + JSON bruto.
- `tools/audit_solana_fixtures.py`: CLI para auditar todos os manifestos de um diretório.
- `tests/test_fixture_audit.py`: cinco testes automatizados.
- Atualizados README e procedimento de evidências.

## Verificações
- Campos obrigatórios e tipos básicos do manifesto.
- `commitment=finalized`, `encoding=json`, `anonymized=false`.
- Nome do arquivo bruto restrito ao diretório do manifesto (bloqueia path traversal).
- Integridade SHA-256 dos bytes brutos.
- Consistência de slot e assinatura entre manifesto e resposta `getTransaction`.
- Não acessa rede e não modifica evidências.

## Limites
- Auditoria estrutural não comprova autenticidade criptográfica da resposta do provedor nem correção semântica do swap.
- Não anonimiza dados, não aprova automaticamente fixture e não substitui revisão humana.
- Os cinco novos testes usam payloads sintéticos exclusivamente para testar o auditor; não são fixtures mainnet.
- Coleta real segue bloqueada por conectividade DNS/RPC; nenhuma chamada Helius ou endpoint pago foi usada.

## Validação
Suíte completa: **76 testes aprovados, 0 falhas** (71 anteriores + 5 novos). `PYTHONPATH=src python -m compileall -q src tests tools`: aprovado.
