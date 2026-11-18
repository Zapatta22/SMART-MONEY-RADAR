# SMR — Auditoria Etapa 16: execução assistida pelo Android

Data: 2026-11-16

## Objetivo

Reduzir a dependência do runtime que apresentou falha DNS, permitindo executar preflight, coleta somente leitura e auditoria estrutural em um Android com Termux.

## Entregas

- `tools/run_smr_android.sh`: fluxo de um comando; define RPC público Solana como padrão, executa `getHealth`, chama o coletor retomável e depois a auditoria offline.
- `tools/collect_solana_candidates.py`: deduplicação estável; coleta sequencial; auditoria imediata; retoma pares existentes somente quando bruto e manifesto existem e passam na auditoria; falha fechada para evidência parcial/inválida; nunca sobrescreve evidência.
- `tests/test_candidate_collection_runner.py`: quatro testes para deduplicação/coleta, retomada, evidência parcial e par inválido.
- `docs/fixtures/ETAPA16-EXECUCAO-ANDROID.md`: pré-requisitos, execução e limites.
- README atualizado.

## Validação local

- `PYTHONPATH=src:. pytest -q`: **95 testes aprovados, 8 subtests aprovados, 0 falhas**.
- `PYTHONPATH=src:. python -m compileall -q src tests tools`: aprovado.
- `bash -n tools/run_smr_android.sh`: aprovado.
- Nenhuma chamada RPC foi executada nesta etapa; não houve coleta real nem teste em dispositivo Android.

## Segurança e limites

- Endpoint padrão: `https://api.mainnet-beta.solana.com`, somente `getHealth` e `getTransaction`.
- Sem Helius, endpoint pago, credenciais, assinatura ou envio de transações.
- Retomada não sobrescreve dados: pares existentes são auditados; arquivos parciais ou inválidos interrompem o processo e permanecem intactos.
- Auditoria estrutural não valida semântica de swap, pools/vaults nem anonimização.

## Próxima tarefa

Executar `bash tools/run_smr_android.sh` em Android com Termux e internet funcional. Se o preflight passar, deixar a coleta e auditoria estrutural terminarem; depois fazer revisão semântica e anonimização controlada antes de aprovar qualquer fixture.

## Estado real

Etapa 16 implementada e testada localmente. Ainda não validada em Android; nenhuma fixture mainnet foi coletada/aprovada; SMR continua offline, somente leitura e sem operação 24/7.
