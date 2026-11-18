# Adendo ao Registro Mestre SMR — inspeção local dos cinco fixtures RAW

Data: 2026-11-18 (UTC)
PR: #16 — feat/offline-fixture-inspector
Branch: feat/offline-fixture-inspector

## Evidência recebida do Termux

O usuário executou localmente o inspetor offline sobre SMART-MONEY-RADAR-ETAPA16/data/fixtures/raw, usando a cópia SMART-MONEY-RADAR-PR16.

Resultado agregado:
- Manifestos encontrados: 5.
- Pares íntegros: 5.
- Pares inválidos: 0.
- Os cinco payloads têm estrutura válida segundo o inspetor.
- Todos reportaram estado on-chain success.
- Todos têm slot e uma ou mais assinaturas.
- Todos têm snapshots pre/post token balances; todos os snapshots contabilizados possuem campo owner.
- Contagens: 10–17 account keys; 4–10 instruções principais; 1–3 grupos CPI; 2–14 instruções internas.
- Três payloads usam addressTableLookups; dois não.
- O tipo de version varia entre inteiro e texto.
- Nenhum dos cinco manifestos declara wallet_address ou monitored_wallet_address.

## Interpretação e limites

- A execução confirmou integridade de manifesto/hash e estrutura JSON/RPC para os cinco pares locais.
- O inspetor declarou network_access=false, database_access=false e writes_files=false.
- A saída não comprova a associação de qualquer transação à carteira monitorada. Não inferir carteira por fee payer, primeiro signatário ou posição em accountKeys.
- A presença de owner em snapshots de token balance não substitui a declaração explícita e verificável da carteira monitorada.
- Estado on-chain success significa que a transação não reportou erro de execução; não prova identificação semântica do protocolo/venue nem reconstrução completa dos swaps.
- Nenhum RAW foi enviado ao GitHub. Nenhum SQLite foi criado/migrado, nenhum dado foi importado, nenhum checkpoint foi avançado e nenhuma RPC/Helius ou operação on-chain foi executada.

## Próxima decisão técnica

Antes de qualquer importação histórica, definir um mapeamento explícito e verificável carteira↔transação para cada fixture (ou declarar formalmente que não existe associação disponível). Em seguida, especificar um importador offline em dry-run, sem avanço de checkpoint, sem sobrescrita silenciosa e com tratamento explícito de protocolos não suportados. Não criar banco nem executar importação até autorização explícita.

## Estado do PR

PR #16 continua Draft, aberto e não merged. A main, PR #14 e PR #15 permanecem preservados.
