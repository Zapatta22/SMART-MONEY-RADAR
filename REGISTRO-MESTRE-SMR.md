# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-19 — continuidade e integração bank-aware da PR #23 em validação isolada

## 1. Estado executivo

Fase atual: preparação e validação de fixtures Solana reais para decodificadores por programa.
Prioridade V1: Solana; arquitetura extensível sem implementar multichain agora.
Estado real: monitor/coletor somente leitura, ingestão e persistência normalizadas, catálogo de programas, coletor RPC de fixtures, auditor offline e anonimizador de projeções implementados na cópia local de auditoria. O SMR completo não está integrado, em produção ou operando 24/7.

## 2. Continuidade e base

Base de entrada: `SMR-CODIGO-BASE-ETAPA12-2026-11-16.zip`, preservada e extraída para esta etapa. A suíte de referência registrada na Etapa 12 era 76/76. O pacote Etapa 13 contém as alterações desta etapa e passou em 86/86 testes.

## 3. Etapas consolidadas

- Etapas 1–6: robustez monitor/Helius, backfill, retries, shutdown, parser conservador, payload bruto/replay, integridade/backup e inventário.
- Etapa 7: contratos de domínio mínimos.
- Etapa 8: normalizador de transação.
- Etapa 9: integração do normalizador no WalletMonitor e persistência atômica no EventStore.
- Etapa 10: matriz de 15 programas Solana, classificação e cinco assinaturas públicas candidatas.
- Etapa 11: coletor JSON-RPC HTTPS somente leitura para `getTransaction` finalized, manifesto, SHA-256 e proteção contra sobrescrita.
- Etapa 12: auditor offline de evidências, integridade, manifesto, SHA-256, assinatura e slot.
- Etapa 13: anonimizador de projeção com mapa reversível separado e confidencial.

## 4. Entregas da Etapa 13

Arquivos novos:
- `src/smart_money_radar/data_sources/fixture_anonymizer.py`
- `tools/anonymize_solana_fixture.py`
- `tests/test_fixture_anonymizer.py`
- `docs/fixtures/ETAPA13-ANONIMIZADOR.md`

Arquivos atualizados:
- `README.md`
- `docs/fixtures/ETAPA10-MATRIZ-PROGRAMAS-E-FIXTURES.md` (alinhado `encoding=json` com o coletor Etapa 11 e resolução por account keys/loaded addresses).

## 5. Política técnica de anonimização

- O payload bruto original é somente lido; não é reescrito nem substituído.
- O bruto e a projeção têm SHA-256 independentes.
- Signers/fee payer são reconhecidos pelo `header.numRequiredSignatures` e também pelo `signer` de respostas `jsonParsed`.
- `owner` dos saldos SPL e token accounts indicadas por `accountIndex` são pseudonimizados.
- Program IDs explícitos e os resolvidos por `programIdIndex` (incluindo inner instructions e `meta.loadedAddresses`) são preservados.
- Mints são preservados automaticamente; pools, vaults e outras contas de protocolo devem ser identificadas e passadas por `--protect`. Outros endereços pessoais (ex.: destinatário SOL fora dos saldos SPL) devem ser revisados e passados por `--anonymize`; `--protect` tem precedência.
- Alias Base58 determinístico de 32 bytes é derivado com HMAC-SHA256 usando segredo local não persistido. Mesma chave/endereço gera o mesmo alias.
- Substituição em strings/logs ocorre por igualdade exata ou token Base58 completo; não há substituição por substring.
- Mapa reversível é gravado em arquivo separado com modo `0600`, fora da pasta de fixtures. O segredo não é salvo e o mapa não deve ser distribuído/commitado.
- Projeção, manifesto e mapa não sobrescrevem arquivos existentes. Manifesto de origem é auditado contra bruto, assinatura, slot e SHA-256 antes da transformação.

## 6. Validação

- Suíte completa: **86 testes aprovados, 0 falhas**.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- Os dez testes novos cobrem preservação byte a byte do bruto, anonimização de signer/fee payer, owner e token account, preservação de program IDs/mints/pools, logs, aliases estáveis, proteção explícita, loaded addresses/CPI, manifesto de origem, caminhos, segredo curto e sobrescrita.
- Testes locais/offline; nenhuma chamada RPC, Helius ou consumo de créditos.
- Payloads usados nos testes são construídos para testar o anonimizador; não são fixtures mainnet.

## 7. Limites e estado de evidência

- A conectividade DNS/RPC do runtime segue bloqueando coleta real. As cinco assinaturas documentadas continuam candidatas, não fixtures aprovadas.
- O anonimizador não faz decodificação semântica e não aprova transação.
- A lista de pools/vaults/contas de protocolo a preservar exige revisão por transação; não se deve anonimizar toda conta não-signatária.
- A cópia atual ainda não está sincronizada ao Replit, celular ou VPS.
- Nenhum decodificador de swap/launchpad/AMM foi aprovado com fixture real.

## 8. Restrições preservadas

- Solana V1; sem multichain nesta fase.
- Somente leitura; sem assinatura/envio de transações ou trades reais.
- Sem endpoints pagos, créditos Helius ou VPS sem autorização explícita.
- Não rotular payload sintético, resumo de explorer ou teste do anonimizador como fixture mainnet real.
- Launch Radar, Market Radar, Decision/Risk/Portfolio e execução financeira não entram nesta etapa.

## 9. Próxima tarefa exata

Antes de alterar o parser, reconciliar a cópia local do Termux com o repositório remoto. O caminho local `~/SMART-MONEY-RADAR-ETAPA16` foi identificado como diretório sem metadados Git; portanto, não executar `git pull`, não inicializar Git nessa pasta e não sobrescrever arquivos. A árvore atual da `main` remota contém `transaction_parser.py`, `domain/normalization.py` e `storage/event_store.py`, mas não contém os decodificadores Raydium CPMM/AMM v4 mencionados no trabalho local. A cópia local registrou esses decodificadores e regressão 25/25, ainda sem integração Git comprovada. A próxima ação é comparar e transportar com segurança esses arquivos e testes para uma branch baseada na `main` atual, preservando a cópia local e sem duplicar testes já aprovados.

Depois da reconciliação, implementar a reconstrução econômica em camada separada: associar instruções externas/CPI, deltas de saldo e contas/venues; gerar `SwapObservation`, `SwapClassification` e `SwapEvidence` sem inferir BUY/SELL quando houver ambiguidade; persistir os três registros de forma atômica no SQLite. Criar fixtures de transações reais anonimizadas e testes de regressão antes de avançar para Smart Money Intelligence e Risk Manager.

## 10. Protocolo de continuidade

Usar este registro, `REGISTRO-MESTRE-SMR-ATUALIZADO-2026-11-16-ETAPA16.md` e a `main` remota após o merge do PR #1 como referências atuais. Separar especificado, implementado, testado, validado remotamente e produção. Não declarar coleta/fixture real concluída até existir payload RPC integral finalized, hash conferido, proveniência e revisão semântica.

## 11. Atualização 2026-11-17 — PR #1

- Repositório: `Zapatta22/SMART-MONEY-RADAR`.
- PR #1: [Implement separated swap domain contracts](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/1).
- Branch de origem: `feat/swap-domain-contracts`; destino: `main`.
- Validação: workflow GitHub Actions `SMR tests` concluído com sucesso; etapas de instalação, suíte `unittest` e `compileall` aprovadas. PR sem conflitos e sem comentários/revisões pendentes.
- Merge concluído em 2026-11-17 21:21:44 (horário local UTC-4). Merge commit: `8e20bbdeeb2e7cdb1d785539c9b6504f47ed59e0`.
- Confirmação remota: PR fechado como merged e `main` aponta para o mesmo SHA.
- Arquivos integrados: `src/smart_money_radar/domain/models.py`, `tests/test_domain_models.py`, `docs/SWAP-DOMAIN-CONTRACTS.md`, `.github/workflows/smr-tests.yml`.
- Contratos agora existentes na `main`: `SwapObservation`, `SwapClassification`, `SwapEvidence` e `build_swap_operation_id()`.
- Limite: o PR não conectou parser/decodificadores, não alterou persistência SQLite e não habilitou execução de ordens. A integração econômica continua pendente.

## 12. Estado atual confirmado e limites

- A `main` remota está atualizada com o merge commit acima.
- Na árvore remota consultada após o merge existem `transaction_parser.py`, `domain/normalization.py` e `storage/event_store.py`; não foram encontrados arquivos de decodificadores Raydium CPMM/AMM v4 nessa árvore.
- O histórico local do Termux registra decodificador CPMM, mapeamento de contas e testes conjuntos CPMM/normalização/AMM v4 aprovados em 25/25. A pasta local informada não é um repositório Git; esses arquivos ainda precisam ser reconciliados com a `main` sem perda.
- Nenhuma integração parser→reconstrução econômica foi iniciada nesta etapa.
- O SMR permanece em monitoramento/análise somente leitura, sem execução de compras ou vendas reais.

## 13. Atualização 2026-11-18 — PR #5 Raydium CPMM exact-output

- Branch: `feat/raydium-cpmm-base-output`, criada a partir da `main` remota.
- PR #5: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/5 (aberto como draft; ainda não integrado).
- Arquivos novos no PR: `src/smart_money_radar/data_sources/raydium_cpmm_decoder.py`, `src/smart_money_radar/data_sources/raydium_cpmm_accounts.py`, `tests/test_raydium_cpmm_decoder.py`, `tests/test_raydium_cpmm_accounts.py`, `docs/RAYDIUM-CPMM-DECODER.md`.
- Decoder agora reconhece estruturalmente `SwapBaseInput` e `SwapBaseOutput`; o discriminator exact-output usado é `37d96256a34ab4ad`. O mapper exige pelo menos 13 contas-base e preserva contas adicionais em `remaining_accounts`.
- Limite preservado: argumentos de instrução são limites/quantidades solicitadas, não prova de valores efetivamente transferidos. Não foi implementada reconstrução econômica, CPI, classificação BUY/SELL, persistência nem execução.
- Testes novos são unitários/sintéticos; não são fixtures reais mainnet.
- GitHub Actions workflow `SMR tests` iniciou para o commit do PR (run 44221663324). No momento desta atualização, instalação estava em andamento e testes/compileall ainda pendentes; portanto, não registrar aprovação até consultar o resultado final.
- PR #5 continua draft e não mergeado. Não alterar `main` diretamente.

### Complemento PR #5 — camada RPC estrutural

- Acrescentados na mesma branch `src/smart_money_radar/data_sources/raydium_cpmm_analyzer.py` e `tests/test_raydium_cpmm_analyzer.py`.
- O analyzer resolve `programId`/ `programIdIndex`, account keys estáticas e loaded addresses (writable antes de readonly), decodifica swaps externos CPMM de input/output e preserva remaining accounts.
- Escopo explicitamente limitado a `message.instructions`: não interpreta `meta.innerInstructions`/CPI, não reconstrói deltas efetivos, não gera BUY/SELL e não persiste operações.
- CI executado no commit anterior à inclusão do analyzer: 110 testes aprovados e `compileall` aprovado. As alterações posteriores do analyzer ainda aguardam uma execução CI confirmada; não extrapolar o resultado anterior para os arquivos novos.
- Head atual da branch: `814309c50d6b0d06c99ce3024ba16f11bbe58117`. PR #5 permanece draft, aberto e não mergeado.

### Revisão técnica complementar — 2026-11-18

- Conferência em documentação oficial atual do Raydium: `SwapBaseInput` e `SwapBaseOutput` compartilham 13 contas-base; o discriminator de `SwapBaseOutput` é `37d96256a34ab4ad`. O sentido input/output segue a direção do usuário, não a ordem canônica do pool.
- Referências oficiais adicionadas a `docs/RAYDIUM-CPMM-DECODER.md`: instruções CPMM, implementação on-chain de SwapBaseOutput e exemplo do SDK.
- Testes de analyzer ampliados para resolver o program ID e contas em `loadedAddresses`, preservar uma conta extra carregada e confirmar explicitamente que `innerInstructions` ainda não são interpretadas como swaps nesta camada.
- Limite atual: a suíte CI de 110 testes foi aprovada no commit inicial do PR, antes dos últimos testes/refinamentos. O conector não retornou uma execução CI associada aos commits posteriores; portanto, não declarar os commits mais recentes validados por CI. A próxima verificação deve ser feita no próprio PR/Ações do GitHub antes de integrar.
- Últimos commits da branch: testes de loaded addresses/CPI-scope `5e77c88efae577d2e9dde66be5884dcb3572a16c`; referências oficiais `9ae034d01f714a9407f1eabc2b8ccfb78686ab32`. O registro mestre também é atualizado nesta branch; a main permanece intacta.

### Compatibilidade adicional do analyzer — 2026-11-18

- `raydium_cpmm_analyzer.py` agora aceita tanto índices numéricos (com resolução de static account keys e loaded addresses) quanto endereços já resolvidos em strings no vetor `accounts`.
- Novo teste cobre endereços resolvidos diretamente. Documentação delimita os formatos esperados: instrução com data Base58 e lista de contas; não declara suporte genérico a todos os formatos JSON-RPC.
- Testes explícitos mantêm a fronteira: innerInstructions/CPI continuam ignoradas nesta versão.
- Últimos commits de código/teste/documentação: `5905922c3d579456f7d8d5e4f0a5ea7851ce84a7` (teste) e `d5b42717fd9c026b66e6d0916e4316081897ae5a` (documentação). Nenhum CI posterior foi retornado pelo conector para esses commits; a validação final continua pendente. PR #5 não foi mergeado.

### Auditoria de integração para a próxima fase — 2026-11-18

Inspeção direta da `main` remota confirmou:

- `domain/models.py` já contém `SwapObservation`, `SwapClassification`, `SwapEvidence` e `build_swap_operation_id()`; os contratos exigem input/output amounts positivos, classificação BUY/SELL/UNKNOWN e evidência com program_id, venue, instruction_index e cpi_path.
- `domain/normalization.py` chama o parser atual e produz deltas agregados por carteira/mint; não atribui ainda deltas a instruções de swap individuais.
- `data_sources/transaction_parser.py` calcula diferenças agregadas entre preTokenBalances/postTokenBalances para o owner observado. Seu caminho de instruções internas atualmente agrega apenas transferências SOL do System Program; não reconstrói swaps SPL por CPI.
- `storage/event_store.py` atualmente persiste observed_transactions, activity_events, token_balance_deltas, processed_signatures e wallet_checkpoints. Não há tabelas específicas para SwapObservation, SwapClassification ou SwapEvidence.

Implicação: o próximo PR após a aprovação do PR #5 deve ser uma camada separada de reconstrução econômica por operação. Não se deve converter diretamente cada delta agregado em SwapObservation: isso confundiria múltiplos swaps na mesma transação. A camada deverá correlacionar instruções externas e CPI, token transfer instructions/eventos, contas de usuário/vault e deltas pré/pós; quando não houver evidência suficiente para separar quantidades por operação, deve produzir UNKNOWN/nenhuma observação econômica em vez de inventar valores. A persistência dos três contratos deve ser atômica e idempotente. Fixtures reais anonimizadas continuam sendo critério de validação antes da integração.

Estado atual do PR #5: branch contém analyzer CPMM para instruções externas, suporte a índices e pubkeys resolvidas, loaded addresses e testes explícitos que deixam CPI fora do escopo. CI completo comprovado apenas no commit inicial do PR (110 testes + compileall); alterações posteriores ainda precisam de execução CI confirmada. Não integrar até validar o head atual.

## 14. Atualização 2026-11-18 — PR #6: Raydium CPMM inner CPI

- PR #5 passou no GitHub Actions no commit `55833d81d166dca46f8973e655b4e22b29bb9829`: workflow `SMR tests` run `44221971607`, job `test` concluído com sucesso; log confirma `Ran 121 tests`, `OK`, e etapa `python -m compileall -q src tests` concluída com sucesso. PR #5 foi marcado ready for review (aberto, mergeable, não mergeado).
- Criada branch dependente `feat/raydium-cpmm-inner-cpi`, baseada na branch do PR #5, não na main. A separação evita misturar a decodificação externa (PR #5) com CPI (PR #6).
- O analyzer passa a percorrer `meta.innerInstructions`, correlacionar cada grupo ao índice da instrução externa e decodificar swaps CPMM encontrados em CPI. Resolve program IDs/contas por índices combinados ou endereços já resolvidos.
- Para rastreio, `instruction_index` registra a instrução externa, `inner_instruction_index` a posição linear dentro do grupo, `stack_height` preserva o nível RPC e `cpi_path` deriva índices hierárquicos de irmãos quando stackHeight está disponível. Sem stackHeight, usa posição linear sem afirmar hierarquia.
- Testes novos cobrem CPI direto, caminho aninhado, fallback sem stackHeight, ausência de innerInstructions, grupos duplicados e accountKeys em formato jsonParsed.
- Documentação registra que `innerInstructions=null` significa trilha não fornecida, não ausência de CPI; instruções plenamente parseadas sem bytes são ignoradas. Decodificar a instrução não equivale a reconstruir transferências SPL/deltas efetivos.
- PR #6 deve ser aberto como draft com base em `feat/raydium-cpmm-base-output` e head `feat/raydium-cpmm-inner-cpi`. Depende da integração prévia do PR #5. Ainda não há CI para este novo código até abrir o PR.
- Limites preservados: sem reconstrução econômica por operação, sem BUY/SELL, sem persistência dos três contratos, sem fixture real aprovada e sem execução de ordens.

### Refinamento de segurança da trilha CPI — 2026-11-18

- Revisado o cálculo de `cpi_path`: se um item intermediário não possui `stackHeight`, o analyzer limpa a pilha de ancestrais conhecida. Instruções posteriores não serão associadas a um pai possivelmente obsoleto; ficam em fallback linear até haver hierarquia demonstrável.
- Teste dedicado adicionado para a sequência stackHeight=2, sem stackHeight, stackHeight=3, garantindo que a terceira instrução não seja falsamente atribuída como filha da primeira.
- Workflow `.github/workflows/smr-tests.yml` no head do PR #6 foi ajustado para permitir `pull_request` com base `feat/**`, mas o workflow executado em PR é determinado pela configuração da branch-base. Como a branch-base do PR #6 é a branch do PR #5 e ainda mantém `pull_request: branches: [main]`, não há execução PR CI confirmada para PR #6 neste momento. A alteração no workflow dentro do head do PR #6, isoladamente, não comprova execução.
- PR #6 permanece draft e dependente do PR #5. Último commit funcional (analyzer, testes e documentação) registrado: `549c44422fa5523a16e14e61bd21931dd13a9c32`; commits posteriores atualizam somente o Registro Mestre. CI para o código novo continua pendente; não integrar.

### CI para PRs empilhados — ajuste 2026-11-18

- A branch-base do PR #6 é `feat/raydium-cpmm-base-output`; o workflow existente nessa base só aceitava PRs direcionados à `main`, portanto o PR #6 não disparava CI por evento pull_request.
- Corrigido o workflow na própria branch-base do PR #6 (branch do PR #5): `pull_request.branches` agora aceita `main` e `feat/**`. Commit: `2ac3a98c7c6deb4203e0cb8e01d4357879ffaf3f`.
- Isso permite validar PRs empilhados sem alterar a base/main. A branch do PR #6 também contém a mesma configuração para continuidade após integração.
- O commit de ajuste do workflow, por si só, ainda não é prova de CI aprovado. É necessário aguardar uma execução de PR #6 após um novo evento na branch head e conferir o job/log completo.

- Teste adicional em `tests/test_raydium_cpmm_analyzer.py`: garante que um grupo CPI com `index=1` seja associado à segunda instrução externa, sem deslocamento para o índice zero. Commit de código/teste: `578711b234033221fa89bf020bc7cdc419998863`.
- CI do PR #6 disparado após esse commit: run `44222435172`, job `134527348957`; na última consulta estava em execução, ainda sem conclusão. Não declarar aprovação até consultar o resultado final e os logs.

## 15. Atualização 2026-11-18 — validação PR #6 e auditoria do PR #4

### PR #6 — CPI Raydium CPMM
- CI do PR #6 concluído com sucesso: run `44222435172`, job `134527348957`; log confirma `Ran 128 tests`, `OK`, e `python -m compileall -q src tests` concluído.
- Commit de código/testes validado: `578711b234033221fa89bf020bc7cdc419998863`. O commit posterior `0f41f2e66ab099cf89d45eadaf7849cc1c6862da` atualizou apenas o Registro Mestre.
- PR #6 foi atualizado com evidência do CI e marcado como pronto para revisão (open, não merged, mergeable). Base: `feat/raydium-cpmm-base-output`; depende do PR #5. Link: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/6.
- Nenhum PR foi integrado nesta etapa.

### PR #4 — persistência dos contratos de swap já proposta
- Auditoria da lista de arquivos do PR #4 encontrou `src/smart_money_radar/storage/event_store.py` e `tests/test_swap_persistence.py`, além do Registro Mestre.
- O patch do PR #4 já implementa tabelas `swap_observations`, `swap_classifications` e `swap_evidence`; `save_swap_bundle` e `get_swap_bundle`; gravação em transação SQLite, idempotência, atualização de classificação/evidência, validação de operation_id determinístico, escopo Solana V1, FK/cascade e testes de rollback/precisão decimal.
- PR #4 é draft/open, CI informado no corpo: 107 testes aprovados no commit `36ca7d1c18f657387455753f4fb5ee09c79ce305`; sem reviews ou threads encontrados nesta consulta.
- Portanto, NÃO recriar a camada de persistência. Próxima integração deverá reutilizar/auditar PR #4 e conectar somente depois que uma reconstrução econômica por operação produzir valores sustentados por evidência.

### Estado técnico e limites
- PR #5: 121 testes aprovados no commit `55833d81d166dca46f8973e655b4e22b29bb9829`; pronto para revisão, não integrado.
- PR #6: 128 testes aprovados no commit de código/testes indicado acima; pronto para revisão, não integrado.
- PR #4: persistência dos três contratos já proposta e testada em draft; não integrada.
- Ainda não há fixture real de mainnet aprovada para Raydium CPMM nem reconstrução econômica por swap. Deltas atuais são agregados por wallet/mint e não devem ser convertidos automaticamente em operações individuais.
- Próxima fase correta: desenhar/testar a camada de reconciliação por operação (instruções externas + CPI + transferências SPL + token balance deltas e contas de pool), usando UNKNOWN/sem SwapObservation quando não houver atribuição inequívoca. Depois conectar aos contratos e à persistência já proposta no PR #4.

## 16. Atualização 2026-11-18 — especificação da reconstrução econômica

- Criada branch de trabalho `feat/raydium-cpmm-economic-reconciliation`, baseada no head da branch do PR #6 (`feat/raydium-cpmm-inner-cpi`), sem alterar `main` nem os PRs existentes.
- Criado `docs/RAYDIUM-CPMM-ECONOMIC-RECONSTRUCTION.md` no commit `793fac4a73f04e09a4544547f16a21969fc224da`.
- A especificação define correlação conservadora entre instrução CPMM, CPI, transferências SPL/Token-2022 e deltas por `accountIndex`; exige valores brutos/decimals exatos, validação de mint/programa, atribuição comprovada da carteira e detecção de account reuse/dupla contagem.
- Regra central: não gerar `SwapObservation` quando input/output efetivos ou carteira não puderem ser atribuídos sem ambiguidade. Argumentos de instrução e deltas agregados por wallet/mint não bastam.
- A especificação identifica a camada de persistência já proposta no PR #4; não recriar tabelas nem `save_swap_bundle`.
- Próximo trabalho de código: implementar primeiro extração tipada de transferências e deltas por token account como evidências independentes, com testes sintéticos de transfer/transferChecked, Token-2022, CPI e ambiguidades. Ainda não conectar ao armazenamento nem emitir observações até fixtures reais anonimizadas aprovadas.
- Esta branch contém apenas a especificação até agora; ainda não há PR #7 nem CI para a nova camada.

### Primeiro incremento de evidências de transferência — 2026-11-18

- Na branch `feat/raydium-cpmm-economic-reconciliation` foi adicionado `src/smart_money_radar/data_sources/solana_token_transfer_decoder.py` (commit de código inicial `3ec6e952ce75fd7fb1b545697fe137ed8af48152`).
- O decoder cobre SPL Token e Token-2022 para instruções base `Transfer` (opcode 3) e `TransferChecked` (opcode 12), em formato compilado Base58 e `jsonParsed`. Preserva programa, contas source/destination/authority, mint quando disponível, amount bruto, decimals, outer index, inner index, stackHeight, cpi_path e status on-chain.
- Testes adicionados em `tests/test_solana_token_transfer_decoder.py` para layouts compilados/parseados, Token-2022, loaded addresses, CPI aninhado, fallback sem stackHeight, transação falha, opcode não relacionado, dados malformados e grupos CPI duplicados. Teste adicional cobre `jsonParsed Transfer`. Commit de teste mais recente: `0b7072a2dbc3b6c43d0a68362560cca9559265ed`.
- PR #7 criado sobre PR #6: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/7. Mantido como draft porque não foi possível confirmar execução de CI para este PR; não declarar testes aprovados. Head de código/testes: `0b7072a2dbc3b6c43d0a68362560cca9559265ed`. Commit posterior atualiza apenas documentação.
- Limite explícito: ainda não decodifica `TransferCheckedWithFee` nem instruções de extensão Token-2022; amount bruto não prova valor líquido recebido. Não correlaciona transferências com swaps, não gera contratos de swap e não persiste.
- Referências oficiais registradas no documento de reconstrução: Solana Transfer Tokens e repositório Token-2022, que confirma layouts base idênticos byte a byte.

- CI do PR #7 concluído com sucesso: run `44222920649`, job `134528960023`; log confirma `Ran 140 tests`, `OK`, e `python -m compileall -q src tests` concluído.
- Commit de código/testes validado: `0b7072a2dbc3b6c43d0a68362560cca9559265ed`. Commits posteriores atualizaram documentação e Registro Mestre. PR #7 foi marcado pronto para revisão (open, não merged), mantendo dependência do PR #6.
- Run: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44222920649. PR: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/7.

### Correção semântica e CI final do decoder de transferências — 2026-11-18

- Ajustado `solana_token_transfer_decoder.py` para preservar explicitamente a variante declarada pelo RPC (`TRANSFER` versus `TRANSFER_CHECKED`), sem inferi-la pela presença opcional de mint/decimals. Anotações de retorno foram alinhadas.
- Adicionado teste para `jsonParsed transferChecked` mesmo quando os metadados opcionais de mint/decimals não estão presentes.
- CI final do código/testes: run `44223056961`, job `134529431226`, conclusão success; `Ran 141 tests`, `OK`, `compileall` aprovado.
- Commit de código/testes validado: `aa768da7c3641b55bec0c5345fc50bb46357a23f`. Alteração posterior do Registro Mestre é somente documental.
- PR #7 atualizado com essa evidência, open, mergeable, pronto para revisão, não merged; permanece dependente do PR #6. Link: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/7.

## 17. Atualização 2026-11-18 — deltas de saldo por token account

- Criada branch `feat/solana-token-account-deltas`, baseada na branch do PR #7 (`feat/raydium-cpmm-economic-reconciliation`), sem alterar main ou PRs anteriores.
- Novo módulo `src/smart_money_radar/data_sources/solana_token_balance_deltas.py` calcula deltas `post - pre` por `accountIndex`, preservando endereço da token account, mint, owner, valores brutos inteiros e decimals. Resolve account keys estáticas e loaded addresses.
- Falha de forma explícita se arrays pre/post estiverem ausentes, houver índice duplicado, mint/decimals/owner divergentes, amount bruto inválido ou accountIndex sem chave. Um lado ausente só vira zero quando ambos arrays existem e o índice aparece no outro lado (criação/fechamento). Transação falha retorna sem deltas; deltas zero são omitidos.
- Testes adicionados em `tests/test_solana_token_balance_deltas.py` para delta exato, contas do mesmo mint separadas, criação/fechamento, saldo inalterado, loaded address, arrays ausentes, duplicidade, mint/decimals, owner, amount malformado e transação falha.
- PR #8 criado como draft, dependente do PR #7: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/8. Commit de código/testes: `c84d90b68d8984b6fa2075df64228b40bdac9e0c`. CI run `44223162230` estava em execução na última consulta; não declarar aprovação até ler conclusão e logs.
- Limite: extração de deltas por conta ainda não atribui o delta a uma instrução/swap; não cria SwapObservation e não assume que payer é o proprietário econômico.

- CI do PR #8 concluído com sucesso: run `44223162230`, job `134529777305`; log confirma `Ran 153 tests`, `OK`, e `python -m compileall -q src tests` concluído.
- Commit de código/testes validado: `c84d90b68d8984b6fa2075df64228b40bdac9e0c`; commits posteriores atualizaram documentação/registro. PR #8 foi marcado pronto para revisão (open, não merged), dependente do PR #7. Link: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/8.

## 18. Atualização 2026-11-18 — correlator de transferências por operação CPMM

- Criada branch `feat/raydium-cpmm-transfer-reconciliation`, baseada em `feat/solana-token-account-deltas` (branch do PR #8). Não alterou `main` nem mergeou PRs anteriores.
- Novo módulo `src/smart_money_radar/data_sources/raydium_cpmm_transfer_reconciliation.py` correlaciona swaps CPMM decodificados com transferências SPL/Token-2022 e deltas por token account.
- A correlação usa as contas do layout CPMM: `input_token_account → input_vault` e `output_vault → output_token_account`; exige exatamente uma transferência por lado, programa token, mint/decimals compatíveis, owner comprovado igual nas duas token accounts e igual à carteira monitorada.
- Para swaps CPI exige stackHeight e prefixo cpi_path demonstráveis. Para swaps externos usa apenas o grupo innerInstructions da instrução externa. Não usa argumentos de swap como quantidades executadas.
- Soma transferências decodificadas de cada token account do usuário e compara com o delta pre/post agregado daquela conta. Isso permite múltiplos swaps sequenciais com reuso de token accounts sem dividir o delta por operação; transferência reivindicada por mais de um swap torna ambos AMBIGUOUS.
- Estados do diagnóstico: MATCHED, AMBIGUOUS e INCOMPLETE. Quantidades brutas só aparecem em MATCHED. Ainda não instancia SwapObservation/Classification/Evidence nem persiste.
- Testes em `tests/test_raydium_cpmm_transfer_reconciliation.py`: swaps externos e CPI aninhado, exclusão de siblings, ausência de stackHeight, duplicidade de transferências, programa/mint divergentes, mismatch transfer/delta, taxas ou transferências não decodificadas, owner/carteira, reuso de token accounts em swaps sequenciais, swap CPMM aninhado, delta duplicado e carteira ausente.
- Correção adicional propagada para a branch: `solana_token_transfer_decoder.py` agora decodifica corretamente bytes zero à esquerda na rotina Base58. O correlator também falha fechado para status não EXECUTED ou variantes de transferência não suportadas.
- CI ainda não consultado para esta branch/PR; não declarar testes aprovados até execução e leitura do log.
- Referências técnicas consultadas: Solana Transaction Introspection e RPC getTransaction (innerInstructions/stackHeight/account keys/loaded addresses); Raydium CPMM official instructions e implementação oficial do swap (13 contas e input/output accounts/vaults).
- Pendências: executar CI, revisar a semântica com fixtures mainnet anonimizadas, ampliar cobertura de variantes Token-2022/fees e só então considerar criar contratos SwapObservation e conectar à persistência já proposta no PR #4.

- CI do PR #9 concluído com sucesso: run `44223562333`, job `134531128207`; log confirma `Ran 169 tests`, conclusão success e `python -m compileall -q src tests` aprovado.
- Commit validado no PR head: `449129f9114420e4f136c0ad081c7820d2d0e399`. PR #9 foi marcado pronto para revisão, aberto, mergeable e não merged. Link: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/9.
- O CI também executou no commit de código `2645f85892b2e05808b95067d7dd07d532725b0b`; o PR run acima validou o head com a atualização documental do registro.

## 19. Atualização 2026-11-18 — builder dos contratos de domínio

- Criada branch `feat/swap-domain-bundle-builder`, baseada em `feat/raydium-cpmm-transfer-reconciliation` (PR #9), sem alterar main ou integrar PRs.
- Novo módulo `src/smart_money_radar/domain/swap_bundle_builder.py` transforma apenas resultados MATCHED do correlator em `SwapObservation`, `SwapClassification` e `SwapEvidence`.
- Quantidades são convertidas de inteiro bruto para Decimal usando decimals comprovados; não usa floats nem argumentos da instrução. operation_id é determinístico por chain, assinatura, índice externo e cpi_path.
- BUY/SELL só é atribuído quando exatamente um dos mints pertence à lista explícita `reference_mints`: input de referência = BUY; output de referência = SELL. Sem configuração ou quando ambos/neither são referência, classificação UNKNOWN/confiança zero.
- Resultados AMBIGUOUS/INCOMPLETE não geram contratos. O builder exige carteira MATCHED igual à carteira monitorada, rejeita evidência incompleta e IDs duplicados.
- O builder não persiste. A camada de persistência já existe em proposta no PR #4; não duplicar.
- Testes adicionados em `tests/test_swap_domain_bundle_builder.py`: Decimal exato, ID determinístico, BUY/SELL configurado, UNKNOWN sem referência, evidence/índice/CPI, ignorar resultados não matched, mismatch de carteira, evidência incompleta, IDs duplicados, metadados obrigatórios e mint de referência inválido.
- CI ainda pendente nesta atualização; não declarar validação até consultar Actions.
- Limite: a camada é sintética/unitária; ainda não foi validada com fixtures reais mainnet. Não existe integração de coleta/produção nem execução de ordens.

- CI do PR #10 concluído com sucesso: run `44223759455`, job `134531766338`; log confirma `Ran 181 tests`, conclusão success e `python -m compileall -q src tests` aprovado.
- Commit validado no PR head: `0b784a77dd922795674194b577c5f0f31355e478`. PR #10 foi marcado pronto para revisão, aberto, mergeable e não merged. Link: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/10.
- Testes do builder são sintéticos. Não existe fixture mainnet real aprovada, nem integração de persistência ou execução financeira.

## 20. Atualização 2026-11-18 — primeira fixture mainnet real e teste de integração

### PR #11 — coleta RPC pelo GitHub Actions
- PR: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/11; branch `feat/github-actions-mainnet-fixture-collector`, destino `main`; aberto, não merged.
- Workflow manual/branch: `.github/workflows/collect-solana-mainnet-fixture.yml`. Usa apenas `https://api.mainnet-beta.solana.com`, sem chave Helius, sem provedor pago e sem assinatura/envio de transação.
- Execução de coleta + anonimização + publicação da projeção: run `44224466171`, sucesso. O coletor recebeu `getTransaction` com `commitment=finalized`, `encoding=json`, `maxSupportedTransactionVersion=0`; slot `353586080`.
- Artefatos privados da execução: bruto + manifesto ID `14392017475` (retenção até 2026-11-25); projeção anonimizada ID `14392790584` (retenção até 2026-12-18). O bruto não foi commitado.
- A chave HMAC de anonimização é efêmera por execução; o mapa reversível fica somente no diretório temporário do runner e não é publicado.

### PR #12 — fixture anonimizada e integração fail-closed
- PR: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/12; branch `feat/real-mainnet-cpmm-fixture`, base `feat/swap-domain-bundle-builder`; aberto, mergeable/clean, não merged.
- Arquivos adicionados: `data/fixtures/mainnet/anonymized/raydium-cpmm-transient-output.json`, manifesto adjacente e `tests/test_real_mainnet_raydium_cpmm_fixture.py`.
- Proveniência: assinatura pública registrada no manifesto; slot `353586080`; transação version `0`; `meta.err=null`; JSON RPC bruto SHA-256 `a2067d162b2bd93f66db4ff86fcf51930bceeeeb223b5816833ec96f34cc5adf`; projeção anonimizada SHA-256 `c7d3c57683d90f48cc6d74162c53df79ebb695aacd3242f463f0dd2b011f4b60`.
- A projeção pseudonimiza quatro endereços pessoais/temporários e preserva 16 endereços explicitamente protegidos, incluindo programas, mints, pool, vaults e contas de protocolo. O mapa reversível não está no repositório.
- Conteúdo real observado: uma instrução externa Raydium CPMM `SwapBaseInput` no índice 6; duas instruções CPI SPL `TransferChecked`; quantidades brutas decodificadas `11371846366418` (6 decimals) e `244498263` (9 decimals); loaded addresses, pre/post token balances e logs presentes.
- O output WSOL usa uma token account temporária criada e fechada na mesma transação. Essa conta não aparece nos arrays `preTokenBalances`/`postTokenBalances`; portanto, não existe delta de token account que prove o owner e a saída líquida daquela conta. A reconciliação retorna corretamente `INCOMPLETE` por falta do delta pre/post; o builder retorna zero bundles. Não afrouxar essa trava nem presumir zero/owner.
- Teste de integração executa decoder CPMM, decoder SPL, extractor de deltas, reconciliador e builder com a projeção mainnet real; verifica também manifesto e SHA-256.
- CI push run `44224602490` e PR run `44224608030`: ambos success; log confirma `Ran 183 tests`, `OK`, e `python -m compileall -q src tests` aprovado.
- Limite: esta é a primeira fixture mainnet aprovada para teste de decodificação e rejeição segura, não um exemplo MATCHED. Nenhuma observação econômica foi gerada nem persistida.

### Próxima ação técnica
- Encontrar e coletar outra transação Raydium CPMM finalizada em que as duas token accounts do usuário tenham deltas pre/post e owner comprovado, para testar o caminho positivo `MATCHED` e o bundle BUY/SELL.
- Alternativamente, estudar suporte explícito a token accounts temporárias somente com prova on-chain de criação, inicialização, owner, transferências e fechamento; nunca inferir a saída apenas pelo delta SOL agregado.
- Não integrar persistência do PR #4, não declarar operação de produção e não habilitar execução financeira até existir validação positiva real e revisão independente.

## 21. Atualização 2026-11-18 — reconciliação dos vaults e edge case Token-2022 real

### PR #13 — reconciliação bilateral de token accounts e vaults
- PR: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/13; branch `feat/real-mainnet-cpmm-fee-fixture`, base `feat/real-mainnet-cpmm-fixture` (PR #12); aberto, não merged.
- Alteração em `raydium_cpmm_transfer_reconciliation.py`: agora exige e reconcilia deltas pre/post das duas token accounts do usuário **e dos dois vaults do pool**. A soma de todas as transferências decodificadas que afetam cada conta deve coincidir com o delta daquela conta.
- Isso fecha uma lacuna real: antes, uma transferência Token-2022 podia coincidir com o débito bruto da carteira, mas o crédito líquido no vault ser menor; como o reconciliador só verificava as contas do usuário, poderia produzir MATCHED sem provar o valor que entrou no pool.
- Testes sintéticos atualizados com deltas dos vaults; adicionados casos para vault delta ausente e divergência entre transferência bruta e variação líquida do vault.

### Segunda fixture mainnet real — Token-2022
- Coleta/anonymização/publicação via workflow run `44224903617`, sucesso; slot `344357800`; transação finalized, `meta.err=null`, version `0`.
- Fingerprint do payload bruto omitido do registro versionado.
- Projeção pseudonimizada: `data/fixtures/mainnet/anonymized/raydium-cpmm-token2022-fee.json`; hash atual `e63ad3fb799b208a5a4209587d3f11d3820476c472f297866a9b4ab244127a73`. Manifesto adjacente usa fixture_id sintético e não publica assinatura original nem fingerprint do payload bruto.
- Artefatos privados: bruto ID `14393115160` (7 dias); projeção ID `14393020518` (30 dias). Raw e mapa reversível não foram commitados; três endereços pessoais foram pseudonimizados e 12 endereços de programa/protocolo/pool/vault/mints protegidos.
- A transação tem um swap CPMM externo no índice 2 e duas transferências CPI `TransferChecked`: Token-2022 na entrada e SPL Token na saída. Quantidades brutas: `734738353` (6 decimals) e `1542848` (9 decimals).
- Débito da token account do usuário: `-734738353`; aumento líquido do vault de entrada: `+661264517`; diferença observada: `73473836` unidades brutas. Não inferir nem nomear a causa/valor de taxa sem decodificação explícita. O teste confirma somente que bruto e delta líquido não coincidem.
- A reconciliação agora retorna `INCOMPLETE` por divergência no vault de entrada; o builder não cria bundle. O vault de saída e a token account de saída reconciliam.

### Evidência de CI
- Push run `44225065832` e PR run `44225069345`: ambos success; `Ran 187 tests`, `OK`; `python -m compileall -q src tests` aprovado.
- O primeiro run após a mudança do reconciliador falhou porque os helpers sintéticos ainda não continham deltas de vault; os helpers foram corrigidos no commit seguinte e ambos os runs finais passaram.
- A fixture anterior de conta temporária continua testando fail-closed por falta de delta da token account de saída. A nova fixture testa fail-closed por divergência do vault. Ainda não há exemplo real MATCHED aprovado.

### Próxima ação técnica
- Buscar uma terceira transação CPMM sem divergência entre transfer amount e vault delta (SPL padrão ou Token-2022 sem efeito não decodificado), para validar o caminho positivo `MATCHED` com fixture real.
- Manter as duas travas atuais: delta de usuário obrigatório e delta de vault obrigatório. Não afrouxar por causa de fixtures que falham.
- Somente após fixture positiva real e revisão independente, avaliar integração do builder com a persistência já proposta no PR #4. Não fazer merge sem aprovação explícita.

## 22. Atualização 2026-11-18 — suporte RPC a transações Solana v1 e novos candidatos

### Coletor RPC — versão máxima 1
- Na branch do PR #11, `rpc_fixture_collector.py` agora solicita `maxSupportedTransactionVersion: 1` em vez de 0; mantém a versão recebida no manifesto.
- Adicionado teste que confirma request v1 e preservação de `version=1` no resultado/manifesto.
- PR #11: branch `feat/github-actions-mainnet-fixture-collector`, head atual `061bbf2fe0a950b39842731792db2ea3918f5ceb`; aberto, base `main`, mergeable/clean, não merged.
- CI push run `44225281047` e PR run `44225289565`: ambos success; `Ran 99 tests`, `OK`; compileall aprovado.
- O candidato de versão 1 inicialmente falhou com `maxSupportedTransactionVersion=0` (RPC code -32015); após a mudança, a coleta do mesmo candidato foi concluída com sucesso.

### Candidatos v1 inspecionados — ainda não fixtures aprovadas
1. **2hgi…** — raw artifact privado ID `14393050912`, run `44225286006`, slot `468317482`, version `1`, raw SHA-256 `e26bedf9768bb7dac1620014c5d2823fcd427616053ed7c977e461b7414fd341`. Tem CPMM dentro de CPI (grupo externo 1) e duas transferências SPL. A token account de entrada WSOL é criada e fechada na mesma transação, sem delta pre/post para essa conta; o caminho atual deve permanecer INCOMPLETE. Não foi commitado nem anonimizado.
2. **4Rb9…** — raw artifact privado ID `14392642326`, run `44225386752`, slot `470053225`, version `1`, raw SHA-256 `083d209435e4842a2cd48559ce281bbb4aecdaf58c26cc40f32f89a2c8c0c6c5`. Tem CPMM externo no índice 2, entrada persistente e conta WSOL de saída temporária criada/fechada, sem delta pre/post para a saída; caminho atual deve permanecer INCOMPLETE. Não foi commitado nem anonimizado.
- Os dois payloads brutos são artefatos privados de retenção de 7 dias; não foram adicionados ao repositório.

### Estado consolidado após esta atualização
- Fixture real 1: CPMM externo + conta de saída temporária; teste fail-closed por falta de delta da token account do usuário.
- Fixture real 2: CPMM externo + Token-2022; teste fail-closed por divergência entre transferência bruta e delta líquido do vault.
- Candidatos v1 adicionais: um CPMM CPI com conta de entrada temporária e um CPMM externo com conta de saída temporária; ainda não integrados ao conjunto de testes.
- Nenhuma fixture real produz MATCHED até agora. Nenhum bundle econômico foi gerado a partir de dados mainnet, nenhuma persistência nova foi conectada e nenhuma execução de ordens foi criada.
- PR #11, #12 e #13 permanecem abertos e não merged; PR #1 continua o único merge explicitamente confirmado desta cadeia recente.

### Próxima ação
- Encontrar uma transação CPMM v1/legacy com duas token accounts do usuário persistentes, ownership comprovado, e deltas de ambos os vaults que coincidam exatamente com as transferências decodificadas. Só essa fixture permitirá validar o caminho positivo MATCHED sem relaxar as salvaguardas atuais.

## 23. Atualização 2026-11-18 — novos candidatos v0/v1 e situação do caminho positivo

### Novos candidatos coletados por RPC (somente artefatos privados)
- **5fcjpg…** — run `44225543633`, artifact `14393200660`, slot `469869799`, version `0`, raw SHA-256 `70d21083c123baedcf2f2ea3757c213a6c00299123cc38b5645f8eb1761bb010`. Jupiter v6 com Raydium CPMM em CPI. O token account de entrada do usuário tem delta; a conta de saída WSOL não aparece nos deltas pre/post. Não é fixture positiva; manter INCOMPLETE.
- **Candidato multi-swap Jupiter** — run `44225638797`, artifact `14391914482`, slot `469955314`, version `1`; fingerprint bruto omitido do registro versionado. Uma instrução externa agregadora contém dois swaps CPMM CPI no mesmo grupo, com múltiplas token accounts, vaults e owners. Candidato para análise posterior de múltiplas operações; não foi anonimizado nem commitado e não deve ser tratado como fixture aprovada.
- **Zai2u…** — run `44225724731`, artifact `14393250687`, slot `469895550`, version `legacy`, raw SHA-256 `1bad458bd1252288b16083f52327d91659ed2d663a570e061601bc39a1d5a033`. CPMM externo no índice 4; a conta de entrada do usuário aparece apenas em `preTokenBalances`, sem par completo em `postTokenBalances`; não é fixture positiva.
- Todos os artefatos acima são privados, somente leitura, com retenção de 7 dias. Nenhum raw adicional ou mapa de anonimização foi commitado.

### CI e branch de coleta
- PR #11 head atual `7159e5f07549cb31bfe5b6558abfcf9fff0303c4`, base `main`, aberto, mergeable/clean, não merged.
- PR CI run `44225733787`: success; `Ran 99 tests`, `OK`; compileall aprovado. Inclui suporte a `maxSupportedTransactionVersion=1`.
- A busca já inspecionou transações CPMM externas, CPMM CPI via Jupiter/Axiom, versões legacy/v0/v1, Token-2022 e contas criadas/fechadas. A maioria dos candidatos SOL/WSOL fecha uma das token accounts na mesma transação; outros apresentam divergência de vault ou múltiplos swaps complexos.

### Estado e próxima ação
- Ainda não há fixture mainnet que passe MATCHED. Isso é uma lacuna real de validação, não motivo para enfraquecer as regras.
- Próximo passo: localizar swap token-token com contas de usuário persistentes e deltas de ambos os lados, ou analisar cuidadosamente o candidato multi-swap descrito acima sem presumir atribuição de owner/transferências.
- Não integrar persistência nem ativar execução financeira até existir caminho positivo comprovado por fixture real.

## 24. Atualização 2026-11-18 — fixture real Jupiter com dois swaps CPMM

### Coleta e anonimização
- Transação finalized, slot `469955314`, version `1`, `meta.err=null`.
- Assinatura e payload bruto permanecem documentados em manifesto privado/artefato de coleta; raw artifact run `44226316427`, retenção 7 dias. O bruto e o mapa reversível não foram commitados.
- Projeção pseudonimizada commitada: `data/fixtures/mainnet/anonymized/raydium-cpmm-jupiter-multiswap.json`; manifesto adjacente. Fingerprint do payload bruto omitido do registro versionado; hash atual da projeção: `d56a291093983c9ea2c2c5e92f66b2282d68504fb036188c404e2a8b9a214684`; 10 endereços substituídos, 16 endereços protegidos. Program IDs e mints foram preservados; contas pessoais foram pseudonimizadas.

### Resultado da inspeção
- Uma instrução externa Jupiter contém **dois swaps Raydium CPMM em CPI**, no mesmo grupo `innerInstructions`, índices internos 0 e 6, com caminhos CPI distintos.
- As duas operações são decodificadas separadamente e recebem operation IDs diferentes com base no CPI path.
- O swap CPMM 1 tem conta intermediária de saída sem delta líquido pre/post; o swap CPMM 2 tem conta intermediária de entrada sem delta líquido pre/post. As contas participam de transferências durante a rota, mas seus saldos no início e fim da transação são iguais.
- O reconciliador retorna `INCOMPLETE` para as duas operações, por ausência de delta de uma token account do usuário em cada swap. O builder retorna lista vazia. Não há divisão artificial de delta agregado nem criação de observações econômicas.
- A segunda operação também envolve Token-2022; a fixture Token-2022 anterior continua cobrindo explicitamente a divergência entre transferência bruta e delta líquido do vault.

### Testes e CI
- Novo teste: `tests/test_real_mainnet_raydium_cpmm_jupiter_multiswap.py`.
- PR #13 push CI run `44226455918`: **190 testes**, `OK`; `python -m compileall -q src tests` aprovado.
- Os três testes da nova fixture passaram: integridade do manifesto/hash, decodificação de dois CPIs distintos, e fail-closed individual sem bundles.
- Fixture/manifesto e teste estão no branch `feat/real-mainnet-cpmm-fee-fixture`, PR #13, head `d1a2d845b3026f39ec0c9a0df9172b8a600fae13`; PR aberto, não merged.

### Coletor reutilizável
- PR #11 branch inclui `.github/workflows/collect-solana-multiswap-fixture.yml`, workflow manual para coletar, anonimizar e publicar somente projeção + manifesto no branch de integração; raw e mapa reversível não são publicados no repositório.
- O primeiro run `44226316427` foi concluído com sucesso; a cópia final da fixture foi feita no branch do PR #13.
- O workflow foi ajustado para manual-only e target branch `feat/real-mainnet-cpmm-fee-fixture`, evitando coleta automática por push.

### Estado consolidado
- Agora existem três fixtures mainnet reais que testam comportamentos fail-closed: conta temporária de saída, divergência Token-2022 entre gross transfer e vault delta, e rota Jupiter com dois swaps CPMM e contas intermediárias sem delta líquido.
- Ainda **não existe** fixture real `MATCHED`; esse é o próximo critério de validação positiva.
- Não houve persistência nova, execução de ordens, assinatura ou submissão de transação.

### Próxima ação
- Procurar fixture mainnet com um swap CPMM direto token-token, sem contas intermediárias, com ambas as token accounts do usuário e ambos os vaults tendo deltas exatos que reconciliem com transferências suportadas. Manter todas as salvaguardas atuais.

## 25. Atualização 2026-11-18 — primeira reconciliação positiva mainnet (MATCHED)

### Mudança no decoder de deltas
- `decode_token_account_balance_deltas()` agora aceita `include_unchanged=True`. O padrão permanece `False`, preservando o comportamento anterior e os consumidores existentes.
- A opção preserva snapshots pre/post com delta zero. Isso permite verificar contas intermediárias de rotas agregadas: transferências de entrada e saída podem se compensar no saldo final, mas ainda precisam reconciliar exatamente.
- Adicionados testes para comportamento padrão, inclusão opcional e rejeição de valor não booleano.

### Resultado da fixture Jupiter — slot 469955314
- A fixture contém dois swaps CPMM em CPI no mesmo outer Jupiter, com caminhos CPI distintos.
- Com snapshots de delta zero incluídos:
  - **Swap CPMM 1:** `MATCHED`. A conta intermediária de saída recebe `1,390,888` unidades e envia as mesmas `1,390,888`; seu delta líquido é zero, mas as transferências reconciliam. A entrada da carteira foi debitada em `4,444,000,000`; desse total, `4,421,780,000` foram transferidos ao vault do pool e `22,220,000` seguiram para outra conta; ambas as transferências são consideradas na reconciliação da conta de entrada. O vault de entrada aumentou exatamente `4,421,780,000` e o vault de saída diminuiu exatamente `1,390,888`.
  - **Swap CPMM 2:** `INCOMPLETE`. A conta intermediária de entrada tem delta zero e suas transferências reconciliam, mas o Token-2022 transfere `670,380,262,328` unidades brutas para a conta de saída, enquanto o delta líquido da conta é `663,676,459,704`. A divergência impede o MATCHED.
- O builder gera **um bundle** para o primeiro swap, com quantidades exatas `4421.78` e `1.390888` (6 decimals) e classificação `UNKNOWN`, pois não foi configurado mint de referência. O segundo swap não gera bundle.
- Este é o primeiro caminho positivo `MATCHED` comprovado com fixture mainnet real. Não é ainda uma classificação BUY/SELL nem uma ordem negociável.

### CI
- PR #13 code head `84f2408242f447a7778755aa45ed18e443dbf872`; register-only head was subsequently updated.
- CI runs `44226758850` (code commit) and `44226848422` (register update): both **192 testes**, `OK`; `python -m compileall -q src tests` aprovado.
- Testes da fixture confirmam separação dos dois CPIs, MATCHED apenas para o primeiro, INCOMPLETE para o segundo e exatamente um bundle produzido.
- A opção `include_unchanged` não muda o padrão dos consumidores; só o teste de integração da rota opta explicitamente por ela.

### Próxima ação
- Revisar se a evidência de conta intermediária e a semântica do output do primeiro CPMM são suficientes para promover a lógica para o fluxo de ingestão; em paralelo, procurar outra fixture independente com caminho positivo e mints de referência explícitos.
- Só depois avaliar persistência usando a proposta do PR #4. Nenhuma execução de ordem foi criada.

## 26. Atualização 2026-11-18 — validação de SELL e triagem de candidatos independentes

### Classificação com referência explícita
- Na fixture positiva Jupiter (slot `469955314`), o bundle continua `UNKNOWN` quando nenhuma referência é configurada.
- O mesmo bundle foi reconstruído com `reference_mints={output_mint}`; a classificação resultou em `SELL`, pois o ativo de referência está no lado de saída. Isso é uma validação da regra do builder, não uma afirmação de que qualquer mint deve ser tratado automaticamente como stablecoin/quote.
- Teste renomeado para refletir o resultado real: `test_matches_first_hop_and_rejects_token2022_net_credit_mismatch`.
- CI run `44227447616`: **192 testes**, `OK`; `python -m compileall -q src tests` aprovado. PR #13 code head `611e5d324691b0e290c7582ec347ddc0c6c55508`.

### Triagem de novos candidatos mainnet
1. **3ptv…** — run `44227075425`, slot `468071665`, version `1`. Raydium CPMM CPI dentro de transação Fomo co-signer. As contas de usuário do swap não têm pares pre/post suficientes; manter `INCOMPLETE`.
2. **4taf…** — run `44227171030`, slot `468071640`, version `legacy`. CPMM externo no índice 2. Entrada da carteira e vault reconciliam; saída WSOL é conta temporária sem delta pre/post. Manter `INCOMPLETE`.
3. **5AJR…** — run `44227248247`, slot `462883338`, version `legacy`. CPMM externo no índice 4. Débito do token de entrada e crédito do vault coincidem; saída WSOL não tem delta de conta de usuário. Manter `INCOMPLETE`.
4. **66ksho…** — run `44227333154`, slot `462883357`, version `1`. CPMM externo no índice 2. Entrada Token-2022 e vault têm transferência compatível; saída WSOL termina em conta temporária com saldo pre/post zero e sem fluxo completo de saída decodificado. Manter `INCOMPLETE`.
5. **29fh…** — run `44226968509`, slot `470208240`, version `0`. Rota Jupiter v6 sem instrução do programa Raydium CPMM; aparecem outros programas de venue. Excluída da validação CPMM (pode servir futuramente para expansão multi-venue).

- Esses candidatos permaneceram em artefatos brutos privados de 7 dias; nenhum raw ou mapa reversível foi commitado. Não são fixtures aprovadas.
- Os exemplos WSOL mostram que a busca por uma segunda fixture positiva ainda precisa evitar contas criadas/fechadas durante a mesma transação.

### Próxima ação
- Procurar outra operação CPMM token-token com duas contas de usuário persistentes e deltas/vaults conciliáveis; preferir um par sem WSOL temporário. Repetir o processo de coleta, inspeção, anonimização e teste. Não relaxar o requisito de evidência.
- Após segunda fixture positiva independente, fazer revisão do caminho MATCHED e então considerar integração do builder à persistência proposta no PR #4.

## 27. Atualização 2026-11-18 — segunda fixture mainnet positiva MATCHED em rota multi-venue

### Coleta e artefato
- O workflow de coleta foi atualizado para o candidato da rota multi-venue; a coleta executou automaticamente após o commit, sem ação manual do usuário. A assinatura não é repetida neste registro.
- Run de coleta `44228609083`: sucesso. Job de RPC e upload de artefato concluídos.
- Artefato bruto privado `14394540849`, ZIP `smr-mainnet-candidate-raw-44228609083.zip`; expira em 7 dias. Contém payload RPC e manifesto.
- Slot `388739013`, versão `0`, commitment `finalized`, `meta.err=null`; fingerprint do payload bruto omitido do registro versionado.
- Projeção mínima pseudonimizada adicionada em `data/fixtures/mainnet/anonymized/raydium-cpmm-route-multivenue.json`, manifesto adjacente. Projection SHA-256 atual: `308f81447dbe9ed83937edc10d9907ccf77c7fd51974b2841af2391097ad633a`. Vinte endereços foram pseudonimizados; mapa reversível permanece fora do repositório.
- A projeção mantém todas as 21 posições internas e stackHeight, transferências relevantes, CPMM CPI, loaded addresses e quatro snapshots pre/post necessários. Instruções não relevantes foram reduzidas a programa/stackHeight, sem alterar a ordem dos CPIs. Documentação: `docs/MAINNET-CPMM-MULTIVENUE-FIXTURE.md`.

### Resultado econômico observado
- Um swap Raydium CPMM aparece como CPI interno `14`, dentro da instrução externa `2`, `stackHeight=2`, CPI path `(3,)`. Transferências de entrada/saída são descendentes em índices internos `15` e `16`, `stackHeight=3`.
- Input efetivo: `4,484,029,903` unidades brutas, 6 decimals = `4484.029903`.
- Output efetivo: `165,074,030` unidades brutas, 8 decimals = `1.65074030`.
- Conta de entrada da carteira: delta líquido zero, pois recebeu e enviou exatamente `4,484,029,903`; ambas as transferências foram decodificadas e reconciliadas.
- Conta de saída da carteira: delta `+74,030`, pois recebeu `165,074,030` e encaminhou `165,000,000`; o fluxo líquido coincide exatamente.
- Vault de entrada: delta `+4,484,029,903`; vault de saída: delta `-165,074,030`. Ambos coincidem com as transferências do swap.
- Resultado do reconciliador: `MATCHED`. Builder gera um bundle. Classificação padrão `UNKNOWN`; referência explícita no mint de entrada produz `BUY`, e no mint de saída produz `SELL`. Não se presume que qualquer mint seja stablecoin/quote.

### Testes e CI
- Novo teste `tests/test_real_mainnet_raydium_cpmm_multivenue.py`: verifica manifesto/hash, CPI identity, 10 transferências, saldo líquido zero de entrada, encaminhamento parcial da saída, deltas dos dois vaults, MATCHED e regras UNKNOWN/BUY/SELL.
- Primeiro CI do novo teste: run `44229045690`, falhou somente porque o hash esperado no manifesto não correspondia aos bytes gravados pela API do GitHub; o teste econômico de reconciliação passou. O hash foi corrigido para o valor observado pelo runner.
- Após corrigir o manifesto, CI run `44229136913` concluiu success. Run `44229184699`, no commit de documentação `98b1c52c19ffa14c3d9d4ea306fa1340ccac4174`, também concluiu success: `Ran 194 tests`, `OK`; `python -m compileall -q src tests` aprovado. O commit posterior `264d35cb25298e92d78867aa640f1c48529c3a6a` altera apenas este Registro Mestre.
- PR #13 permanece aberto, sem merge. Nenhuma ordem, assinatura ou submissão financeira foi criada.

### Estado consolidado e próxima ação
- Agora há duas fixtures mainnet positivas independentes para o caminho CPMM `MATCHED`: (1) rota Jupiter com duas operações CPMM, sendo a primeira MATCHED e a segunda INCOMPLETE; (2) rota multi-venue com uma operação CPMM MATCHED e contas intermediárias reconciliadas por todas as transferências.
- As fixtures fail-closed anteriores permanecem intactas: conta temporária sem delta, divergência Token-2022 gross/net, e swaps em rota sem prova completa.
- Próxima ação: revisar o diff agregado do PR #13 e a integridade das projeções antes de propor qualquer merge. Não fazer merge sem aprovação explícita do usuário.

- Confirmação final: PR #13 permanece open e mergeable; CI run `44229203783` concluiu success após a integração das novas fixtures e documentação. Atualizações posteriores deste Registro não alteram código. Nenhum merge foi executado.

## 28. Atualização 2026-11-18 — pseudonimização dos identificadores públicos das fixtures

### Correção aplicada na branch do PR #13
- Nas duas projeções CPMM positivas, as assinaturas on-chain foram substituídas por placeholder sintético Base58 de 64 bytes (`1` repetido 64 vezes); o `recentBlockhash` foi substituído por placeholder sintético de 32 bytes.
- Os manifestos públicos foram migrados para `smr.pseudonymized-fixture.v2`: usam `fixture_id` sintético, removem assinatura original, `raw_sha256` e nome de manifesto derivado da assinatura; mantêm o hash da projeção para integridade.
- O nome de arquivo da fixture Jupiter foi corrigido no manifesto para `raydium-cpmm-jupiter-multiswap.json`.
- Testes atualizados para gerar IDs de operação e bundles com `fixture_id`, e para rejeitar a presença dos campos públicos `signature` e `raw_sha256`.
- Documentação esclarece que as fixtures são pseudonimizadas, não anônimas: slot, horário, mints e quantidades reais continuam potencialmente correlacionáveis com dados públicos da Solana.
- Nenhum dado econômico, transferência, delta, mint ou resultado de reconciliação foi alterado intencionalmente. O hash da projeção foi recalculado para cada arquivo.

### Validação pendente
- Alterações realizadas somente na branch `feat/real-mainnet-cpmm-fee-fixture`; `main` não foi modificada e PR #13 não foi integrado.
- A CI precisa executar novamente os testes e `compileall` no novo head. Até essa execução, a alteração é código publicado na branch, mas não validada.
- A remoção dos identificadores diretos reduz exposição acidental, mas não garante não reidentificação; para isso seria necessário generalizar também metadados correlacionáveis, o que alteraria o caráter exato das fixtures.

## 29. Atualização 2026-11-18 — ressalva de histórico Git após pseudonimização

- A correção da seção 28 altera os arquivos no head atual, mas os commits anteriores da branch do PR #13 ainda preservam versões históricas das projeções e manifestos com assinatura original e fingerprint do payload bruto.
- Nenhuma reescrita de histórico foi executada. O repositório está privado; não ampliar o acesso nem publicar artefatos antes de decidir se a história do branch precisa ser reescrita.
- Uma reescrita exigiria reconstruir o histórico do PR com cuidado e poderia alterar os SHAs/referências dos commits. Não executar sem avaliar impacto e obter autorização explícita.
- Mesmo com limpeza de histórico, slot, horário, mints e quantidades reais preservados podem permitir correlação com a blockchain pública.

## 30. Atualização 2026-11-18 — validação redundante de evidências no builder

### Lacuna identificada e corrigida
- A revisão independente mostrou que o `swap_bundle_builder` confiava nos campos `MATCHED` sem revalidar se as quantidades declaradas na reconciliação eram iguais às quantidades das transferências anexadas, nem se as contas/CPIs das transferências correspondiam às contas do swap.
- O builder agora valida, antes de criar `SwapObservation`, que os valores brutos coincidem com as transferências; input/output usam as contas e programas SPL esperados; mints/decimals explícitos são consistentes; as transferências foram executadas e são de tipo suportado; e as transferências CPI são descendentes do CPI CPMM identificado.
- Também rejeita a reutilização da mesma instrução de transferência como input e output do mesmo swap.
- A verificação é uma segunda barreira no limite de domínio; não substitui a reconciliação e não altera as regras de classificação.

### Testes e CI
- Novo teste cobre quantidade divergente, conta de destino incorreta e caminho CPI não descendente.
- CI PR run `44233510799` no commit `cde1920a5aabde800dde09d38cc1f766fb2b6bb7`: **195 testes**, `OK`; `python -m compileall -q src tests` aprovado.
- O push run correspondente `44233504873` também concluiu sucesso.

### Compatibilidade com persistência
- PR #4 permanece draft, aberto e baseado em `main`; sua implementação `SQLiteEventStore.save_swap_bundle()` não está presente na branch do PR #13.
- A integração ainda não foi feita. O contrato compatível é chamar `save_swap_bundle(bundle.observation, bundle.classification, bundle.evidence)` somente depois de a transação pai real estar persistida em `observed_transactions`.
- Não mesclar PR #4 nem conectar persistência antes da revisão independente de seu esquema/migração e da definição da sequência correta entre branches empilhadas.

### Estado
- PR #13 continua aberto e não merged; head `cde1920a5aabde800dde09d38cc1f766fb2b6bb7`; base `feat/real-mainnet-cpmm-fixture`.
- `main` não foi alterada. Nenhuma ordem, assinatura ou submissão financeira foi criada.

## 31. Atualização 2026-11-18 — evidências de delta preservadas no bundle

### Mudança técnica
- A reconciliação `MATCHED` agora preserva, além das transferências e quantidades executadas, os quatro deltas brutos usados na decisão: token account de entrada, token account de saída, vault de entrada e vault de saída.
- O builder exige que os quatro deltas estejam presentes e sejam inteiros brutos (não booleanos) antes de criar os contratos de domínio.
- `SwapEvidence.evidence` agora registra explicitamente esses quatro valores, permitindo que a persistência e uma auditoria posterior recuperem por que a operação foi considerada reconciliada, inclusive nos casos de saldo líquido zero.
- Não houve mudança nos critérios de `MATCHED`, `INCOMPLETE` ou `AMBIGUOUS`, nem nas quantidades econômicas; os deltas são evidência adicional, não uma fonte substituta para os valores de transferência.

### Testes e CI
- Testes atualizados para verificar os deltas da fixture multi-venue e da rota Jupiter, além da rejeição de reconciliação sem delta e de delta com tipo inválido.
- CI push run `44233840405` no commit `d98680b47b3cf9fbaef4f40bf84dd22a9fbc1e63`: **196 testes**, `OK`; `python -m compileall -q src tests` aprovado.
- PR #13 continua aberto e não merged. A persistência proposta no PR #4 continua fora desta branch; não há integração de escrita no EventStore.

## 32. Atualização 2026-11-18 — pseudonimização da fixture negativa Token-2022

- A terceira projeção do PR #13 (`raydium-cpmm-token2022-fee.json`) também foi migrada para `smr.pseudonymized-fixture.v2`.
- Assinatura e recentBlockhash substituídos por placeholders sintéticos; manifesto agora usa `smr-fixture-raydium-cpmm-token2022-fee-v1`, remove `signature`, `raw_sha256` e nome de arquivo derivado da assinatura, e mantém hash da projeção.
- Teste de integração usa fixture_id e valida ausência dos identificadores/fingerprint originais.
- Slot, horário, mints e valores exatos foram mantidos para preservar o caso fail-closed de Token-2022; portanto, continua pseudonimizada e potencialmente correlacionável, não anônima.
- CI push run `44234097307` no commit `5fe434150647c2d46177c0b89151e51abdda1a85`: **196 testes**, `OK`; `python -m compileall -q src tests` aprovado.

## 33. Atualização 2026-11-18 — conferência das três fixtures no head atual

- Auditoria dos 18 arquivos alterados no PR #13 confirmou que as três projeções mainnet (`Jupiter multi-swap`, `multi-venue` e `Token-2022 fee`) usam assinaturas/blockhash sintéticos e que os três manifestos usam schema `smr.pseudonymized-fixture.v2`.
- Os três manifestos têm `fixture_id` sintético, `pseudonymized=true`, `anonymized=false`, sem campos `signature` ou `raw_sha256`; todos os `projection_file` correspondem ao nome real do arquivo.
- Busca no conjunto atual de arquivos alterados não encontrou as três assinaturas originais nem os três fingerprints brutos dessas fixtures.
- Os metadados econômicos preservados ainda permitem correlação on-chain. O histórico Git antigo ainda contém versões anteriores; nenhuma reescrita foi feita.
- O commit documental desta atualização ocorre após o CI `44234097307` e altera apenas este Registro Mestre. O código, fixtures, manifestos e testes do commit validado `5fe434150647c2d46177c0b89151e51abdda1a85` não foram alterados depois.

## 34. Atualização 2026-11-18 — revisão de compatibilidade PR #13 ↔ PR #4

### Cadeia de dependências confirmada
- PR #5 (`feat/raydium-cpmm-base-output`) parte da `main`.
- PR #6 (`feat/raydium-cpmm-inner-cpi`) usa PR #5 como base.
- PR #7 (`feat/raydium-cpmm-economic-reconciliation`) usa PR #6 como base.
- PR #8 (`feat/solana-token-account-deltas`) usa PR #7 como base.
- PR #9 (`feat/raydium-cpmm-transfer-reconciliation`) usa PR #8 como base.
- PR #10 (`feat/swap-domain-bundle-builder`) usa PR #9 como base.
- PR #12 (`feat/real-mainnet-cpmm-fixture`) usa PR #10 como base.
- PR #13 (`feat/real-mainnet-cpmm-fee-fixture`) usa PR #12 como base.
- PR #11 (coletor RPC) e PR #4 (persistência SQLite) são linhas separadas baseadas na `main`.
- Todos os PRs #5–#13 consultados continuam abertos e não merged. PRs #5–#9 e #12–#13 reportam mergeable; PR #10 reportou mergeable na consulta mais recente. Não alterar bases nem fazer merge em lote sem revisar a sequência e o estado atualizado de cada PR.

### Compatibilidade técnica confirmada
- PR #13 produz `SwapDomainBundle` com `observation`, `classification` e `evidence`, compatível com a assinatura pública de `SQLiteEventStore.save_swap_bundle(observation, classification, evidence)` do PR #4.
- O EventStore exige que a transação pai já exista em `observed_transactions`, identificada por `(wallet_address, signature)`; a FK composta e `ON DELETE CASCADE` também dependem dessa linha pai.
- Sequência proposta para o futuro adaptador:
  1. Receber payload RPC validado e assinatura real da transação.
  2. Executar `normalize_transaction(raw, wallet, signature)`.
  3. Persistir primeiro a transação pai com `save_observation(wallet, signature, raw, list(normalized.activity_events), normalized_observation=normalized)`.
  4. Decodificar swaps CPMM, transferências SPL e deltas por token account com `include_unchanged=True`.
  5. Executar reconciliação conservadora; apenas resultados `MATCHED` seguem ao builder.
  6. Chamar `build_swap_domain_bundles(..., signature=signature, ...)` usando a assinatura real, nunca o `fixture_id` de uma fixture de teste.
  7. Para cada bundle, chamar `save_swap_bundle(bundle.observation, bundle.classification, bundle.evidence)`.
- Os deltas armazenados na tabela legada `token_balance_deltas` são por mint/carteira, não substituem os deltas por token account/vault. A evidência detalhada do CPMM fica em `SwapEvidence`; o payload RPC pai permanece disponível para replay.
- `save_swap_bundle` é atômico para os três contratos de uma operação e idempotente por `operation_id`. A gravação do pai e dos bundles ocorre em transações separadas; em uma transação com vários swaps pode haver persistência parcial se o processo falhar entre bundles. Replay idempotente pode completar o restante, mas um adaptador futuro deve registrar/monitorar esse estado e testar recuperação após falha.

### CI e limites
- PR #4 head `817069c46bf23d67adf9a025360898a1a5ec6ced`: CI run `44218451061` success; **107 testes**, `OK`; `python -m compileall -q src tests` aprovado.
- PR #13 code validation permanece CI run `44234097307` no commit `5fe434150647c2d46177c0b89151e51abdda1a85`: **196 testes**, `OK`; compileall aprovado. Commits posteriores no branch foram documentais.
- A tabela `swap_observations` do PR #4 usa `CREATE TABLE IF NOT EXISTS`; isso não adiciona FK a uma tabela preexistente criada por uma versão anterior. O próprio histórico do PR registra que bancos antigos podem exigir rebuild/migração explícita. Não há DB de produção fornecido nem migração de produção executada.
- Não foi criado adaptador parser→reconciliador→EventStore nesta revisão. Não houve merge, alteração da `main`, assinatura, ordem ou submissão on-chain.

## 35. Atualização 2026-11-18 — branch de integração PR #14 e checkpoint diferido

- Criada branch `integration/pr13-sqlite-persistence` a partir do head atualizado do PR #13 (`a4e7a26fd75bd7612e330242211a5be77c39e4c1`).
- Aberto PR #14 em Draft, base `feat/real-mainnet-cpmm-fee-fixture` (não `main`): https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/14.
- Incorporado à branch de integração o `SQLiteEventStore` e os testes `tests/test_swap_persistence.py` do head do PR #4 (`817069c46bf23d67adf9a025360898a1a5ec6ced`). PR #4 permanece aberto e inalterado.
- Durante a integração foi identificado risco de avanço prematuro do checkpoint: `save_observation()` marcava a assinatura como processada antes de o parser/reconciliador/builder/persistência de swaps terminar. Uma interrupção nesse intervalo poderia fazer o monitor ignorar a repetição.
- Corrigido na branch #14 de forma retrocompatível: `save_observation(..., advance_checkpoint=True)` mantém o comportamento legado por padrão; quando `False`, arquiva o pai sem marcar a assinatura nem avançar checkpoint. Novo `mark_processed(wallet_address, signature)` exige que o pai exista e só então marca a assinatura e avança checkpoint.
- Adicionados testes para provar que o checkpoint permanece parado até depois da gravação do bundle e que `mark_processed` rejeita transação pai ausente.
- CI ainda não foi observada para o head `08acc5762e4ee1d7144835ee79c79fe26d5b1c99`; a execução não foi confirmada. Portanto, alterações permanecem não validadas por CI neste estado.
- Ainda não existe adaptador parser→reconciliador→builder→EventStore. A sequência futura deve chamar `save_observation(..., advance_checkpoint=False)`, persistir todos os bundles `MATCHED` e chamar `mark_processed()` apenas depois de completar o processamento da transação (inclusive quando não houver swap válido, após registrar o resultado).
- Nenhum PR foi integrado; `main` não foi alterada; nenhuma transação financeira foi assinada ou enviada.
## 36. Atualização 2026-11-18 — adaptador CPMM conectado ao WalletMonitor

### Implementação na branch do PR #14
- Criado `src/smart_money_radar/domain/raydium_cpmm_persistence_pipeline.py`, com `process_raydium_cpmm_observation()` e resultado tipado `RaydiumCpmmPipelineResult`.
- O adaptador aceita payload RPC direto ou envelope `result`, valida a assinatura externa contra `transaction.signatures` quando esse campo existe, normaliza a observação e arquiva o payload antes de processar swaps, sempre com `advance_checkpoint=False`.
- Para transação falhada on-chain ou sem swaps CPMM, arquiva e marca como processada após confirmar o resultado.
- Para swaps CPMM, executa decoder CPMM, decoder SPL/Token-2022, deltas por token account com `include_unchanged=True`, reconciliação, builder e persistência dos três contratos.
- Apenas bundles derivados de reconciliações `MATCHED` são persistidos. Qualquer `INCOMPLETE`, `AMBIGUOUS`, diferença entre quantidade de swaps decodificados e reconciliações, ou bundle ausente mantém o checkpoint parado.
- Bundles já gravados são idempotentes por `operation_id`; em falha parcial, o replay pode completar os restantes sem duplicar operações.
- Erros de parsing/reconstrução preservam o payload e gravam somente o tipo da exceção em `parse_error`, sem avançar checkpoint nem persistir texto potencialmente sensível da exceção.

### Integração com o monitor e recuperação
- `src/smart_money_radar/services/wallet_monitor.py` agora encaminha transações recebidas por WebSocket e backfill ao adaptador.
- `WalletMonitor` aceita `reference_mints` explícitos; sem configuração, classificação permanece `UNKNOWN` conforme o contrato do builder.
- `SQLiteEventStore.get_pending_signatures()` recupera observações arquivadas com payload que ainda não estão em `processed_signatures`.
- `_backfill_wallet()` tenta reprocessar pendências antes do backfill normal, inclusive quando ainda não existe checkpoint; nessa primeira execução, não inicia varredura histórica ampla.
- Pendências acima do limite configurado interrompem o processo sem avançar cursor. Transação que continue sem reconciliação completa faz o backfill parar e permanece recuperável.

### Testes e CI
- Testes novos cobrem orquestração MATCHED, transação sem CPMM, reconciliação incompleta, ausência de resultado do reconciliador, erro de normalização/reconstrução, assinatura RPC divergente, checkpoint diferido e replay de pendência na primeira execução.
- CI final de código/testes: run `44235755313`, commit `56d8509af0169bb11e9698460ba9c7e492a439b6`, **217 testes OK**, `python -m compileall -q src tests` aprovado.
- O commit posterior `a8aa3745dcb85d7b12b914f6d7f5bbeb341276d4` alterou somente `docs/CPMM-SQLITE-PIPELINE.md`; não mudou código nem testes.
- Execução: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44235755313

### Estado e limites
- PR #14 permanece Draft, aberto, mergeable e baseado em `feat/real-mainnet-cpmm-fee-fixture` (branch do PR #13), não em `main`.
- PR #14 ainda não foi integrado; `main` não foi alterada. PR #4 e PR #13 continuam separados e abertos.
- A integração cobre somente Raydium CPMM. Não há persistência de outros venues por este adaptador, nem tabela específica para motivos de reconciliação negativa.
- `save_swap_bundle()` é atômico por operação, não para todos os swaps da mesma transação; o checkpoint diferido e o replay idempotente protegem contra perda silenciosa.
- Não foi executada transação on-chain, assinatura, compra ou venda. O fluxo permanece observacional e de persistência.
### Validação adicional end-to-end com fixture mainnet
- Adicionado `test_real_mainnet_fixture_runs_end_to_end_through_sqlite_pipeline` em `tests/test_real_mainnet_raydium_cpmm_multivenue.py`.
- A fixture pseudonimizada real de mainnet agora percorre o adaptador completo: RPC wrapper → normalização → EventStore pai → decoder CPMM → transferências SPL → deltas → reconciliação `MATCHED` → builder → SQLite → checkpoint.
- Resultado verificado: 1 swap CPMM decodificado, 1 `MATCHED`, 1 bundle persistido, classificação `UNKNOWN`, quatro deltas preservados, payload bruto arquivado e checkpoint avançado somente ao final.
- CI atualizado: run `44235971430` (push) e run `44235978478` (pull_request), commit `9282bc3686f7a8a5a3c4224c387c440269c95c95`: **218 testes OK** e `python -m compileall -q src tests` aprovado.
- A revisão end-to-end cobre a fixture real multi-venue CPMM; não representa validação de outros DEX/venues nem execução on-chain.
### Validação end-to-end negativa e replay multi-swap
- Fixture Token-2022 com divergência entre transferência bruta e crédito líquido do vault: pipeline retorna `pending_reconciliation`, zero bundles, assinatura não processada e checkpoint inalterado.
- Fixture Jupiter multi-swap: duas instruções CPMM são decodificadas; primeira reconciliação `MATCHED`, segunda `INCOMPLETE`. O pipeline persiste somente o primeiro bundle e mantém a transação pendente.
- Reprocessamento da fixture Jupiter confirma idempotência: o bundle já existente não é contado como novo (`saved_bundles=0`), a segunda operação continua sem classificação/persistência positiva e o checkpoint permanece inalterado.
- CI final atualizado: runs `44236116100` (push) e `44236122222` (pull_request), commit `8a0b497eb0648aeed58947ce76b306916e3debf7`: **220 testes OK**, `python -m compileall -q src tests` aprovado.
- As três coberturas end-to-end agora incluem: fixture positiva multi-venue CPMM; fixture negativa Token-2022; rota Jupiter com um hop positivo e um hop incompleto.
## 37. Atualização 2026-11-18 — trilha persistente de auditoria de reconciliação

### Implementação
- `src/smart_money_radar/storage/event_store.py` define `SwapReconciliationRecord` e a tabela append-only `swap_reconciliation_attempts`.
- Cada linha registra `attempt_id`, carteira, assinatura, `operation_id`, índice da instrução, índice interno, caminho CPI, status, motivo técnico e horário.
- Status permitidos: `MATCHED`, `INCOMPLETE`, `AMBIGUOUS` e `UNRESOLVED`.
- A tabela tem FK para `observed_transactions` e índice por carteira/assinatura. Não depende de `swap_observations`, porque resultados negativos precisam existir sem bundle positivo.
- `save_swap_reconciliation_attempt()` grava todos os swaps de uma tentativa atomicamente; cada replay gera novo `attempt_id` e preserva o histórico anterior.
- `get_swap_reconciliation_attempts()` recupera o histórico em ordem de gravação; `storage_stats()` agora inclui a contagem da tabela.
- O adaptador `process_raydium_cpmm_observation()` grava um resultado por swap decodificado antes de persistir bundles. Se faltar resultado do reconciliador, grava `UNRESOLVED` com motivo explícito e mantém checkpoint parado.
- Os resultados negativos não viram `SwapObservation`/`SwapClassification`/`SwapEvidence` positivos e não alteram critérios de aceitação.

### Testes e evidência
- Testes cobrem append-only em duas tentativas, preservação do motivo, validação de status, exigência de observação pai e persistência de `MATCHED`, `INCOMPLETE` e `UNRESOLVED` no pipeline.
- Fixtures mainnet ampliadas: multi-venue confirma trilha `MATCHED`; Token-2022 confirma `INCOMPLETE`; Jupiter multi-swap confirma `MATCHED` + `INCOMPLETE` e histórico repetido após replay.
- CI PR #14: run `44237232546`, commit de código/testes `ff5a50001d2585e03f015eb2085503879f78ccae`, **223 testes OK** e `python -m compileall -q src tests` aprovado.
- O commit `f433cc1066074d52ba7037aaf09036d5d7ed5f7a` posterior à execução CI altera apenas `docs/CPMM-SQLITE-PIPELINE.md`; não modifica código ou testes.
- Runs anteriores `44237061928` e `44237077540` falharam por fixtures mock sem identidade `swap`; corrigidos com swaps simulados contendo instruction index/CPI path. A execução PR subsequente `44237232546` passou.

### Estado
- PR #14 permanece Draft, aberto, mergeable e baseado em `feat/real-mainnet-cpmm-fee-fixture`; não foi integrado à `main`.
- Nenhuma transação on-chain, assinatura, compra ou venda foi executada.
### Integridade adicional da identidade de auditoria — 18/11/2026
- `save_swap_reconciliation_attempt()` agora recalcula `operation_id` a partir de chain Solana, assinatura, índice da instrução e caminho CPI, rejeitando qualquer identidade divergente antes da gravação.
- Teste negativo dedicado confirma rejeição de `operation_id` não determinístico; teste de FK usa identidade válida para alcançar e comprovar a rejeição por observação pai ausente.
- CI PR #14 final: run `44237431650`, commit `bec4ad3bea7eec1d4076fadaddb10d68e731c1d9`, **224 testes OK** e `python -m compileall -q src tests` aprovado. Push run correspondente: `44237424906`.
- Runs `44237364127`/`44237373440` falharam porque o teste de observação pai ausente inicialmente usava `operation_id` inválido; corrigido para identidade determinística, após o que a execução PR #14 passou.
- Head PR #14 após validação: `bec4ad3bea7eec1d4076fadaddb10d68e731c1d9`; Draft, aberto, mergeable, não mergeado. `main` intacta.

## 38. Atualização 2026-11-18 — consultas e diagnóstico do histórico de reconciliação

### Implementação inicial na branch/PR #15
- Criada a branch `feat/reconciliation-diagnostics` a partir do head do PR #14 (`894b1b0db413f10a456a63f22d2d715e2c6c4cc1`), sem alterar a `main`, PR #14 ou PR #4/#13.
- Aberto PR #15 em Draft: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/15, base `integration/pr13-sqlite-persistence`.
- `SQLiteEventStore.query_swap_reconciliation_attempts()` consulta trilha por carteira, assinatura, `operation_id`, status e intervalo de data/hora, com limite validado e ordem mais recente primeiro.
- `SQLiteEventStore.get_reconciliation_diagnostics()` agrega número de tentativas, operações e assinaturas distintas, contagens de `MATCHED`, `INCOMPLETE`, `AMBIGUOUS` e `UNRESOLVED`, motivos recorrentes e observações arquivadas não processadas.
- O relatório devolve a contagem total de pendências e até 100 detalhes para evitar resposta sem limite.
- Testes adicionados para agregação de status/motivos/pendências, filtros e ordenação de consultas, além de validação de parâmetros.
- Commits iniciais: implementação `5e0ad5ebf11ae594083a49f5a55aab381f025b40`; testes `21be683b949443c40dadeeb0a3a658e990a866e8`. A documentação foi atualizada em commit separado nesta branch.
- CI de código/testes no commit `21be683b949443c40dadeeb0a3a658e990a866e8`: run `44238405072` success, **227 testes OK** e `python -m compileall -q src tests` aprovado. Commits posteriores nesta branch alteraram somente documentação/registro; o código e os testes executados são os mesmos do commit validado.
- Para permitir CI em PRs empilhados com base `integration/**`, o workflow `.github/workflows/smr-tests.yml` foi ampliado na branch do PR #14; PR #14 CI run `44238553367` passou com **224 testes OK** e compileall aprovado. Essa mudança não altera o código do pipeline.
- PR #15 permanece Draft e aberto; PR #14 permanece Draft e aberto; PR #13 e PR #4 permanecem abertos; nenhum merge foi executado e a `main` permanece intacta.
- Nenhuma transação on-chain, assinatura, compra ou venda foi executada.

### Próxima ação
- Consultar o CI do PR #15. Se falhar, corrigir somente a causa apontada e aguardar nova execução. Se passar, revisar os contratos de retorno e ampliar consultas por período/status conforme necessário antes de avançar para integração de painel/API.

## 39. Atualização 2026-11-18 — serviço somente leitura para diagnósticos (PR #15)

### Implementação
- Após conferir o head real do PR #15, confirmado que a camada de consulta já estava implementada no EventStore; não foi recriada.
- Criado `src/smart_money_radar/services/reconciliation_diagnostics.py` com `ReconciliationDiagnosticsService` como fachada de aplicação somente leitura.
- `get_report()` delega para `SQLiteEventStore.get_reconciliation_diagnostics()`; `list_attempts()` delega para `query_swap_reconciliation_attempts()`. Os filtros e limites permanecem validados pelo EventStore.
- O serviço não oferece operações de gravação, alteração de checkpoint, replay ou execução on-chain.
- Criado `tests/test_reconciliation_diagnostics_service.py` com testes de delegação, retorno e superfície sem métodos de mutação.
- Documentada a separação entre EventStore, serviço de aplicação e futura API/interface em `docs/CPMM-SQLITE-PIPELINE.md`.

### Estado de validação
- Arquivos de código/testes adicionados em commits sequenciais na branch `feat/reconciliation-diagnostics`: serviço `7b95ca889f4e87a39af651fe7c26f2b4e6d82c63`; testes `30817e85f60c93a376e21fa41b31e8f92e67fa3c`.
- A suíte de 227 testes e compileall do commit anterior `21be683b949443c40dadeeb0a3a658e990a866e8` não valida estes dois novos arquivos; CI posterior ainda precisa confirmar a nova implementação.
- PR #15 continua Draft, baseado em `integration/pr13-sqlite-persistence`; não alterar a `main` nem fazer merge automático.
- Nenhum endpoint, dashboard ou interface visual foi criado nesta etapa. Nenhuma assinatura ou transação on-chain foi executada.

### Próxima ação
- Aguardar CI do head atualizado do PR #15; se passar, revisar contrato de resposta e decidir a próxima fronteira de integração com API/painel. Se falhar, corrigir apenas a causa apontada pelo CI.

## 40. Atualização 2026-11-18 — resumo de leitura para futuro dashboard (PR #15)

### Implementação
- Confirmado CI completo do commit `b0df50a23edaf60e680e57958c186db2869e59a8`: workflow `44238955912` concluído com sucesso.
- Criado `src/smart_money_radar/services/dashboard_read.py` com `DashboardReadService` para compor estatísticas de armazenamento, diagnóstico de reconciliação e até 20 eventos recentes persistidos.
- O retorno é marcado `mode=read_only` e normaliza `datetime`, `Decimal` e tuplas para formato serializável em JSON.
- Filtro opcional por carteira; sem chamadas de rede, gravações, avanço de checkpoint ou execução de transações.
- Criado `tests/test_dashboard_read_service.py` com testes de composição, serialização, injeção de dependência e ausência de operações de mutação.
- Documentada a fronteira entre serviço de leitura e futura camada HTTP/UI em `docs/CPMM-SQLITE-PIPELINE.md`.

### Validação e estado
- Serviço de dashboard commit `86321c76f911f0a89224f4485bb92caba9d764a7`; testes commit `6c5752281d1d80e1b7b4cd4742f9faa3b76f32e4`.
- CI para o novo código ainda precisa concluir; os 227 testes anteriores e o CI do serviço de diagnóstico não cobrem esta adição.
- PR #15 permanece Draft, aberto, sem merge e baseado em `integration/pr13-sqlite-persistence`. `main` permanece intacta.
- Nenhum servidor HTTP, endpoint REST, autenticação ou painel gráfico foi criado. Nenhuma chamada RPC ou transação on-chain foi executada.

### Próxima ação
- Aguardar CI do head atualizado. Após aprovação, decidir e especificar o adaptador HTTP mínimo, incluindo autenticação local, limites de consulta e política de exposição dos dados antes de abrir qualquer porta de rede.

### Adendo de validação — dashboard read service
- CI `44239180470` falhou em 1 dos 233 testes devido somente à expectativa incompleta do mock em `tests/test_dashboard_read_service.py`. O método de produção encaminhou os argumentos padrão corretos; o teste esperava apenas `wallet_address`.
- Corrigido o teste para verificar também `since=None`, `until=None` e `top_reasons_limit=10`. Commit corretivo: `41614511bced2c6467677d9d7cb0aa7ecefa0bd0`. Aguardando novo CI; não considerar validado até sucesso.

## 41. Atualização 2026-11-18 — adaptador HTTP local somente leitura (PR #15)

### Validação anterior
- CI `44239234802` concluído com sucesso no commit de correção `41614511bced2c6467677d9d7cb0aa7ecefa0bd0`; testes unitários e compileall aprovados.

### Implementação nova
- Criado `src/smart_money_radar/services/dashboard_http.py` com `create_read_only_server()`, baseado apenas na biblioteca padrão Python.
- Endpoints GET: `/health`, `/api/v1/dashboard`, `/api/v1/reconciliation/attempts`.
- Segurança: token Bearer obrigatório (mínimo 32 caracteres), comparação constante, host exclusivamente loopback, sem CORS, sem métodos de escrita, `Cache-Control: no-store` e `nosniff`.
- Servidor não inicia sozinho. Nenhum host público, porta de rede externa, execução RPC ou transação foi habilitado.
- Criado `tests/test_dashboard_http.py` cobrindo autenticação, respostas, 404, 405 e rejeição de configuração insegura.
- Commits de implementação/testes: `db02cbc7c705755fa02cc3b2bb49879ac74a6876` e `5311381df039d38f44b5b60a0af7b1ec7bf00a16`. CI novo ainda precisa passar.

### Próxima ação
- Aguardar CI do head atualizado e corrigir somente falhas demonstradas. Manter PR #15 Draft e não fazer merge.

## 42. Continuação 2026-11-18 — comando para iniciar a API local

- CI do adaptador HTTP inicial: run `44239424161` passou integralmente (job de testes e compileall).
- Adicionado entry point `smr-api` em `pyproject.toml` e função `main()` em `services/dashboard_http.py`.
- O launcher exige `SMR_API_TOKEN` (32+ caracteres), usa `SMR_DB_PATH` ou `data/smr_history.sqlite3`, não carrega configurações Helius e não habilita RPC/rede Solana.
- `--host`/`--port` configuráveis; a validação do servidor continua recusando qualquer host não-loopback.
- Ctrl+C encerra servidor e fecha EventStore.
- Testes adicionados em `tests/test_dashboard_http_main.py` para token obrigatório e ciclo de vida de encerramento.
- Commits: launcher `025af8b28277f036e5af79b4e10e6e9ace128fd3`, entry point `61df0b483b3188067ad5a3a092ddfd394fad1c75`, testes `6e69218610f444aa67f24c1108c235368712f0a1`.
- CI desta etapa ainda pendente; manter PR #15 Draft até conclusão.

### Próxima ação
- Verificar CI do head atualizado; corrigir apenas falhas reais. Depois revisar limites de query e cobertura de erros HTTP antes de qualquer uso pelo Android.

## 43. Correção CI do launcher — 2026-11-18

- Run `44239651757` falhou no passo `Install project`; log aponta `tomllib.TOMLDecodeError` na linha 17 do `pyproject.toml`, antes de executar testes ou compileall.
- Causa identificada: a entrada `smr-api` foi gravada na mesma linha de `smr` com os caracteres literais `\\n`.
- Correção aplicada no commit `ec8445224ca88070f83cac9fb12862348fc876f1`; arquivo relido e agora contém as duas entradas em linhas TOML separadas.
- Não houve alteração da lógica da API para corrigir esse erro.
- CI de revalidação ainda precisa concluir. Portanto, launcher e seus testes ainda não estão validados por CI.

### Próxima ação
- Acompanhar o workflow disparado pela correção; se a instalação passar, examinar o resultado dos testes e compileall. Se falhar, usar o log específico antes de qualquer nova alteração.

## 44. Proteção de volume no endpoint de auditoria — 2026-11-18

- Revisão do `query_swap_reconciliation_attempts()` identificou que o EventStore exige limite positivo, mas não impõe teto máximo.
- Para impedir consultas HTTP excessivas, o adaptador agora valida `limit` de 1 a 500 (padrão 100) antes de chamar o serviço.
- Valores menores que 1 ou maiores que 500 retornam HTTP 400; novo teste cobre `limit=501`.
- Commits: validação HTTP `2f93d3fa5d58a6be4bcd11dfd98c8a2485a4e1a8`; teste `d3b320a7e0d06a46f72f4f3cbf83a2576df7fbdd`.
- CI precisa validar os commits desta proteção e a correção TOML anterior.

## 45. CI aprovado — launcher e limite HTTP (2026-11-18)

- CI run `44239943317` concluído com sucesso no commit `8e509d8f6963e965b9d1f005f84c4d06c9f3d70a`.
- Instalação do pacote aprovada após correção do TOML.
- **241 testes unitários aprovados**.
- `python -m compileall -q src tests` aprovado.
- Inclui testes do `smr-api` (token obrigatório, ciclo de vida e fechamento), adaptador HTTP e limite de consulta 1..500.
- PR #15 permanece aberto, Draft, mergeable; base `integration/pr13-sqlite-persistence`; sem merge. `main` intacta.

### Próxima ação
- Fazer revisão final de contrato e comportamento do adaptador (incluindo bind de host loopback, lifecycle e respostas de erro), depois preparar uma estratégia segura de conexão do painel Android. Não expor a API externamente sem TLS/autorização adicional e decisão explícita.

## 46. Primeiro painel visual local — 2026-11-18

- Adicionada interface HTML servida em `/` e `/dashboard` pelo adaptador local.
- A página é estática e não autenticada, mas não retorna dados privados; chamadas à API continuam exigindo Bearer token.
- Token informado pelo usuário permanece somente na memória JavaScript; não é gravado em armazenamento persistente do navegador.
- Exibe métricas de reconciliação, quatro status, motivos recorrentes, eventos recentes e tabela de tentativas com filtro de status.
- Valores recebidos são inseridos por `textContent`; cabeçalhos CSP, `no-store` e `nosniff`; nenhuma dependência externa.
- Servidor continua limitado a loopback; sem CORS, acesso remoto, RPC ou escrita.
- Commits: painel `d4de89da1eba73ad8fea97ac99711b22bb500f26`; teste HTTP `ac8dd700e2a795d6440e0a6cdfefa2bd8bae8967`.
- CI ainda pendente; painel não deve ser considerado validado até execução de 242+ testes e compileall.

### Próxima ação
- Aguardar CI do painel; corrigir apenas falhas reais. Depois avaliar no Android a melhor forma de iniciar e abrir `http://127.0.0.1:8765/` localmente.

## 47. CI aprovado do painel visual local — 2026-11-18

- CI run `44240284448` concluído com sucesso.
- Instalação do pacote: aprovada.
- **242 testes unitários aprovados** (`Ran 242 tests ... OK`).
- `python -m compileall -q src tests`: aprovado.
- Inclui teste da página local HTML sem autenticação de conteúdo, presença dos cabeçalhos de segurança e manutenção de autenticação nas rotas JSON.
- PR #15 continua aberto, Draft, mergeable, base `integration/pr13-sqlite-persistence`; sem merge. `main` intacta.
- Commit do painel `d4de89da1eba73ad8fea97ac99711b22bb500f26`; teste `ac8dd700e2a795d6440e0a6cdfefa2bd8bae8967`; CI run `44240284448`.

### Próxima ação
- Revisar e preparar instruções de execução no Termux/Android sem ativar a API remotamente. Antes de orientar a execução real, confirmar o método de instalação/execução do pacote no ambiente do usuário e se o banco local existe; não criar um banco vazio que possa ser confundido com o histórico real.

## 48. Inicializador Android/Termux seguro para o painel — 2026-11-18

- Criado `tools/run_smr_dashboard_android.sh`.
- Exige banco SQLite já existente; se não existir, aborta sem criá-lo.
- Verifica em conexão SQLite `mode=ro` a presença das tabelas `activity_events`, `observed_transactions`, `processed_signatures`, `wallet_checkpoints` e `swap_reconciliation_attempts`; banco incompleto é rejeitado sem migração.
- Gera token temporário de 256 bits com `secrets.token_hex(32)`, exibe para entrada manual no painel e não grava em arquivo.
- Define `SMR_DB_PATH`, `PYTHONPATH`, inicia `smr-api` via módulo Python e permanece loopback-only; não ativa RPC/Helius.
- Criado `tests/test_dashboard_android_launcher.py` com sintaxe bash, ausência de banco sem criação e banco incompleto sem migração.
- Commits: launcher `e42e2a8f3fc94e7c773b183f5d1a4236a8ab5dc6`; testes `16c21733427e5549f494942e1146123815ec1fd4`.
- CI ainda pendente para os três novos testes.

### Próxima ação
- Aguardar CI; se aprovado, preparar instrução única e simples para o usuário executar no Termux, somente depois de confirmar caminho do banco real.

## 49. CI aprovado do inicializador Android — 2026-11-18

- CI run `44240462766` concluído com sucesso no head `a8699f0388b80979de298cfa31d86f1703108ae3`.
- **245 testes unitários aprovados** (`Ran 245 tests ... OK`).
- `python -m compileall -q src tests`: aprovado.
- Inclui testes de sintaxe Bash, ausência de criação de banco inexistente e ausência de migração em banco incompleto.
- O script Android não foi executado em dispositivo real; validação CI não substitui teste no Termux do usuário.
- PR #15 permanece aberto, Draft, mergeable, base `integration/pr13-sqlite-persistence`; sem merge. `main` intacta.

### Próxima ação
- Antes de pedir execução no Android, confirmar existência e caminho do banco histórico real do usuário. O script aborta se não encontrar o arquivo ou as tabelas esperadas, sem modificar o banco.

## 50. CI final do registro e estado de prontidão do painel — 2026-11-18

### Validação documental
- Workflow GitHub Actions run `44240525942`, disparado pelo commit documental anterior, terminou com sucesso.
- Job `test`: instalação do projeto, execução da suíte unitária e `python -m compileall -q src tests` concluídos com sucesso.
- Não houve alteração de código/testes entre o CI de código do launcher (run `44240462766`, 245 testes) e este CI documental. O novo run confirma também o head documental então vigente.
- Head consultado antes desta atualização: `9ed34a09de2dfe050eb87a2317139e6ec631342b`.
- PR #15 continua aberto, Draft, mergeable e não mergeado; base `integration/pr13-sqlite-persistence`. `main` intacta.

### Estado real do painel
- Implementação e CI concluídos para API local somente leitura, interface HTML e launcher Termux.
- Ainda não comprovados no dispositivo do usuário: execução real em Android/Termux, localização do banco SQLite correto, integridade/schema desse banco e exibição de dados reais.
- Não executar o launcher por enquanto: seu caminho padrão `data/smr_history.sqlite3` não foi confirmado como banco histórico real. Não criar banco vazio, migrar ou sobrescrever dados.
- A coleta RPC anteriormente executada em `~/SMART-MONEY-RADAR-ETAPA16` não comprova que o EventStore SQLite recebeu os bundles e as tabelas necessárias.

### Próxima ação exata
- Identificar, sem abrir nem modificar conteúdo, os arquivos SQLite existentes dentro da pasta do projeto Termux e seus subdiretórios. Só depois inspecionar schema em modo somente leitura e decidir se algum é o banco histórico adequado.
- Se nenhum banco compatível existir, planejar uma etapa explícita de ingestão/persistência no EventStore antes de usar o painel. Não apresentar o painel como operacional com dados reais até essa validação.
- Manter PR #15 e PR #14 em Draft; PR #13 e PR #4 preservados. Nenhum merge para `main`, RPC adicional, assinatura ou operação financeira autorizados por esta etapa.

## 51. Investigação da ausência de SQLite no Termux — 2026-11-18

### Evidência recebida do dispositivo
- O usuário executou uma busca por arquivos .db, .sqlite e .sqlite3 em ~/SMART-MONEY-RADAR-ETAPA16; nenhum caminho foi retornado.
- Isso não prova ausência de bancos fora dessa pasta nem exclui um caminho personalizado em SMR_DB_PATH; nenhum caminho externo foi confirmado.

### Auditoria dos scripts e do fluxo remoto
- tools/run_smr_android.sh executa check_solana_rpc.py, collect_solana_candidates.py com saída em data/fixtures/raw e audit_solana_fixtures.py. Não instancia SQLiteEventStore, não chama smr watch e não persiste bundles SQLite.
- src/smart_money_radar/cli.py implementa smr watch PUBLIC_ADDRESS; esse caminho instancia SQLiteEventStore(settings.database_path) e WalletMonitor.
- HeliusSettings.database_path usa por padrão <raiz-do-projeto>/data/smr_history.sqlite3, salvo override por SMR_DB_PATH.
- HeliusSettings.from_environment() exige SMR_ALLOW_NETWORK=true (ou equivalente aceito) e HELIUS_API_KEY. Portanto, smr watch habilita conexões WebSocket/RPC Helius e não deve ser iniciado sem decisão explícita do usuário.
- No fluxo PR #14, o monitor encaminha transações para process_raydium_cpmm_observation(), que arquiva payload, reconcilia CPMM, registra tentativas e persiste bundles. Esse código está em branch empilhada/PR aberto; não há evidência de que a pasta local Etapa 16 contenha essa versão.
- O painel/launcher PR #15 exige schema SQLite já existente e valida em modo somente leitura; não deve criar ou migrar o banco.

### Conclusão e limites
- A ausência do SQLite é compatível com o uso anterior do script de coleta/auditoria: esse script produz fixtures JSON, não banco histórico.
- Não foi provado que dados coletados estejam perdidos; eles podem existir como JSON em data/fixtures/raw. Também não foi inspecionado o conteúdo local desses arquivos.
- Não executar smr watch, não criar banco manualmente, não alterar .env, não iniciar Helius e não iniciar o painel até confirmar a versão local e a configuração de armazenamento.
- Nenhuma alteração de código foi feita nesta investigação.

### Próxima ação segura
- Verificar somente o caminho efetivo configurado para o banco, sem imprimir chave Helius nem outros segredos: se SMR_DB_PATH estiver definido, mostrar apenas esse caminho; caso contrário, informar que a configuração padrão do código remoto é data/smr_history.sqlite3 sob a raiz do projeto. Em seguida, confirmar se o caminho existe. A verificação não deve iniciar Python do SMR, importar configurações que leiam .env, conectar à rede, criar arquivos ou migrar banco.

## 52. Atualização 2026-11-18 — ausência do SQLite padrão e CI documental final

- O usuário executou a verificação de `SMR_DB_PATH` no diretório `~/SMART-MONEY-RADAR-ETAPA16`.
- Resultado: variável `SMR_DB_PATH` não definida; caminho padrão resolvido para `/data/data/com.termux/files/home/SMART-MONEY-RADAR-ETAPA16/data/smr_history.sqlite3`; arquivo não encontrado.
- Em conjunto com a busca anterior por `.db`, `.sqlite` e `.sqlite3` sem resultados na árvore Etapa16, não há banco SQLite identificado nessa cópia/caminho. Isso não prova perda de dados JSON nem exclui um banco em outro diretório.
- Nenhum banco foi criado, aberto para escrita ou migrado. Nenhum comando `smr watch`, Helius ou RPC foi iniciado.
- CI do commit documental `62be8e34b511e1793e24f3f4163728cc97b8e3ae`: run `44240917136`, job `test`, conclusão `success`; instalação, testes unitários e compileall concluídos com sucesso.
- PR #15 permanece aberto, Draft, mergeable e não merged; head continua `62be8e34b511e1793e24f3f4163728cc97b8e3ae`; base `integration/pr13-sqlite-persistence`. `main` permanece intacta.
- Próxima ação segura: inventariar somente os arquivos JSON coletados em `data/fixtures/raw` e confirmar se a cópia local possui o código/branch esperado. Não inicializar monitoramento Helius nem criar banco até definir explicitamente a configuração e o consentimento para rede.

## 53. Verificação dos fixtures JSON locais — 2026-11-18

### Evidência recebida do Termux
- O usuário executou corretamente o comando de busca por arquivos .json em data/fixtures/raw.
- O comando não produziu saída.
- Como erros foram suprimidos por 2>/dev/null, o resultado prova apenas que nenhum arquivo .json foi listado nesse caminho. Não distingue entre diretório inexistente, diretório vazio ou ausência de arquivos com essa extensão.
- Não concluir que todos os fixtures foram perdidos nem que não existam em outros diretórios do projeto.

### Estado e segurança
- Banco SQLite padrão já não foi encontrado na cópia local; esta verificação também não localizou JSON em data/fixtures/raw.
- Nenhum arquivo foi criado, alterado ou removido. Nenhum banco foi criado/migrado; nenhum monitoramento Helius/RPC foi iniciado.
- PR #15 foi consultado: aberto, Draft, não merged, mergeable; head c6d52aceb770b30846682f6aad2afd2c8ee4be80, base integration/pr13-sqlite-persistence. CI run 44240917136 confirmado success (instalação, testes unitários e compileall). main permanece sem alteração nesta etapa.

### Próxima ação segura
- Fazer inventário somente de arquivos sob a pasta data da cópia local, sem suprimir erros e sem abrir arquivos: listar diretórios/arquivos existentes em profundidade limitada. Isso esclarecerá se há fixtures noutro subdiretório e se a própria pasta data/fixtures/raw existe.
- Depois, confirmar branch/commit local antes de decidir como criar o EventStore. Não executar smr watch, não criar banco vazio e não iniciar o painel sem o schema real esperado.

## 54. Inventário da pasta data — 2026-11-18

### Evidência recebida do Termux
- O usuário executou `find "$HOME/SMART-MONEY-RADAR-ETAPA16/data" -maxdepth 4 -print`.
- A saída apresentada não contém caminho nem erro.
- Não concluir ainda que data inexiste: confirmar o diretório atual, existência do caminho e status de saída com uma verificação explícita (`pwd`, `ls -ld`, `printf`/`test`).

### Estado e segurança
- Não há evidência de SQLite no caminho padrão nem de JSON em data/fixtures/raw.
- Nenhum arquivo foi criado, alterado ou removido; nenhum banco foi criado/migrado; monitoramento Helius/RPC não foi iniciado.
- PR #15 continua aberto, Draft, não merged; head dbe82cca702fc7dfe2f509a4b213b746d9ed93e9, base integration/pr13-sqlite-persistence. Consulta posterior confirmou mergeable=true. Nenhum workflow run foi retornado para o commit documental dbe82cca702fc7dfe2f509a4b213b746d9ed93e9; não declarar CI específico aprovado.
- CI 44240917136 foi aprovado para o commit anterior c6d52aceb770b30846682f6aad2afd2c8ee4be80. main permanece intacta.

### Próxima ação segura
- Confirmar caminho atual e existência da pasta data, sem alterar arquivos. Só depois inventariar a árvore correta e verificar branch/commit local.

## 55. Auditoria dos manifestos de fixtures locais e requisitos para ingestão histórica — 2026-11-18

### Evidência recebida do Termux
- O usuário inspecionou os manifestos em `data/fixtures/raw` e `data/fixtures/anonymized`.
- Foram encontrados cinco manifestos RAW. Todos informam proveniência `Solana JSON-RPC getTransaction`, `anonymized: false`, e contêm campos `signature`, `slot`, `version`, `commitment`, `encoding`, `endpoint_host`, `raw_file` e `sha256`.
- Foram encontrados cinco manifestos ANONYMIZED com schema `smr.anonymized-fixture.v1` e `anonymized: true`; incluem `projection_file`, `projection_sha256`, `mapping_file`, `provenance_manifest` e `protected_address_count`.
- Os manifestos RAW identificam a transação e proveniência, mas não declaram `wallet_address` monitorada. Portanto, não se pode inferir com segurança qual carteira deve ser associada à observação apenas pelo manifesto.
- As projeções anonimizadas não devem ser importadas como payload bruto de produção: endereços foram substituídos e os dados servem a auditoria/testes de decodificação.

### Auditoria do código remoto na branch PR #15
- A CLI `smr` possui comandos `check` e `watch`; não existe comando de importação offline.
- `process_raydium_cpmm_observation()` aceita payload RPC local, `wallet_address` e `signature`; valida que a assinatura informada aparece em `transaction.signatures` quando esse vetor está presente.
- O pipeline arquiva o payload e persiste normalização, reconciliação, tentativas e bundles CPMM.
- O pipeline atual marca a assinatura processada em transações falhadas on-chain, sem swaps CPMM e em processamento CPMM completo. Logo, não deve ser reutilizado diretamente para ingestão histórica genérica sem um modo explícito que impeça avanço de checkpoint.
- `SQLiteEventStore.save_observation(..., advance_checkpoint=False)` já permite arquivar observações sem atualizar checkpoint. `reprocess_observation()` também não altera checkpoint.
- `save_observation()` usa upsert por carteira/assinatura; portanto, uma importação deve verificar colisões e proveniência antes de substituir payload já arquivado.
- A tabela `processed_signatures` e os checkpoints são específicos à carteira. A ingestão histórica precisa manter essa semântica e não misturar carteira monitorada com fee payer/signers inferidos.

### Decisão técnica provisória
- Importador futuro deve ser offline, explícito e idempotente, com carteira monitorada fornecida/configurada de forma verificável, validação de manifesto/SHA-256/assinatura/slot e modo dry-run obrigatório antes de gravar.
- Não deve chamar RPC/Helius, não deve importar projeções anonimizadas como histórico real e não deve avançar checkpoints por padrão.
- A importação inicial precisa separar: (a) arquivamento de payload bruto; (b) processamento de swaps CPMM suportados; (c) transações de outros protocolos, que devem permanecer identificadas como não suportadas/pendentes, não ser falsamente marcadas como análise econômica concluída.
- Antes de implementar, ainda é necessário inspecionar a estrutura real de cada JSON bruto e confirmar a política de associação carteira↔transação. A existência de cinco manifestos não prova que todas as cinco transações sejam adequadas ao pipeline CPMM.

### Estado e segurança
- Nenhum banco foi criado ou migrado; nenhum JSON foi importado.
- Nenhuma chamada RPC/Helius foi realizada nesta auditoria.
- PR #14 e PR #15 permanecem Draft; nenhuma alteração na `main`.
- A inspeção dos manifestos confirmou que os arquivos RAW e ANONYMIZED estão presentes no Termux, contrariando a hipótese anterior de que `data/fixtures/raw` poderia estar vazia. A busca anterior sem resultados ocorreu em outro momento/cópia/estado e não deve ser tratada como prova de ausência atual.

### Próxima ação exata
- Inspecionar somente a estrutura dos cinco JSON RAW (sem imprimir endereços ou assinaturas), confirmar consistência com os respectivos manifestos e identificar os campos de transação disponíveis. Depois disso, definir o contrato de importação e sua cobertura por protocolo antes de qualquer criação de banco.

## 56. Auditoria remota dos fixtures versionados e estado de CI — 2026-11-18

### Estado GitHub conferido
- PR #15 permanece aberto, Draft, não merged.
- Head atual consultado: `1af769b04d48b7fdd11279ef80842794a360ec7d`; base `integration/pr13-sqlite-persistence`.
- Arquivos RAW locais do Termux não estão versionados na branch consultada: a tentativa de buscar os caminhos com nomes de assinatura em `data/fixtures/raw` retornou 404. A listagem de arquivos alterados do PR #13 confirma que os fixtures mainnet versionados estão sob `data/fixtures/mainnet/anonymized/`, não na pasta local `data/fixtures/raw/`.
- CI do head `1af769b...`: workflow `SMR tests`, run `44247868160`, concluído com sucesso. Não foram retornados status checks adicionais pelo endpoint combinado.

### Estrutura efetivamente inspecionada no GitHub
Três projeções pseudonimizadas versionadas foram lidas sem reproduzir valores de endereços ou assinaturas:
- `raydium-cpmm-jupiter-multiswap.json`: envelope JSON-RPC com `result`; transaction com `message` e `signatures`; meta inclui `innerInstructions`, `preTokenBalances`, `postTokenBalances`; 34 account keys, 11 snapshots pre e 11 post, 1 grupo de inner instructions.
- `raydium-cpmm-route-multivenue.json`: envelope JSON-RPC; message com account keys/instruções; meta inclui deltas token e inner instructions; 13 account keys, 4 snapshots pre e 4 post, 1 grupo de inner instructions.
- `raydium-cpmm-token2022-fee.json`: envelope JSON-RPC; message inclui address table lookups; meta inclui deltas token e inner instructions; 15 account keys, 4 snapshots pre e 4 post, 1 grupo de inner instructions.
- Estes arquivos são projeções pseudonimizadas para testes de decoder/reconciliador. Sua estrutura não substitui os cinco payloads RAW do Termux nem permite validar os respectivos hashes/proveniência.

### Achados da auditoria de código
- `audit_fixture()` verifica JSON, campos obrigatórios, commitment `finalized`, encoding `json`, `anonymized is False`, proteção contra path traversal no nome do bruto, SHA-256, slot e presença da assinatura em `result.transaction.signatures`.
- O auditor não recebe nem determina `wallet_address`; sua finalidade é integridade/proveniência, não atribuição de carteira.
- O coletor grava exatamente os bytes RPC e um manifesto, exige HTTPS, assinatura Base58 de 64 bytes, commitment finalized e ausência de sobrescrita.
- `normalize_transaction()` requer `wallet_address` e `signature` explícitos; filtra eventos pela carteira fornecida.
- Testes de integração das projeções usam `accountKeys[0]` como carteira de teste. Isso é uma escolha do fixture de teste e não prova que a primeira account key dos cinco payloads locais seja a carteira monitorada pelo usuário.
- O pipeline CPMM atual pode avançar checkpoint em transações falhadas on-chain ou sem swaps CPMM. Isso reforça que ele não pode ser invocado sem alteração como importador histórico genérico; além disso, outros protocolos não podem ser marcados como processados por um pipeline CPMM.
- Não há importador offline de lote implementado.

### Decisão técnica mantida
- Não importar RAW sem mapeamento explícito e verificável de carteira monitorada por transação.
- Não importar projeções anonimizadas como histórico real.
- O importador futuro deve operar em dry-run por padrão, validar par manifesto/bruto, evitar sobrescrita/upsert silencioso de observações preexistentes, separar protocolos não suportados e não avançar checkpoints durante importação histórica.
- A próxima implementação segura pode começar por um validador/inventariador offline que emite apenas metadados estruturais sem endereços, assinaturas ou URLs de RPC; a importação SQLite continua bloqueada até definição da associação de carteira e política de checkpoint.

### Segurança e execução
- Nenhum fixture RAW local foi enviado ao GitHub.
- Nenhum payload RAW foi lido remotamente porque não está versionado na branch.
- Nenhum banco criado/migrado, nenhuma importação executada, nenhuma RPC/Helius iniciada e nenhuma operação on-chain.
- Nenhuma alteração na `main`; PR #14 e #15 preservados como Draft.

## 57. PR #16 — inspetor offline e privado de estrutura das fixtures — 2026-11-18

### Branch e PR
- Branch: `feat/offline-fixture-inspector`, derivada do head do PR #15.
- PR #16: `[DRAFT] Add privacy-preserving offline fixture inspector`.
- URL: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/16
- Base: `feat/reconciliation-diagnostics`; head atual após criação inicial: `c8f9bb3d94d11541366a171d9d8edd5ea376c3ae`.
- PR #16 está Draft, aberto, não merged. Não altera `main`, PR #14 ou PR #15.

### Implementação
Novo arquivo `tools/inspect_solana_fixture_structure.py`:
- Faz inspeção offline dos pares `*.raw.json` / `*.manifest.json` com o auditor `audit_fixture()`.
- Por fixture, informa integridade do par, erros estáticos, campos do envelope/transaction/message/meta, contagens de account keys, instruções, grupos/instruções internas, snapshots pre/post, snapshots com owner, contagem de assinaturas, presença de slot, tipo de versão e estado on-chain.
- Não imprime nomes/caminhos de arquivo, endereços, assinaturas, mints, IDs de programas, blockhashes, valores de token ou URLs.
- Declara explicitamente que o manifesto não declara wallet address; não infere carteira de accountKeys/signers.
- Não acessa RPC/Helius, não inicializa SQLite, não grava arquivos e não avança checkpoints.
- Código de saída: 0 para todos os pares íntegros/estruturalmente válidos; 1 para qualquer par inválido; 2 quando não há manifestos.
- Uso local documentado no PR: `PYTHONPATH=src python tools/inspect_solana_fixture_structure.py data/fixtures/raw`.

Novo teste `tests/test_offline_fixture_structure_inspector.py`:
- Fixture sintética com valores sentinela de endereço, assinatura, mint e programa.
- Confere contagens estruturais e que nenhum valor sensível aparece na saída.
- Confere que erro de SHA-256 é reportado sem imprimir identidade do arquivo.
- Os testes ainda aguardam execução CI no head do PR #16; não declarar aprovação até resultado concluído.

### Limitações e próximo passo
- Não foi possível inspecionar os cinco RAW locais diretamente pelo GitHub porque eles não estão versionados na branch; nenhum RAW foi enviado ao repositório.
- A ferramenta é código pronto para executar localmente, mas ainda não foi executada no Termux.
- Nenhuma importação SQLite, associação de carteira, migração, criação de DB, RPC/Helius ou operação on-chain foi realizada.
- Após CI aprovado, a próxima ação operacional será o usuário executar o inspetor no Termux para obter contagens/estrutura sem revelar identificadores. Só então será definida a política de associação carteira↔transação e a ingestão histórica segura.

## 58. Revisão de segurança do inspetor e correção de vazamento potencial — 2026-11-18

### CI do primeiro corte
- Run `44248192946` (`SMR tests`, run number 352) concluído com `success`.
- Instalação do projeto, testes unitários e compileall concluídos com sucesso para o head anterior `1f614457022bd75d259c78c98076b039c35cfc12`.

### Revisão adicional após CI
A leitura direta do código identificou uma possibilidade de exposição: exceções de sistema operacional poderiam incluir o caminho do manifesto, e nomes de campos arbitrários em JSON poderiam ser reproduzidos no relatório. Embora os testes iniciais tenham passado, isso não atendia integralmente à promessa de saída sem identificadores.

Correções aplicadas na branch:
- Exceções `OSError` agora viram mensagem genérica `manifesto inacessível`, sem ecoar caminho.
- Listas de campos no relatório são filtradas por allowlists fixas de nomes RPC conhecidos; chaves arbitrárias do payload não são reproduzidas.
- Novo teste garante que caminho sintético contendo texto de carteira/assinatura não aparece no relatório quando o manifesto não pode ser aberto.

### Commits e estado
- Correção do inspetor: `6e6da41e78452aad5e00ccc85b7545c63ef560cb`.
- Teste de redação de caminho: `366f38cbc68c196750a4341124fc3810c8f26c1a`.
- Commits de correção e teste: `6e6da41e78452aad5e00ccc85b7545c63ef560cb` e `366f38cbc68c196750a4341124fc3810c8f26c1a`.
- Head funcional seguido da atualização documental: `92aeae7b392ee4329932f5e9d442b42164c2e953`.
- CI para esse head: run `44248529109`, em andamento no momento do registro; o sucesso do run anterior não valida as correções.
- PR #16 permanece Draft, aberto, não merged.
- Nenhum dado RAW foi enviado; nenhuma execução local, RPC, banco, migração, checkpoint ou operação on-chain ocorreu.

## 59. Correção de teste de redação e CI — 2026-11-18

- CI do head `92aeae7b392ee4329932f5e9d442b42164c2e953`: run `44248529109` falhou em um único teste novo; 247 outros testes passaram (total 248).
- Falha não era no redator: o JSON de teste escapava o caractere acentuado como `\\u00ed`, enquanto a asserção procurava o texto Unicode literal.
- Corrigido o teste para serializar com `ensure_ascii=False`, preservando a verificação de que caminho sensível não é exibido.
- Commit corretivo: `5e02581090366a46fca6c5fe49cccaaed2099ee7`.
- Aguardando CI para o novo head. Nenhuma alteração funcional adicional, nenhum dado local enviado, nenhuma execução de DB/RPC/on-chain.

## 60. CI aprovado e precisão da detecção de associação de carteira — 2026-11-18

### CI do inspetor
- Run `44248632411` (`SMR tests`, run number 360), head `bc07ca08de21999fc116b064ad87b17c7a773c74`: concluído com sucesso.
- Instalação, 248 testes unitários e compileall aprovados.
- A falha anterior do run `44248529109` foi exclusivamente a asserção Unicode, corrigida no commit `5e02581090366a46fca6c5fe49cccaaed2099ee7`.

### Ajuste adicional após revisão
- Revisão identificou que o campo `manifest_declares_wallet_address` estava fixado em `False`, independentemente do manifesto.
- Corrigido para verificar a presença explícita de `wallet_address` ou `monitored_wallet_address`, sem expor os respectivos valores.
- Teste adicional verifica detecção e ausência de vazamento.
- Commits: `25af1268f6bd7bb99bf135199ed08b25121b58eb` e `54acb2cf8ca13eda45055d7c6757d26c310b43a0`.
- CI da alteração adicional: run `44248785379` (run number 363), concluído com sucesso no commit de teste `54acb2cf8ca13eda45055d7c6757d26c310b43a0`; 249 testes unitários OK e compileall aprovado.
- PR #16 permanece Draft, aberto e não merged; `main` intacta.

### Próxima ação
CI da alteração adicional aprovado. O PR #16 permanece Draft. Próxima ação operacional: executar o inspetor local nos cinco pares RAW do Termux, apenas leitura e sem enviar dados ao GitHub. A presença do campo é apenas uma declaração no manifesto, não prova a legitimidade da associação carteira↔transação.

## 61. Inspeção local concluída e contrato preliminar de importação histórica — 2026-11-18

### Evidência local recebida
- O usuário executou `tools/inspect_solana_fixture_structure.py` no clone PR16, apontando para os RAW preservados na cópia original do Termux.
- Resultado: 5 manifestos encontrados, 5 íntegros/estruturalmente válidos, 0 inválidos.
- Todos os cinco payloads reportaram `on_chain_status=success`, slot presente e snapshots pre/post token balances; os snapshots contabilizados tinham campo `owner`.
- Variação estrutural observada: 10–17 account keys, 4–10 instruções principais, 1–3 grupos CPI e 2–14 instruções internas; três payloads têm address table lookups; versão RPC aparece como inteiro ou texto.
- Nenhum manifesto declara `wallet_address` ou `monitored_wallet_address`.
- O inspetor confirmou `network_access=false`, `database_access=false` e `writes_files=false`.

### CI e estado do PR #16
- Commit documental `01a410833650c022909f97c475b468631130b47e`: workflow `SMR tests`, run `44249289181` (run 366), concluído com sucesso.
- PR #16 permanece aberto, Draft, não merged, mergeable; head consultado `01a410833650c022909f97c475b468631130b47e`, base `feat/reconciliation-diagnostics`.
- Nenhuma alteração em `main`; PR #14 e #15 preservados.

### Especificação preliminar adicionada
- Novo documento `docs/IMPORTACAO-HISTORICA-SOLANA-ESPECIFICACAO.md`, commit `1e00c36a2c3b835f37ffbef34aaca962ccac096a`.
- Define fases de descoberta, validação, atribuição explícita, cobertura de protocolo e dry-run sem efeitos colaterais.
- Exige mapeamento externo explícito carteira↔transação; não inferir por fee payer, signatário, accountKeys ou owner de token account.
- Define estados para carteira ausente, falhas de integridade, protocolo não suportado, duplicata idêntica e colisão de identidade.
- Bloqueia no dry-run qualquer inicialização de `SQLiteEventStore`, pois o construtor pode criar/migrar schema.
- Bloqueia uso direto do pipeline CPMM atual como importador genérico, pois seu fluxo pode marcar como processadas transações sem swaps CPMM e avançar checkpoint.
- Importação persistente, criação/migração de banco e checkpoint continuam exigindo autorização explícita.

### Próxima etapa segura
- Implementar apenas o planejador/dry-run offline, sem SQLite e sem gravações, com relatório redigido.
- A ausência de associação explícita deve produzir `WALLET_UNASSIGNED`; não presumir que os cinco RAW pertencem a uma única carteira.
- Antes de persistir qualquer coisa, revisar o mapeamento carteira↔transação e obter autorização específica.

## 62. Planejador offline de importação histórica — primeira implementação — 2026-11-18

### Código adicionado
- `tools/plan_solana_historical_import.py`: planejador offline, somente leitura, sem EventStore.
- `tests/test_historical_import_planner.py`: testes de carteira ausente, associação explícita, hash divergente, transação on-chain falha, manifesto via symlink e mapeamento inválido.
- Documento atualizado: `docs/IMPORTACAO-HISTORICA-SOLANA-ESPECIFICACAO.md`, seção 9.

### Contrato funcional implementado
- Descoberta determinística de manifestos no diretório fornecido.
- Reutiliza `audit_fixture()` para integridade/proveniência (hash, assinatura, slot, finalized, encoding e `anonymized=false`).
- Rejeita manifestos/payloads via symlink e caminhos resolvidos fora do diretório autorizado.
- Mapeamento explícito local opcional `{signature: monitored_wallet}`; nenhum valor é exibido.
- Sem associação: `WALLET_UNASSIGNED`.
- Divergência entre mapa e declaração explícita no manifesto: `WALLET_MAPPING_CONFLICT`.
- `meta.err` não nulo: `ON_CHAIN_FAILED`.
- Associação explícita: `READY_FOR_REVIEW`, não significa autorização de gravação.
- Saída só contém índice e estado; sem caminhos, endereços ou assinaturas.
- Reporta `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false`, `execution_authorized=false`.

### Limites e segurança
- Não classifica automaticamente protocolo/venue; cobertura DEX precisa de revisão posterior.
- Não compara duplicatas com SQLite porque não abre banco.
- Não cria arquivos, banco, migração, checkpoint, RPC/Helius ou operações on-chain.
- O mapa privado não deve ser enviado ao GitHub.
- Nenhum dos cinco RAW locais foi enviado ao repositório.
- Os arquivos criados no GitHub estão na branch `feat/offline-fixture-inspector`; PR #16 continua Draft, não merged; `main` e PRs #14/#15 preservados.

### Validação
- Testes adicionados ao repositório, aguardando CI do head atualizado. Não declarar aprovação até workflow concluído.
- A execução local dos cinco RAW com o novo planejador ainda não ocorreu; não pedir para rodar até CI passar.

### Próxima ação
- Acompanhar CI; corrigir falhas se existirem.
- Após CI aprovado, orientar execução local no clone PR16 apontando para os RAW originais, sem fornecer/compartilhar mapeamento de carteira.
- Analisar o relatório redigido. Associação e cobertura de protocolo permanecem decisões humanas; nenhuma persistência está autorizada.

## 63. CI aprovado do planejador offline — 2026-11-18

- Head validado: `0c493b51fc98f5453f5b3763b0aeee48631464a6`.
- Workflow `SMR tests`, run `44249986290` (run 372): concluído com sucesso.
- Job `test`: instalação concluída; **255 testes passaram** (`Ran 255 tests ... OK`); `python -m compileall -q src tests` concluído com sucesso.
- A suíte inclui os seis testes novos do planejador: carteira ausente, associação explícita, hash divergente, falha on-chain, manifesto symlink e mapa inválido.
- PR #16 continua Draft, aberto, não merged, mergeable; `main` intacta.
- Próxima ação: executar o planejador no clone PR16 contra os RAW originais, sem mapa de carteiras inicialmente. Isso deve retornar `WALLET_UNASSIGNED` para os cinco casos e confirmar o relatório local sem expor identificadores.
- Não criar/abrir SQLite, não enviar RAW nem mapa ao GitHub, não importar, não migrar, não avançar checkpoint, não iniciar RPC/Helius ou execução on-chain.

## 64. Dry-run local confirmado e teste de imutabilidade reforçado — 2026-11-18

### Execução local do usuário
- Clone PR16 avançado por `git fetch` + `git merge --ff-only` até `d54d2be655a4d6f662f5b1906cc8d8e99ae0a636`; working tree estava limpo e branch correta antes da atualização.
- Execução de `tools/plan_solana_historical_import.py` sobre os RAW originais: 5 manifestos, 5 `WALLET_UNASSIGNED`, sem outros estados.
- Relatório confirmou `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false`, `execution_authorized=false`.
- Portanto, a ferramenta confirmou que os arquivos são candidatos estruturalmente íntegros, mas nenhuma transação está atribuída a uma carteira monitorada. Nenhum dado foi importado.

### Teste adicional
- Adicionado teste `test_dry_run_is_redacted_and_does_not_modify_inputs` em `tests/test_historical_import_planner.py`, commit `266577837cb30d7d613ae0222a50cbd0eabc499f`.
- Teste compara hashes dos arquivos antes/depois e verifica que assinatura, carteira e caminho não aparecem no relatório, além das flags de ausência de rede/banco/gravação/checkpoint.
- CI desse novo commit ainda precisa concluir.

### Próxima etapa
- Aprofundar a análise de cobertura de protocolo dos cinco payloads sem imprimir program IDs ou outros identificadores.
- Não inferir carteira por owner, fee payer, signatário ou posição em accountKeys.
- Persistência, criação/migração SQLite, RPC/Helius e operações on-chain continuam não autorizadas.

## 65. Auditoria offline de cobertura de protocolos — implementação iniciada 2026-11-18

- CI do teste de imutabilidade do planejador (run `44250215068`, #376) concluiu com sucesso. Os passos de testes unitários e compileall passaram.
- Revisão da matriz `domain/program_registry.py` confirma que registro de Program IDs significa identificação conhecida, não implementação de decoder.
- Nesta branch, a cobertura de decoder diretamente comprovada pelo código é estreita: Raydium CPMM para instruções swap base input/output; SPL Token e Token-2022 para Transfer/TransferChecked. Não há base para declarar suportados Raydium AMM v4, Jupiter, Meteora DLMM ou DAMM v2 apenas por estarem no registro/catálogo.
- Criado `tools/audit_solana_protocol_coverage.py` e `tests/test_protocol_coverage_audit.py`. O auditor revalida fixtures, resolve program IDs de instruções externas/CPI incluindo ALT, agrega somente nomes conhecidos e contagens, nunca imprime IDs/endereço/assinatura/caminhos, rejeita symlinks antes da leitura do payload e não acessa rede/SQLite nem grava.
- O teste cobre resolução por índice, CPI, programa registrado com escopo estreito, programa desconhecido, redação e symlink.
- Commits: auditor `d7f32ecd3648ebbdbe78a84a8cb6715e15542d16`; testes iniciais `3248d5466fb12845d0ca34943af8fce08bac6af0`; hardening contra symlink `8276e610ecb39fe7d60a2327407d2bc6a799183e`; expectativa de teste corrigida `04ae970ec73f82aaf9166ac3cbfd9e53c94ccb52`.
- CI do novo auditor: run `44250502846` (#381), concluído com sucesso; **259 testes unitários OK** e compileall aprovado. O CI cobre o commit funcional `04ae970ec73f82aaf9166ac3cbfd9e53c94ccb52`; o head atual posterior é documental.
- Próximo passo: executar auditor localmente contra os cinco RAW originais e avaliar o relatório redigido antes de qualquer importação. Não associar carteiras por heurística, não criar DB, não usar RPC/Helius e não avançar checkpoints.

## 66. Auditoria local de cobertura dos cinco RAW — 2026-11-18

### Execução confirmada pelo usuário
- Clone PR16 atualizado por fast-forward de `d54d2be` para `84e6e96`; branch correta e working tree limpo antes do fetch/merge.
- `tools/audit_solana_protocol_coverage.py` executado contra o diretório RAW original.
- Resultado: 5 manifestos, 5 auditados, 0 inválidos; 60 instruções externas + CPI contabilizadas; 0 programas não resolvidos.
- Totais por programa registrado: SPL Token 22; System Program 9; Associated Token Account 4; Meteora DAMM v2 4; Jupiter Aggregator v6 2; Meteora DLMM 2; Token-2022 1; Raydium AMM v4 1; Raydium CPMM 1. Total registrado: 46 instruções.
- 14 instruções pertencem a programas fora do registro atual; isso não permite concluir que sejam venues desconhecidas ou swaps.
- Ocorrências por fixture (somente índices sintéticos do relatório):
  1. DAMM v2, ATA, SPL, System e Token-2022; 3 instruções não registradas.
  2. Raydium AMM v4 e SPL; 2 não registradas.
  3. Jupiter v6 e Meteora DAMM v2, ATA, SPL e System; 2 não registradas.
  4. Meteora DLMM e SPL; 3 não registradas.
  5. Raydium CPMM, SPL e System; 4 não registradas.
- Escopo de decoder contabilizado: SPL Token 22, Token-2022 1 e Raydium CPMM 1. Os demais protocolos identificados ainda não têm decoder de venue comprovado nesta branch.
- O número de instruções não equivale ao número de swaps econômicos: CPI, roteamento e múltiplas transferências podem fazer parte de uma mesma operação. Não converter contagens diretamente em BUY/SELL ou eventos.
- O relatório confirmou `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false`.
- Nenhum RAW foi enviado ao GitHub; nenhum banco foi criado/importado; nenhuma carteira foi inferida.

### Lacunas e sequência técnica recomendada
1. Meteora DAMM v2: aparece em dois payloads, incluindo uma rota com Jupiter; decoder precisa separar instrução de venue e transferências CPI.
2. Raydium AMM v4: aparece em um payload; requer decoder específico, sem reutilizar layout CPMM.
3. Meteora DLMM: aparece em um payload; tratar múltiplos bins/transferências e reconciliação econômica.
4. Jupiter v6: modelar como agregador/roteador, não venue; identificar venue efetiva por CPI e evitar dupla contagem.
5. Investigar os 14 programas fora do registro apenas por nome/categoria allowlisted, sem expor IDs; não presumir que todos sejam relevantes para swap.

Cada decoder deve começar com contrato estrutural e fixtures de teste; depois reconciliar transferências/deltas e somente então produzir `SwapObservation`. Até isso ocorrer, casos sem cobertura permanecem não resolvidos/incompletos, nunca classificados por heurística.

### Próximo passo
Revisar instruções/contas e evidências de CPI do payload de DAMM v2 de forma redigida, definir o contrato do decoder e testes antes de implementar. Não iniciar importação, persistência, criação/migração SQLite, RPC/Helius, checkpoint ou execução on-chain.

## 67. Fingerprints redigidos de instruções de venue — implementação em validação

- Evoluído tools/audit_solana_protocol_coverage.py para emitir venue_instruction_profiles apenas para venues registradas e Jupiter como agregador.
- Cada perfil contém somente nome do programa, origem top-level/inner, prefixo de até 8 bytes da instrução em hexadecimal, comprimento total dos dados, quantidade de contas, stack height e contagem agrupada.
- Não imprime os bytes restantes (onde podem estar valores/quantidades), índices/endereços de contas, Program IDs, carteiras, assinaturas ou paths.
- Decodifica Base58 localmente para extrair fingerprint; sem RPC, banco ou gravações.
- Teste sintético verifica fingerprint, tamanho, contagem de contas, localização e ausência de identificadores.
- Commits: auditor c75a16234d08f1bae2061c784da6a474789994bd; teste 1ebc04eb625028d67a53e17b4bfac4e8d9efb613; correção de bytes zero/Base58 no auditor 6ac99dbb32fa35771b3c3113fbc1c42c50f6a56d; correção equivalente no teste ab6a09522d4347f53e474082188cd926e90872a3.
- CI run 44251053718 (#393), commit funcional `ab6a09522d4347f53e474082188cd926e90872a3`: concluído com sucesso, 259 testes unitários OK e compileall aprovado.
- Próximo passo: após CI, atualizar clone PR16 e executar novamente o auditor nos cinco RAW. Os fingerprints vão permitir especificar decoders DAMM v2, AMM v4, DLMM e roteamento Jupiter sem expor payload sensível.

## 68. Fingerprints locais e validação documental inicial do Meteora DAMM v2 — 2026-11-18

### Execução local confirmada pelo usuário
- Clone PR16 avançado por fast-forward de `84e6e96` para `65c03c8c423302a89c09ea6a4de29b78396c3c1d`; branch `feat/offline-fixture-inspector` e working tree limpo antes do fetch/merge.
- Auditoria executada novamente sobre os cinco RAW locais: `manifest_count=5`, `audited_count=5`, `AUDITED=5`, zero instruções com programa não resolvido.
- Flags confirmadas: `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false`.
- Perfis DAMM v2 observados:
  - top-level: prefixo `f8c69e91e17587c8`, 24 bytes de dados, 14 contas, stack height 1, uma ocorrência no payload de índice 1;
  - inner: prefixo `e445a52e51cb9a1d`, 196 bytes, 1 conta, stack height 2 no payload de índice 1;
  - no payload de índice 3, o perfil inner de 196 bytes reaparece com stack height 3 e também há perfil top-level com prefixo `f8c69e91e17587c8`, 24 bytes, 14 contas, stack height 2.
- O prefixo top-level `f8c69e91e17587c8` coincide com os primeiros oito bytes de SHA-256 de `global:swap`, o discriminador Anchor da instrução `swap`. A documentação oficial Meteora identifica `swap` como caminho legacy exact-in e `swap2` como caminho atual com ExactIn, PartialFill e ExactOut. Portanto, os dois perfis top-level são evidência consistente de chamada `swap` legacy; não há perfil top-level `swap2` nos cinco RAW.
- Correção de interpretação: `e445a52e51cb9a1d` é o marcador genérico de instrução Event CPI do Anchor (`EVENT_IX_TAG_LE`), não o discriminador do evento. No código oficial Meteora, `p_emit_cpi()` concatena esse marcador com os bytes de `Event::data(&EvtSwap2 { ... })`; portanto, os oito bytes seguintes devem conter o discriminador do evento (`bd4233a826507599` para `EvtSwap2`). O perfil de 196 bytes é exatamente compatível com 8 bytes do wrapper + 8 bytes do discriminador + 180 bytes do payload serializado. A evidência estrutural indica fortemente Event CPI EvtSwap2, mas a confirmação nos bytes RAW locais ainda precisa ser feita lendo o discriminador no offset 8.
- O marcador `e445...` também aparece em perfis sob outros programas porque é o wrapper genérico de Event CPI do Anchor. O discriminador do evento fica nos bytes 8–15 e deve ser interpretado em conjunto com o programa que executa o CPI, tamanho e contexto de instrução.

### Fontes oficiais consultadas
- Meteora DAMM v2 Instructions: `swap` (legacy exact-in) e `swap2` (modos exact-in/partial-fill/exact-out).
- Meteora DAMM v2 Events: eventos Anchor são emitidos por event CPI; `EvtSwap2` é associado a `swap` e `swap2` e é o evento canônico para analytics.
- A validação documental não substitui a conferência da versão exata do IDL/programa que produziu as transações históricas.

### Decisão e próximo passo
- Não implementar ainda um decoder completo. Primeiro obter a versão oficial do IDL/commit correspondente ao programa mainnet e identificar a instrução inner `e445...` sem heurística.
- Próximo contrato DAMM v2 deve distinguir: instrução top-level `swap`; eventual instrução `swap2`; evento CPI confirmado; outras instruções/eventos; transferências SPL/Token-2022 associadas; e reconciliação econômica por operação.
- A saída econômica deverá usar os deltas e transferências reais reconciliados, não apenas `amount_0/amount_1` ou o evento, considerando transfer fees e taxas descritas pelo protocolo.
- Não inferir BUY/SELL sem mint de referência explícito; não contar eventos/transferências como swaps adicionais; manter desconhecidos como UNKNOWN/INCOMPLETE.
- Nenhum RAW foi enviado ao GitHub. Nenhum decoder DAMM v2 foi implementado, nenhum SQLite foi criado/aberto, e nenhuma importação, RPC/Helius, checkpoint ou operação on-chain foi executada.

## 69. Identificação estrutural de Event CPI DAMM v2 e extensão do auditor — 2026-11-18

### Fonte oficial fixada
- Repositório oficial: MeteoraAg/damm-v2, commit consultado 18936b18c26708f6e9b52cacc01ea2f99868ba8e.
- Arquivos de referência: programs/cp-amm/src/instructions/swap/ix_p_swap.rs, programs/cp-amm/src/event.rs, programs/cp-amm/src/instructions/swap/ix_swap.rs, programs/cp-amm/src/state/pool.rs e programs/cp-amm/src/entrypoint.rs.
- p_handle_swap() processa ExactIn, PartialFill e ExactOut, realiza transferências e chama p_emit_cpi(Event::data(&EvtSwap2 { ... }), event_authority).
- p_emit_cpi() concatena EVENT_IX_TAG_LE antes dos bytes retornados por Event::data e emite CPI ao próprio programa usando a autoridade de evento.
- SwapParameters2: amount_0: u64, amount_1: u64, swap_mode: u8. Enum: 0 ExactIn, 1 PartialFill, 2 ExactOut.
- EvtSwap2 contém pool, direção, modo de cobrança, referral, parâmetros, resultado, transfer fees, timestamp e reservas. SwapResult2 inclui input/output, amount_left, preço, claiming/protocol/compounding/referral fees.
- O tamanho serializado do evento é 188 bytes: discriminador Anchor de 8 bytes + payload de 180 bytes. Com o wrapper Event CPI de 8 bytes, a instrução interna mede 196 bytes.
- A emissão do evento usa uma conta de autoridade no CPI, consistente com o perfil observado de uma conta.
- O discriminador Anchor de EvtSwap2 é bd4233a826507599; o marcador Event CPI observado é e445a52e51cb9a1d. Logo, o marcador observado é wrapper genérico, não discriminador de evento. A confirmação nos RAW exige comparar bytes 8–15 com bd4233a826507599.

### Alteração funcional em PR #16
- Auditor agora separa event_cpi_profiles dos perfis comuns de instrução.
- Para instruções internas de programas registrados como venue/agregador, quando os dados começam pelo wrapper Event CPI e têm pelo menos 16 bytes, registra somente nome do programa, discriminador de evento (8 bytes), comprimento total, quantidade de contas, stack height e contagem.
- Identifica como EvtSwap2 somente quando o programa é Meteora DAMM v2 e o discriminador no offset 8 corresponde exatamente a bd4233a826507599; os demais ficam UNKNOWN.
- Não expõe payload do evento, pool, mints, valores, carteiras, Program IDs, assinaturas ou caminhos. Continua offline/read-only, sem SQLite, rede, gravação ou checkpoint.
- Teste sintético cobre wrapper + discriminador + 180 bytes de payload, total 196 bytes, uma conta e stack height 2, além de redação.
- Commits funcionais: auditor 6add87df5f7f9f113f0a809c6ea563bdfdf3af00; teste inicial 41dd2c84dbe8666e4f4293a8f20e8f1066070fdb; fixture sintética corrigida 0af12f16f06aa80d0af7c5e6727d3ff1584f49e2.
- CI/status do novo head ainda não apresentou execução nem checks na consulta; não declarar testes aprovados.

### Próxima validação
- Atualizar o clone PR16 e executar o auditor nos cinco RAW locais. Confirmar se os eventos DAMM v2 reportam event_discriminator_hex=bd4233a826507599, event_name=EvtSwap2, tamanho 196 e uma conta.
- Se a confirmação ocorrer, registrar EvtSwap2 como evento CPI confirmado, mas não contar evento e instrução top-level como dois swaps. Ainda será necessário reconciliar transferências e deltas por operação antes de criar SwapObservation.
- Nenhum RAW foi enviado ao GitHub; nenhuma importação, SQLite, RPC/Helius, checkpoint ou operação on-chain foi executada.

## 70. CI da identificação Event CPI DAMM v2 — 2026-11-18

- O head atual do PR #16 é `dea3f6428c7c7e85254fa8fb23645e6ed9df3b4e` (commit documental que atualiza a especificação DAMM v2 Event CPI).
- GitHub Actions workflow `SMR tests`, run `44251933124` (#402), concluiu com `success` para esse head.
- A execução CI inclui o teste sintético `test_recognizes_damm_v2_evt_swap2_inside_anchor_event_cpi`, que valida wrapper Anchor + discriminador `bd4233a826507599`, payload de 180 bytes (196 bytes totais), uma conta e stack height 2; também verifica que Program ID e efeitos colaterais não aparecem no relatório.
- O CI valida o comportamento com fixture sintética. **Não confirma** que os bytes 8–15 dos dois Event CPI DAMM v2 presentes nos cinco RAW locais sejam `bd4233a826507599`.
- A validação local pendente continua sendo executar o teste específico e o auditor atualizado nos cinco RAW, no clone Termux `$HOME/SMART-MONEY-RADAR-PR16`. Esperado, se a hipótese estiver correta: dois perfis DAMM v2 `EvtSwap2`, comprimento 196, uma conta, stack heights 2 e 3.
- A documentação oficial atual da Meteora confirma que `EvtSwap2` é emitido por `swap` e `swap2`, e que ExactOut inverte a interpretação dos campos amount_0/amount_1 em relação a ExactIn/PartialFill. Isso reforça a exigência de decodificar o modo antes de interpretar quantidades.
- PR #16 permanece Draft, aberto, não merged; `main` não foi alterada.
- Nenhum RAW foi enviado ao GitHub; nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

### Próxima ação
Aguardar a saída local do comando já fornecido para fast-forward + teste específico + auditoria dos cinco RAW. Não repetir nem presumir sucesso local. Se o discriminador for confirmado, registrar o resultado observado e então definir o contrato de decoder DAMM v2 com reconciliação SPL/Token-2022 e deltas de token accounts/vaults.

## 71. Confirmação local de EvtSwap2 nos cinco RAW — 2026-11-18

### Execução Termux confirmada pelo usuário
- Clone `$HOME/SMART-MONEY-RADAR-PR16` fast-forward de `65c03c8` para `59fd946`; branch `feat/offline-fixture-inspector`, verificações de branch e working tree limpo passaram antes do fetch.
- Suíte específica `test_protocol_coverage_audit.py`: 4 testes executados, todos `OK`.
- Auditor local nos RAW: `manifest_count=5`, `audited_count=5`, status `AUDITED=5`; nenhuma instrução com programa não resolvido.
- Fixture de índice 1: programa Meteora DAMM v2, discriminador `bd4233a826507599`, evento `EvtSwap2`, comprimento 196, uma conta, stack height 2, count 1.
- Fixture de índice 3: mesmo discriminador/evento/comprimento/conta, stack height 3, count 1.
- Total: **dois Event CPI EvtSwap2 DAMM v2 confirmados nos RAW locais**. A fixture 3 também contém a instrução DAMM v2 interna de 24 bytes no stack height 2; o evento no stack height 3 é evidência separada associada ao contexto de execução, não um segundo swap econômico.
- Os perfis Event CPI Jupiter v6 e Meteora DLMM permaneceram `UNKNOWN`; não foram classificados por semelhança do wrapper.
- Flags finais: `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false`.
- Nenhum payload, assinatura, endereço, mint, valor ou RAW foi enviado ao GitHub/chat.

### Conclusão técnica
- A hipótese de discriminador deixou de ser apenas estrutural: os bytes 8–15 dos dois payloads DAMM v2 inner correspondem ao discriminador oficial de EvtSwap2.
- O evento é agora identificado nos dados reais, mas isso **não** equivale a um decoder completo de parâmetros/resultados nem à criação de `SwapObservation`.
- Não contar a instrução `swap`, o Event CPI e as transferências SPL como operações distintas. Associar evidências pelo contexto da instrução top-level, grupo de inner instructions, stack height e ordem CPI.
- Interpretar `SwapParameters2` conforme `swap_mode`: 0 ExactIn, 1 PartialFill, 2 ExactOut. Para ExactOut, `amount_0` é output desejado e `amount_1` input máximo. Não assumir quantidades efetivamente transferidas a partir dos parâmetros.
- Para gerar uma observação econômica, ainda é obrigatório decodificar transferências e reconciliar deltas por token account/vault, incluindo Token-2022 transfer fees e taxas do protocolo.

### Próxima etapa de engenharia
Definir decoder DAMM v2 em camadas: (1) discriminadores e parser estrito de instruções `swap`/`swap2`; (2) parser estrito de Event CPI `EvtSwap2` com validação de comprimento/enum; (3) vínculo evento↔instrução sem dupla contagem; (4) reconciliação econômica com transfers e token-account deltas; (5) testes sintéticos positivos/negativos para ExactIn, PartialFill, ExactOut, truncamento, eventos desconhecidos, múltiplos swaps e Token-2022 fees. Manter separado do pipeline CPMM; não expandir o pipeline CPMM por inferência.

- PR #16 permanece Draft, aberto e não merged; `main` intacta.
- Nenhum SQLite, importação histórica, RPC/Helius, checkpoint, trade ou operação on-chain foi executado.

## 72. Primeiro decoder estrutural DAMM v2 — implementação aguardando validação

### Código adicionado ao PR #16
- Novo módulo `src/smart_money_radar/data_sources/damm_v2_decoder.py`.
- Novo conjunto `tests/test_damm_v2_decoder.py`.
- Fonte oficial fixada: `MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e`.
- Commits funcionais: decoder `9bd940d86209bfe89a03dd66e5bfa23593ae3ba9`; testes `8562da8c2d8d87228b706aff2012fa36b2d16ef0`.

### Escopo do parser
- Reconhece somente o Program ID DAMM v2 e discriminadores Anchor exatos para `swap` legacy (`f8c69e91e17587c8`) e `swap2` (`414b3f4ceb5b5b88`).
- `swap` decodifica `amount_in` e `minimum_amount_out`, fixando modo `EXACT_IN`.
- `swap2` decodifica `amount_0`, `amount_1` e modo 0/1/2; em `EXACT_OUT`, preserva sem inverter os campos: amount_0 = output desejado, amount_1 = input máximo.
- Reconhece Event CPI com wrapper Anchor + discriminador `EvtSwap2` e comprimento exato 196 bytes.
- Decodifica pool (bytes), direção A→B/B→A, collect-fee mode, referral bool, parâmetros, SwapResult2 (incluindo u128 next_sqrt_price), transfer fees, timestamp e reservas.
- Valida tamanhos exatos, modos/direções/enum, booleano Borsh e amount_0 positivo; eventos/descriminadores desconhecidos não são forçados para EvtSwap2.
- Não interpreta dados como BUY/SELL, não gera `SwapObservation`, não liga evento a instrução e não reconcilia transfers/deltas. É parser estrutural isolado, não pipeline operacional.

### Testes adicionados (ainda aguardando execução)
- Swap legacy ExactIn.
- swap2 ExactOut com semântica amount_0/amount_1 preservada.
- Modos inválidos e tamanhos de instrução inválidos.
- EvtSwap2 com campos de evento/resultados, fees e reservas.
- Evento desconhecido/programa incorreto.
- Payload truncado, direção inválida e booleano inválido.
- O head atual do PR #16 é `8562da8c2d8d87228b706aff2012fa36b2d16ef0`; na consulta inicial ainda não havia workflow run nem status checks para esse head. Não declarar CI aprovado até consulta posterior.

### Próxima validação
Fast-forward do clone PR16, executar `test_damm_v2_decoder.py` e a suíte completa. Corrigir qualquer falha antes de ampliar o auditor ou criar adaptador de reconciliação. Nenhuma alteração ao pipeline CPMM existente.

- PR #16 segue Draft, aberto, não merged; `main` intacta.
- Nenhum RAW enviado; nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain executada.

## 73. Validação CI e conferência do parser DAMM v2 com fonte oficial (18/11/2026)

- CI do commit funcional `45ca36761dbefacbe30fb3f6cd694b6f32e4ed23`: workflow `SMR tests`, run `44252571670` (#408), concluído com sucesso. O resultado CI cobre os testes adicionados e a suíte configurada no workflow, incluindo compileall.
- Conferência do parser contra o código oficial MeteoraAg/damm-v2 fixado em `18936b18c26708f6e9b52cacc01ea2f99868ba8e`:
  - `swap`: Anchor discriminator `f8c69e91e17587c8`; payload de 24 bytes; parâmetros legacy `amount_in` e `minimum_amount_out`, equivalentes a ExactIn.
  - `swap2`: discriminator Anchor `414b3f4ceb5b5b88` (SHA-256 de `global:swap2`); payload de 25 bytes; `amount_0`, `amount_1`, `swap_mode`.
  - `EvtSwap2`: discriminator `bd4233a826507599`, precedido pelo wrapper Event CPI `e445a52e51cb9a1d`; payload completo de 196 bytes.
  - Ordem serializada conferida com `event.rs`, `SwapParameters2` e `SwapResult2`: pool, direção, modo de coleta, referral, parâmetros, resultado, transfer fees, timestamp e reservas.
  - Valores enum conferidos: direção AtoB/BtoA = 0/1; CollectFeeMode BothToken/OnlyB/Compounding = 0/1/2; SwapMode ExactIn/PartialFill/ExactOut = 0/1/2.
- O parser mantém a fronteira estrutural: não associa evento a instrução, não interpreta contas/mints, não produz SwapObservation e não reconcilia transferências SPL/Token-2022 ou deltas de vaults. O evento não deve ser contado como swap adicional.
- **Validação local Termux ainda pendente**: o usuário ainda precisa fast-forwardar o clone PR16 e executar o teste específico, a suíte completa e compileall. CI aprovado não substitui essa verificação local.
- PR #16 permanece Draft, aberto e não mergeado; main intacta. Nenhum RAW foi enviado ao GitHub; nenhuma importação, SQLite, RPC/Helius, checkpoint ou operação on-chain foi executada.

## 74. Validação local do parser e associação estrutural DAMM v2 ↔ EvtSwap2 (18/11/2026)

### Validação local do parser
- O usuário atualizou o clone PR16 por fast-forward até `2396f61e01d23a4523449af7c19dced71ed1cd13`.
- Testes específicos `test_damm_v2_decoder.py`: **6/6 aprovados**.
- Suíte completa naquele head: **266 testes aprovados**; `compileall -q src tests` terminou sem erro.
- Avisos `ResourceWarning` em testes HTTP não causaram falha. A validação local não executou RPC, banco, importação ou operação on-chain.

### Associação implementada
- Novo módulo `src/smart_money_radar/data_sources/damm_v2_analyzer.py`; testes `tests/test_damm_v2_analyzer.py`.
- Analisa instruções DAMM v2 `swap`/`swap2` e eventos `EvtSwap2` no mesmo payload RPC.
- Associa somente quando: mesmo índice de instrução externa; evento posterior à instrução swap; `stackHeight` do evento exatamente um nível acima; caminho CPI do evento tem como pai exato o caminho da instrução swap.
- Resolve `programIdIndex` incluindo `meta.loadedAddresses` em transações versionadas.
- Se stackHeight estiver ausente/inválido, invalida a hierarquia restante daquele grupo e não inventa associação.
- Preserva operações distintas em rotas com múltiplos swaps. Um evento não é contado como swap adicional.
- Estados emitidos: `MATCHED`, `EVENT_MISSING`, `AMBIGUOUS` e `UNMATCHED_EVENT`. Ambiguidades e eventos sem vínculo não são forçados para uma operação.
- A saída mantém instrução e evento como evidências separadas. Não reconcilia transferências SPL/Token-2022 ou deltas de token accounts/vaults, não cria `SwapObservation`, não classifica BUY/SELL e não integra o pipeline CPMM.

### CI
- Workflow `SMR tests`, run `44253659374` (#421), concluído com sucesso no commit `708cc57d492fe8f784e9fbcbf641904b5829d913`.
- **274 testes unitários aprovados** e etapa `compileall` aprovada.
- O total CI inclui oito novos testes de associação/base58/loaded addresses; a validação local de 266 testes ocorreu antes desses oito testes novos.

### Próxima etapa
Executar no Termux os oito testes novos e a suíte completa no head atual. Após validação local, avançar para decodificação/reconciliação de transferências SPL/Token-2022 e deltas por operação, sem criar `SwapObservation` antes de evidência econômica completa.

PR #16 permanece Draft, aberto, não merged; `main` intacta. Nenhum RAW foi enviado ao GitHub; nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

## 75. Validação local completa da associação DAMM v2 e estado atualizado do PR16 (18/11/2026)

- Usuário atualizou o clone PR16 por fast-forward de `2396f61` para `5e34958e1726f209020f3fe41a61b2ff76f3176a`; branch correta e working tree limpo foram exigidos pelo comando antes do fetch.
- Testes focados do analisador `test_damm_v2_analyzer.py`: **8/8 aprovados**.
- Testes focados do decoder `test_damm_v2_decoder.py`: **6/6 aprovados**.
- Suíte completa no Termux: **274 testes OK**; `python -m compileall -q src tests` terminou sem erro.
- Alguns testes HTTP exibiram ResourceWarning de recursos temporários/HTTPError; não houve falha. Não há evidência de que esses avisos tenham afetado o resultado funcional.
- CI do head completo `5e34958e1726f209020f3fe41a61b2ff76f3176a`: workflow `SMR tests`, run `44253820850` (#422), concluído com sucesso.
- PR #16 permanece Draft, aberto, mergeable, não merged; base `feat/reconciliation-diagnostics`. `main` permanece intacta.
- A validação cobre decoder e associação estrutural; ainda não cobre associação econômica por transferências SPL/Token-2022 e deltas por swap nos cinco RAW locais.
- Nenhum RAW foi enviado ao GitHub; nenhuma importação, criação/migração SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

### Próxima etapa técnica
Construir uma camada de reconciliação DAMM v2 por operação, começando pela inspeção local redigida dos cinco RAW com o analisador recém-validado e, depois, definindo vínculos conservadores entre instrução/evento, transferências SPL/Token-2022 e deltas de token accounts. Tratar transfer-fee de Token-2022 explicitamente; não reutilizar automaticamente o reconciliador CPMM nem produzir `SwapObservation` enquanto os papéis de contas e quantidades não estiverem comprovados.

## 76. Validação do auditor de associação DAMM v2 nos cinco RAW e início do mapeamento de contas (18/11/2026)

### Auditor local validado
- Usuário atualizou o clone PR16 por fast-forward de `5e34958` para `1083862`.
- `test_damm_v2_association_audit.py`: **3/3 testes aprovados**.
- Auditor local `tools/audit_damm_v2_associations.py`: cinco manifestos auditados, cinco íntegros, zero inválidos.
- Fixtures 1 e 3: cada uma contém uma instrução swap DAMM v2 e um EvtSwap2 associados, ambos `MATCHED`.
- Fixtures 2, 4 e 5: nenhum swap DAMM v2 reconhecido pelo escopo atual.
- Relatório redigido apenas por índice/contagens/estados. Sem rede, SQLite, escrita, checkpoint ou autorização de execução.
- Os resultados confirmam associação estrutural nos RAW reais, não reconciliação econômica.

### Mapeamento de contas iniciado no PR16
- Novo módulo `src/smart_money_radar/data_sources/damm_v2_accounts.py`.
- Novo teste `tests/test_damm_v2_accounts.py`.
- Mapeia as 14 contas base do swap DAMM v2: autoridade do pool, pool, token accounts de input/output, vaults A/B, mints A/B, payer, token programs A/B, referral account, event authority e program; preserva contas adicionais.
- Resolve índices compilados ou chaves já resolvidas.
- Usa a direção A→B/B→A do EvtSwap2 para orientar vault, mint e token program de entrada/saída; verifica que o pool no evento coincide com a conta pool da instrução e que os programas token são SPL Token ou Token-2022.
- Não presume payer como carteira monitorada. Não reconcilia transferências, não calcula quantidades, não cria SwapObservation e não integra o pipeline CPMM.
- Referência de ordem de contas: IDL oficial `cp_amm.json` do SDK Meteora DAMM v2.
- Commits: módulo `5ab5444`; testes `d6d664c`; correções do teste `c9f8aeb` e `e4351fa`.
- CI #435 (run `44255075630`) foi iniciado para o commit anterior à última correção do teste; a validação do head atual ainda não está confirmada.
- **Validação local do novo mapeador pendente**.

### Próxima ação
Executar no Termux o teste `test_damm_v2_accounts.py` e compileall após fast-forward. Só então avançar para correlacionar transferências executadas com input/output accounts e vaults. Token-2022 transfer-fee permanece fail-closed até suportar a extensão de transferência com taxa e reconciliar o líquido/bruto.

PR #16 segue Draft, aberto e não merged; `main` intacta. Nenhum RAW foi enviado ao GitHub; nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

## 77. Correção e validação do mapeador de contas DAMM v2 (18/11/2026)

- A primeira execução local de `test_damm_v2_accounts.py` revelou erro em `_base58_encode()`: a contagem de bytes zero iniciais usava uma sequência literal incorreta, fazendo a codificação do pool do EvtSwap2 divergir da conta pool da instrução.
- Correção funcional no commit `08094285737314dda596c9874077056287d0f9ec`: a função agora conta bytes nulos reais antes de converter o valor para Base58.
- Validação local do usuário no Termux após fast-forward `fe1c6c5..0809428`: **5/5 testes de `test_damm_v2_accounts.py` aprovados**; `python -m compileall -q src tests` terminou sem erro.
- Os testes cobrem direções A→B e B→A, preservação de remaining accounts, rejeição de pool divergente, lista curta, token program desconhecido, resolução de índices compilados e índice inválido.
- CI do commit `08094285737314dda596c9874077056287d0f9ec`: workflow `SMR tests`, run `44255325088` (#441), concluído com sucesso.
- O mapeador agora está validado nos testes específicos e no compileall. Isso não comprova reconciliação econômica: transferências SPL/Token-2022, deltas de token accounts/vaults e taxas Token-2022 ainda não foram correlacionados por operação.
- Próxima etapa: estudar a atribuição conservadora das transferências e dos deltas a cada swap DAMM v2, sem reutilizar automaticamente o reconciliador CPMM e sem criar `SwapObservation` antes de evidência econômica completa.
- PR #16 continua Draft, aberto e não merged; base `feat/reconciliation-diagnostics`; `main` intacta. Nenhum RAW foi enviado ao GitHub; nenhuma importação, criação/migração SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

## 78. Atribuição conservadora de transferências DAMM v2 (18/11/2026)

- Criados `src/smart_money_radar/data_sources/damm_v2_transfer_analyzer.py` e `tests/test_damm_v2_transfer_analyzer.py`.
- A camada recebe associações swap↔EvtSwap2 já comprovadas, mapeamentos de contas e transferências decodificadas; procura no mesmo grupo externo os pares exatos user-input→vault-input e vault-output→user-output.
- Exige transferência executada, descendência CPI em relação ao swap, stackHeight conhecido, caminho CPI confiável e posição anterior ao Event CPI EvtSwap2.
- Exige exatamente uma transferência por papel; múltiplos candidatos ou reutilização da mesma transferência entre operações resultam em `AMBIGUOUS`. Ausência resulta em `TRANSFER_MISSING`; associação estrutural não resolvida resulta em `ASSOCIATION_UNRESOLVED`.
- Exige mint e decimals explícitos, programa token coerente e quantidade bruta positiva. Transfer simples sem mint/decimals fica `INCOMPLETE`.
- Resultado positivo é somente `ATTRIBUTED`, não `MATCHED` econômico. Não compara montantes com EvtSwap2, não reconcilia deltas pre/post de token accounts/vaults, não calcula taxas e não cria `SwapObservation`.
- Token-2022 sinaliza `transfer_fee_review_required`; instruções TransferCheckedWithFee e withheld fees ainda não são decodificadas. Nenhum caso Token-2022 é declarado economicamente reconciliado.
- Endurecido `SolanaTokenTransfer` com `cpi_path_valid`: hierarquia depois de stackHeight ausente/inconsistente é marcada não confiável. O atribuidor rejeita tais transferências mesmo que o decoder mantenha um caminho posicional legado.
- Testes CI:
  - run `44255914744` (#445), primeira implementação e ordem temporal: success.
  - run `44256010582`, proteção temporal adicional: success.
  - run `44256150190`, caminho CPI não confiável e testes correspondentes: success; job de testes e compileall concluídos com sucesso.
- Commits funcionais mais recentes: `34ab6825190b725081859bc59de98b5157eb9c0a`, `6b3d7781abd50475c8801e769dc4237142856895`.
- Validação local no Termux e aplicação aos cinco RAW reais ainda pendentes. Não enviar RAW ao GitHub.
- Próxima etapa: decoder conservador de deltas pre/post por accountIndex, rejeitando snapshots ausentes, duplicados, mint/decimals divergentes e contas sem correspondência; depois correlacionar quatro contas (user input, input vault, output vault, user output) com as transferências atribuídas.
- PR #16 permanece Draft, aberto, não merged; base `feat/reconciliation-diagnostics`; `main` intacta. Nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

## 79. Decoder conservador de deltas pre/post de token accounts (18/11/2026)

- Adicionados `src/smart_money_radar/data_sources/solana_token_balance_delta_decoder.py` e `tests/test_solana_token_balance_delta_decoder.py`.
- Resolve token account por `accountIndex` contra `message.accountKeys` e, em transações não jsonParsed, `meta.loadedAddresses.writable/readonly`.
- Calcula delta em unidades raw inteiras somente quando há snapshots pre e post pareados para o mesmo índice, mint e decimals consistentes.
- Não presume saldo zero quando falta um dos lados; não aceita índice duplicado, índice fora de accountKeys, mint/decimals divergentes, owner divergente, amount inválido ou decimals fora de u8.
- Não produz delta quando `meta.err` é não nulo ou quando o status de execução não foi explicitamente informado.
- Resultado `complete` só é verdadeiro quando não há nenhuma issue no conjunto analisado. Issues são redigidas por código e índice, sem endereço/mint.
- O decoder é genérico e somente leitura. Não atribui delta a swap, carteira ou instrução; não calcula valor UI, não abre banco, não grava e não avança checkpoint.
- CI do head funcional `639b53db5e8c520f87f67ff9204ff1ea78990a52`: run `44256509698`, workflow `SMR tests`, success; job de testes unitários e compileall aprovados.
- Validação local no Termux e auditoria redigida nos cinco RAW ainda pendentes.
- Próxima etapa: adicionar auditor offline redigido para observar cobertura/completude dos snapshots reais e, depois, reconciliar por swap somente quando as quatro contas necessárias tiverem deltas inequívocos. Deltas são transacionais e podem agregar várias operações; contas/vaults reutilizados entre swaps ou transferências externas devem bloquear atribuição individual.
- PR #16 permanece Draft, aberto, não merged; base `feat/reconciliation-diagnostics`; `main` intacta. Nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

## 80. Auditoria redigida de cobertura dos quatro deltas DAMM v2 (18/11/2026)

- Adicionado `tools/audit_damm_v2_delta_coverage.py` e `tests/test_damm_v2_delta_coverage_audit.py`.
- A ferramenta valida cada par manifesto/RAW por `audit_fixture()`, analisa associações DAMM v2↔EvtSwap2, mapeia contas pela direção do evento, decodifica transferências SPL/Token-2022 e calcula deltas pre/post por accountIndex.
- O relatório apresenta somente índice sintético, estados e contagens. Não expõe endereços, mints, assinaturas, caminhos, nomes de arquivo ou quantidades.
- A cobertura dos quatro papéis é verificada separadamente: token account de input, vault de input, vault de output e token account de output. Exige quatro contas distintas, snapshots completos, mints coerentes e sinais dos deltas compatíveis com os fluxos esperados.
- Estados de cobertura incluem colisão de papéis, snapshots incompletos, delta ausente, divergência de mint e sinal divergente. Mesmo `FOUR_ACCOUNT_DELTAS_PRESENT` significa apenas cobertura estrutural/sinais; não prova igualdade de quantidades nem reconciliação econômica.
- Se a atribuição das transferências não for `ATTRIBUTED`, a cobertura é reportada como `TRANSFER_ATTRIBUTION_NOT_CONFIRMED`. Token-2022 continua exigindo revisão de transfer fee.
- A ferramenta é offline e read-only: sem RPC/Helius, SQLite, escrita de arquivos, checkpoint, importação ou execução. Não cria `SwapObservation`.
- Commits: auditor `bf8e0ba074d7c12394f4ebb516eb982f41b675f3`; testes `60e43d92352e013d797c2ed77bd38f631f58d44c`.
- CI para o commit do auditor iniciou como run `44256966076` (#464), ainda `in_progress` na última consulta. O CI do commit que acrescenta os testes ainda não foi confirmado.
- Validação local no Termux e auditoria dos cinco RAW permanecem pendentes. Nenhum RAW foi enviado ao GitHub.
- Próximo passo após CI: validar os testes no Termux e executar o auditor sobre os cinco RAW. Não promover cobertura de quatro deltas a reconciliação econômica sem comparar valores brutos/líquidos com transferências e EvtSwap2, contabilizar fees e provar exclusividade por operação.
- PR #16 permanece Draft, aberto, não merged; `main` intacta. Nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain foi executada.

### Correção de integração dos testes e CI subsequente
- O primeiro CI que incluiu o teste novo falhou por ModuleNotFoundError: a função de cobertura estava definida no script tools/, enquanto o teste a importava como módulo de data_sources.
- Correção: extraída a função para src/smart_money_radar/data_sources/damm_v2_delta_coverage_audit.py; o script CLI agora importa essa função compartilhada.
- Commits corretivos: módulo 5afcbb9c39d57e3b0b424bb1f1cbffc0f797b2da; refatoração CLI a3034ad69da208d2f33fa306a733ad72ee603e25.
- Novo CI para o head corretivo: run 44257098656 (#469), ainda in_progress na última consulta. Não declarar aprovação até conclusão.

## 81. Validação local da cobertura de deltas DAMM v2 nos cinco RAW (18/11/2026)

O clone local PR16 foi atualizado por fast-forward até `1e85540`; a árvore de trabalho foi confirmada limpa antes da validação.

### Testes
- `test_damm_v2_delta_coverage_audit.py`: **6/6 aprovados**.
- Suíte completa: **309 testes aprovados** (`Ran 309 tests`, `OK`).
- Avisos `ResourceWarning` em testes HTTP/SQLite apareceram, mas não causaram falhas.
- Esta execução não incluiu `compileall`; não declarar essa etapa como validada neste head local.

### Auditoria local dos cinco RAW
- `manifest_count=5`, `audited_count=5`, todos com status operacional `AUDITED`.
- Fixture 1: um swap; uma transferência estruturalmente atribuída; cobertura bloqueada por `DELTA_SIGN_MISMATCH`; revisão de transfer fee necessária.
- Fixture 2: nenhum swap DAMM v2 reconhecido; uma issue de delta no conjunto da transação.
- Fixture 3: um swap; uma transferência estruturalmente atribuída; cobertura bloqueada por `SNAPSHOT_SET_INCOMPLETE`; uma issue de delta.
- Fixtures 4 e 5: nenhum swap DAMM v2 reconhecido no escopo atual; sem issue de delta reportada.
- As duas transferências com status `ATTRIBUTED` continuam sendo atribuições estruturais, não quantidades economicamente reconciliadas.
- `AUDITED` significa que o par foi processado pela ferramenta, não que o swap passou na reconciliação.

### Limites e segurança
- Nenhuma operação DAMM v2 alcançou `FOUR_ACCOUNT_DELTAS_PRESENT` no relatório local.
- Não há reconciliação econômica: ainda faltam igualdade exata entre transferências brutas, deltas líquidos e campos executados de EvtSwap2; contabilização das taxas do protocolo; análise de transfer fee/withheld fee Token-2022; e prova de exclusividade dos efeitos por operação.
- Flags confirmaram `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false`, `economic_reconciliation=false` e `execution_authorized=false`.
- Nenhum RAW ou mapa de carteira foi enviado ao GitHub. Nenhuma importação, SQLite, RPC/Helius, checkpoint ou operação on-chain foi executada.

### Próxima fronteira técnica
Antes de implementar reconciliação econômica, especificar os invariantes por modo `ExactIn`, `PartialFill` e `ExactOut`, os campos efetivamente executados de `EvtSwap2`, as taxas do protocolo e os efeitos de Token-2022. Deltas pre/post são agregados à transação; se houver efeitos de outras instruções/operações sobre as mesmas contas, não repartir por heurística: manter `INCOMPLETE` ou `AMBIGUOUS`. Criar testes sintéticos positivos e negativos para cada regra antes de qualquer produção de `SwapObservation`.

PR #16 permanece Draft, aberto e não integrado; `main` intacta.

## Especificação de reconciliação econômica DAMM v2 (18/11/2026)
- Criado docs/DAMM-V2-RECONCILIACAO-ECONOMICA.md no commit 3199cca4d14bf22e0934a2688423f32c91a0f136.
- Formalizados parâmetros ExactIn, PartialFill e ExactOut; distinção entre limites solicitados e efeitos executados; campos EvtSwap2 preservados sem presumir equações ainda não verificadas.
- Definido livro de quantidades por operação: débito bruto do usuário, crédito líquido do vault de entrada, débito do vault de saída, crédito líquido do usuário, transfer fees/withheld e taxas AMM separadas.
- Definidos requisitos fail-closed para Token-2022, exclusividade de transferências, contas compartilhadas, deltas pre/post agregados e ausência de resíduos.
- Matriz de testes sintéticos obrigatória e separação entre decoder, atribuição, reconciliação econômica e contratos de domínio.
- A fonte oficial atual confirma os modos e os campos do evento, mas as equações exatas ainda precisam ser auditadas no código fixado MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e. Nenhum reconciliador econômico foi implementado.
- Estado dos RAW permanece: fixture 1 DELTA_SIGN_MISMATCH com revisão de transfer fee; fixture 3 SNAPSHOT_SET_INCOMPLETE; nenhuma operação com MATCHED econômico.
- Nenhuma importação, SQLite, RPC/Helius, checkpoint ou operação on-chain.

## Auditoria das equações DAMM v2 no código oficial fixado (18/11/2026)
- Auditoria direta de MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e, incluindo exact-in, partial-fill, exact-out, pool result, fee mode, token fee helpers e transferência CPI.
- Confirmado: included_transfer_fee_amount_in é o valor bruto transferido do usuário; SwapResult2.included_fee_input_amount é o crédito líquido no pool antes da taxa AMM; excluded_fee_input_amount é após taxa AMM.
- Confirmado: saída principal usa included_transfer_fee_amount_out como transferência bruta do vault e excluded_transfer_fee_amount_out como crédito líquido esperado do usuário.
- ExactIn converte amount_0 bruto em entrada líquida; ExactOut converte amount_0 (saída líquida desejada) em saída bruta e calcula entrada bruta máxima com taxas; PartialFill ajusta a transferência de entrada ao consumo efetivo e deixa amount_left sem transferir do usuário.
- Meteora invoca TransferChecked; Token-2022 aplica TransferFeeConfig do mint. Não se deve exigir opcode TransferCheckedWithFee específico. O withheld amount precisa de evidência do estado do token account/configuração histórica.
- Confirmado que collect_fee_mode + trade_direction determinam fees_on_input/fees_on_token_a; referral gera transferência separada adicional do vault. Protocol/LP/compounding/referral fees não podem ser confundidas com Token-2022 transfer fees.
- Documento docs/DAMM-V2-RECONCILIACAO-ECONOMICA.md seção 12 registra as relações e limites. Próximo passo: fixtures sintéticas com equações e rounding, inclusive ambos os sentidos, fee mode e referral; depois decodificador de withheld state e reconciliador puro.
- Nenhum reconciliador, SwapObservation, DB, importação, RPC/Helius, checkpoint ou ação on-chain foi implementado/executado.

- Complemento Token-2022: a documentação oficial confirma que TransferChecked retém automaticamente a taxa em TransferFeeAmount na conta de destino. TransferCheckedWithFee é opcional e não é exigido pelo código Meteora fixado. Atribuição de withheld exige configuração do mint no epoch histórico e variação da extensão da conta; estado final agregado sem estado anterior não prova atribuição individual.

- Refinamento de critério: a leitura direta da extensão TransferFeeAmount é corroborativa, não requisito absoluto. A taxa pode ser provada por transferência bruta + campos bruto/líquido do EvtSwap2 + delta spendable pre/post, se todos os movimentos da conta estiverem identificados e a atribuição for exclusiva. Deltas agregados com movimentos não atribuídos continuam INCOMPLETE.

- Matriz de FeeMode documentada na seção 12.10: collect_fee_mode + direção definem fees_on_input, fees_on_token_a e o mint/vault de cobrança; referral_fee é transferido separadamente e split_fees registra protocol_fee líquido de referral. Reconciliador deverá validar a transferência referral quando has_referral.

## 82. PR #17 — aritmética pura de taxas DAMM v2 / Token-2022 (18/11/2026)

- Confirmada sincronização local PR16: `HEAD=0d951fc`, branch `feat/offline-fixture-inspector`, acompanhando `origin`, árvore limpa.
- Criada branch `feat/damm-v2-economic-fee-math` a partir do head PR16 `0d951fc5413d0f83a328c71e76055e1f1f58c05b`; PR #17 aberto como Draft, base PR16, não integrado.
- Novo módulo `src/smart_money_radar/data_sources/damm_v2_fee_math.py`: aritmética pura para TransferFee Token-2022 (gross/net, ceil, maximum_fee, taxa 100%, overflow), taxas AMM DAMM (included/excluded, denominador 1e9, rounding up), split claiming/compounding/protocol/referral (rounding down) e matriz de seis FeeMode.
- Novo teste `tests/test_damm_v2_fee_math.py`: 18 métodos de teste sintéticos determinísticos, sem rede, DB, relógio ou RAW.
- Nova documentação `docs/DAMM-V2-ARITMETICA-TAXAS.md` descreve fontes oficiais, regras reproduzidas e limites.
- Fontes Meteora fixadas em `18936b18c26708f6e9b52cacc01ea2f99868ba8e`; Token-2022 TransferFee interface consultada para ceil/cap/inversão.
- Importante: isto valida primitivas aritméticas, não a reconciliação de uma operação. Não decodifica bytes/configuração histórica de mint ou epoch, não modela a curva/amount_left de PartialFill, não atribui transferências/deltas, não verifica referral on-chain e não produz MATCHED nem SwapObservation.
- CI do PR #17 ainda não apareceu na consulta inicial; não declarar testes aprovados até workflow terminar. Clone local PR17 ainda não foi criado nem sincronizado.
- PR #16 permanece Draft e não integrado; PR #17 permanece Draft e não integrado; `main` intacta. Nenhum RAW foi alterado/enviado. Nenhuma importação, SQLite, RPC/Helius, checkpoint ou operação on-chain.
- Próxima ação: acompanhar CI do PR #17; corrigir falhas e então sincronizar branch PR17 no Termux para executar os 17 testes focais e a suíte completa. Após validação, avançar para decodificação explícita de TransferFeeConfig/TransferFeeAmount e depois reconciliador econômico fail-closed.

## 83. Validação local e CI do PR #17 — aritmética de taxas DAMM v2 / Token-2022 (18/11/2026)

### Validação local no Termux
- Clone separado criado em `$HOME/SMART-MONEY-RADAR-PR17`, sem tocar na cópia original nem nos clones PR15/PR16.
- Branch confirmada: `feat/damm-v2-economic-fee-math`; HEAD local `99ce0ce`; árvore de trabalho limpa e sincronizada com origin.
- Testes focais de `test_damm_v2_fee_math.py`: **18/18 aprovados** (a suíte efetiva contém 18 métodos de teste, embora a seção 82 tenha descrito originalmente 17 casos).
- Suíte completa: **327 testes aprovados** (`Ran 327 tests`, `OK`).
- `python -m compileall -q src tests` executado sem erro.
- ResourceWarnings de HTTPError/SQLite apareceram em alguns testes, sem falha; permanecem como observação técnica, não como falha da suíte.

### CI
- Commit validado: `99ce0ce3b3d76b97e86fd52d2855c34a01011b33`.
- Workflow `SMR tests`, run `44260221128` (#484): **success**.
- O status combinado não retornou status contexts adicionais; a aprovação é sustentada pelo workflow concluído com sucesso.

### Interpretação e limites
- Aritmética isolada está validada localmente e no CI; isso não equivale a reconciliação econômica DAMM v2 completa.
- Ainda faltam decoder dos bytes de TransferFeeConfig/TransferFeeAmount com seleção histórica de epoch, curva executada de PartialFill, atribuição exclusiva de referral e demais transferências, conciliação bruta/líquida com EvtSwap2 e deltas por operação.
- Os cinco RAW locais continuam sem reconciliação econômica confirmada; resultados anteriores de cobertura permanecem fail-closed.
- Não foi executada importação, criação/migração SQLite, RPC/Helius, checkpoint, trade ou operação on-chain. Nenhum RAW ou mapa de carteira foi enviado ao GitHub.

PR #17 continua Draft, aberto e não integrado; PR #16 continua Draft e não integrado; `main` permanece intacta.

### Próxima etapa técnica
Implementar, isoladamente e com testes sintéticos, o decoder de estado Token-2022 (`TransferFeeConfig` e `TransferFeeAmount`), incluindo seleção da taxa aplicável ao epoch histórico e validação de bytes/offsets. Não iniciar reconciliador nem persistência até essa camada ser revisada.

## 84. Bloqueio de evidência CPI não confiável na reconciliação CPMM (18/11/2026)

- Correção autorizada pelo usuário para o finding da auditoria de integração: o decoder já marcava `SolanaTokenTransfer.cpi_path_valid=False` após `stackHeight` ausente/inconsistente, mas dois consumidores aceitavam a transferência sem consultar o indicador.
- Em `raydium_cpmm_transfer_reconciliation.py`, `_is_descendant()` agora rejeita transferências internas cujo `cpi_path_valid` não seja explicitamente `True`. Swaps externos continuam usando o escopo do grupo `innerInstructions` associado à instrução externa, sem exigir prova de descendência CPI interna.
- Em `swap_bundle_builder.py`, `_validate_transfer_evidence()` revalida o indicador no limite do domínio para swaps internos; evidência CPI não confiável gera `ValueError` e não pode produzir `SwapDomainBundle`.
- Testes de regressão adicionados: caminho aparentemente descendente com `cpi_path_valid=False` resulta `INCOMPLETE`; builder rejeita reconciliação marcada MATCHED quando a transferência interna tem caminho não confiável; teste preserva o comportamento de swap externo escopado ao grupo externo.
- Commits GitHub na branch `feat/damm-v2-economic-fee-math`: `cf8773983b2c14ea8293cedf6c2724844229aa98` (reconciliação), `8f357b9f0b92c3b14efdcf3b1a9b80656cba2fc7` (limite do domínio), `feea909deeb50723badb015eebdef17d787aa4bf` (teste de reconciliação), `0dbcd4f184063de2c4d891d3c0b1c428602000bd` (teste do builder) e `3ea650b642311210bd052bf4ca33d27807c82c10` (teste de preservação do swap externo).
- CI confirmado no HEAD `bf70082019880e14c6281e672bbcd43f51e32a03`: workflow `SMR tests`, run #513 (`44266056128`), **success**; etapas `Run unit tests` e `Compile source and tests` concluídas com sucesso.
- Escopo: nenhuma alteração em `main`, RAW fixtures, banco de dados, imports de dados, RPC/Helius, checkpoints, persistência ou operações on-chain. PR #17 permanece Draft e não integrado; PR #18 não foi alterado.
- Efeito colateral de integração identificado, sem alteração no PR #18: como sua branch foi criada sobre o antigo head do PR #17 (`58606137e3d096e19b34eb84bae604101c07fef`), a comparação atual mostra PR #18 divergente da nova base: 16 commits à frente e 6 atrás; `mergeable=false`. Nenhum rebase/update foi executado nele.
- Próxima ação: decidir e executar separadamente a atualização/rebase da branch do PR #18 para incorporar a nova base do PR #17, mantendo ambos em Draft e sem merge.

## 85. PR #18 — decoder de estado TransferFee Token-2022 (18/11/2026)

- Branch `feat/token2022-transfer-fee-state-decoder` criada sobre o head do PR #17 (`58606137e3d096e19b34eb84bae604101c07fef`), sem alterar `main`.
- PR #18 aberto como Draft, base `feat/damm-v2-economic-fee-math`, head documental inicial `26bfdd773eb10cd8d15688498ac6f3cf07bc0bf2`; não integrado.
- Criado `src/smart_money_radar/data_sources/token2022_transfer_fee_state.py`: decoder TLV estrito para `TransferFeeConfig` (108 bytes) e `TransferFeeAmount` (8 bytes), tipo de conta Mint/Account, cabeçalho little-endian, offsets 165/166 e validação de payload.
- `TransferFeeConfigState.fee_for_epoch(epoch)` escolhe newer quando epoch >= newer.epoch; caso contrário older. Epoch é argumento explícito, nunca inferido pelo decoder.
- Criado `tests/test_token2022_transfer_fee_state.py` com 12 testes sintéticos: epoch boundary, withheld, extensão desconhecida, padding zero, tipo incorreto, ausência, truncamento, tamanho, duplicação, basis points e tipos inválidos.
- Criado `docs/TOKEN2022-TRANSFER-FEE-STATE-DECODER.md` com layout e limites.
- Fonte consultada: `solana-program/token-2022`, `interface/src/extension/transfer_fee/mod.rs` e `interface/src/extension/mod.rs` no branch main em 18/11/2026. Discriminantes 1/2 e AccountType Mint=1/Account=2 confirmados.
- Testes locais e CI ainda pendentes; não declarar decoder validado. O PR #18 foi criado Draft; mergeability ainda não é conclusiva e não será integrado nesta etapa.
- Limites: authorities permanecem bytes opacos; withheld_amount isolado não prova taxa de uma transferência; decoder não consulta RPC, não persiste, não atribui transferências, não reconcilia e não cria SwapObservation.
- Nenhum RAW foi alterado/enviado. Nenhuma importação, SQLite, RPC/Helius, checkpoint, trade ou operação on-chain.

### Próxima ação
Aguardar CI e validar no Termux em clone separado PR18: testes focais, suíte completa, compileall, HEAD e status. Corrigir qualquer falha antes de ampliar o decoder ou iniciar reconciliação econômica.

### Validação local e CI do PR #18 — 18/11/2026

- Clone separado confirmado em `$HOME/SMART-MONEY-RADAR-PR18`, branch `feat/token2022-transfer-fee-state-decoder`, HEAD local `0d2b906`, árvore limpa e sincronizada com origin.
- Testes focais: 12/12 OK.
- Suíte completa: 339 testes OK.
- `python -m compileall -q src tests`: concluído sem erro (o encadeamento do comando chegou a `git rev-parse` e `git status`).
- CI GitHub run `44261319172` (#490): completed/success no commit `0d2b9069072d3547b3dce8d79a77b31c4bf67ff9`.
- Foram observados ResourceWarnings não fatais em testes preexistentes de HTTP/SQLite; não houve falha. Isso não comprova ausência de vazamentos e não foi escopo corrigido nesta etapa.
- Conclusão: PR18 tem validação local e CI aprovados para o head atual. Continua Draft, aberto e não integrado. Nenhuma integração autorizada.

### Revisão defensiva adicional do decoder PR #18
- Revisão do código identificou que o parser verificava AccountType e TLV, mas não validava explicitamente os bytes de padding do Mint entre o fim da base de 82 bytes e o AccountType no offset 165.
- Corrigido `decode_transfer_fee_config()` para rejeitar qualquer byte não zero nesse intervalo.
- Adicionado teste negativo `test_rejects_nonzero_mint_padding`.
- Atualizada a documentação do decoder. Commits de correção: `409574205c9fafd971e75dde60385e04e88b62c6` (código), `204a4ae54cdf32dd9245534915da84b90c334ace` (teste), `3f7c9eb75ff292ef29b9adf3d1a227f219293a83` (documentação).
- Os resultados prévios 12/12 focais, 339 testes e CI #490/#491 referem-se ao código anterior à correção. A nova versão ainda requer validação local e CI. Não considerar o head novo validado.

### Auditoria de compatibilidade TLV do PR #18 — 18/11/2026

- Revisão comparativa com o iterador oficial try_for_each_tlv_extension_type em solana-program/token-2022/interface/src/extension/mod.rs.
- Encontrada divergência de compatibilidade: o decoder rejeitava uma cauda final de um byte e rejeitava bytes após o marcador TLV Uninitialized (tipo 0), enquanto o iterador oficial encerra a leitura nesses casos (a cauda de um byte pode ocorrer durante realocação).
- Ajustado _read_extensions() para: (a) encerrar quando resta menos de 2 bytes; (b) encerrar ao encontrar tipo Uninitialized; (c) continuar rejeitando cabeçalho incompleto de entrada não terminadora e payload truncado.
- Adicionados dois testes: cauda de um byte durante realocação e terminador Uninitialized.
- Atualizada a documentação para registrar a semântica compatível com Token-2022.
- Commits desta correção: código c60d99d8cbb088a3999ae2813f9bd8864e088bc1, testes 73d26dc303cc9508865fc673f7d8dbf4443ea749, documentação ab4f947bfb35ba590b830bf2a1ff28afd55224d4.
- A validação CI #495 (340 testes) refere-se ao head anterior e8b30976efe36de2878efec79b8d25035ac3efbc; não valida estas alterações novas.
- Estado: aguardando CI no novo head. PR permanece Draft, aberto e não integrado.

### CI corretivo da compatibilidade TLV — 18/11/2026

- Primeira execução após os novos testes: run 44264725856 (#499), falhou em 2 testes focais porque os literais binários foram gravados com barras invertidas duplicadas; os testes não estavam fornecendo os bytes pretendidos.
- Corrigidos os literais para bytes reais: cauda 0x7f e terminador 00 00 seguido por bytes residuais.
- Commit corretivo dos testes: ab6d994ddf2e7adf86039c3a4bf3ba4bce9b2888.
- Novo CI do PR: run 44264858445 (#503), evento pull_request, associado ao head ab6d994ddf2e7adf86039c3a4bf3ba4bce9b2888; estado observado: queued.
- A execução #499 não deve ser usada como validação final. A execução #495 (340 testes) valida apenas o head anterior e8b3097.
- Próxima ação: consultar o resultado do run #503, confirmar todos os testes e compileall, depois revisar novamente o diff completo e a mergeability do PR. Não integrar nem remover o estado Draft nesta etapa.

### Validação CI após correção TLV — resultado confirmado

- CI #503 (run 44264858445), commit de código/testes ab6d994ddf2e7adf86039c3a4bf3ba4bce9b2888: success; 342 testes executados; etapa compileall concluída com sucesso.
- CI #504 (run 44264912053), head ac0390a0d8fc285ba906bcf05453898f2bf3efae: success; 342 testes executados; etapa compileall concluída com sucesso.
- Os 2 testes novos de compatibilidade TLV passaram na execução #503/#504; total de testes do decoder: 15.
- O head ac0390a é uma atualização documental do Registro Mestre sobre o resultado corretivo; o código e os testes validados permanecem nos commits c60d99d, 73d26dc e ab6d994.
- PR #18 continua aberto, Draft, não integrado, mergeable=true; base feat/damm-v2-economic-fee-math; branch está 15 commits à frente e 0 atrás da base. Nenhuma review registrada.
- Não alterar main nem integrar. Próxima ação: revisão final do diff e decisão explícita sobre retirar Draft/merge em etapa separada.

### Integração das branches PR #17 e PR #18 — 18/11/2026
- Branch `feat/token2022-transfer-fee-state-decoder` atualizada por merge commit para incorporar o HEAD atual `fd0f73284039bacc4ec4e6b6a88def21f813ce0d` do PR #17.
- O histórico original do PR #18 foi preservado como segundo parent do merge commit; o HEAD do PR #17 é o primeiro parent.
- O Registro Mestre foi consolidado: seção 84 registra a correção CPI do PR #17 e a seção 85 preserva o registro técnico do decoder Token-2022 do PR #18.
- Nenhum PR foi integrado; ambos permanecem Draft. `main` não foi modificada.
- CI do merge commit `c04fafcfd50b810b56cacbf1f110d703f29b8c10`: workflow `SMR tests`, run #515 (`44266493751`), **success**; `Run unit tests` e `Compile source and tests` concluídos com sucesso.
- Próxima ação: revisar o diff integrado do PR #18 e confirmar se a mergeability permanece estável; não retirar Draft nem integrar sem autorização.

## 86. Atualização documental final do PR #18 — sincronização e CI (18/11/2026)

- PR #18 permanece aberto, Draft e não integrado; branch `feat/token2022-transfer-fee-state-decoder`, base `feat/damm-v2-economic-fee-math`.
- A branch do PR #18 incorpora o head do PR #17 `fd0f73284039bacc4ec4e6b6a88def21f813ce0d`. Comparação atual entre esse head e o head do PR #18 `769bf4ba07b697f615c00be6c22006d3dc7edb39`: **18 commits à frente, 0 atrás**; merge base igual ao head do PR #17.
- O diff próprio do PR #18 contra a base atual contém exatamente quatro arquivos: este Registro Mestre, `docs/TOKEN2022-TRANSFER-FEE-STATE-DECODER.md`, `src/smart_money_radar/data_sources/token2022_transfer_fee_state.py` e `tests/test_token2022_transfer_fee_state.py`. A correção CPI do PR #17 está na base e não é duplicada no diff próprio do PR #18.
- CI GitHub Actions `SMR tests`, run #517 (`44266570005`), associado ao HEAD `769bf4ba07b697f615c00be6c22006d3dc7edb39`: **completed/success**. Job `test`, etapas `Run unit tests` e `Compile source and tests` concluídas com sucesso.
- CI #515 também havia passado no merge commit da sincronização. O resultado #517 é a validação final registrada para o HEAD documental atual.
- Revisão estática final do decoder não encontrou bloqueio técnico evidente: TLV, tipos/tamanhos das extensões, offsets, padding, truncamentos/duplicações, terminador `Uninitialized`, cauda final de um byte e seleção older/newer por epoch estão cobertos pela implementação/testes e alinhados ao comportamento oficial consultado.
- Limites preservados: decoder offline; não consulta RPC, não infere epoch, não persiste, não atribui taxas a transferências/swaps, não reconcilia e não cria `SwapObservation`. `withheld_amount` isolado não prova taxa aplicada. Testes/CI não equivalem a validação econômica em nova fixture mainnet.
- Nenhuma alteração em `main`, RAW fixtures, banco de dados, imports, RPC/Helius, checkpoints ou operações on-chain. PR #17 e PR #18 continuam Draft e não integrados.
- A descrição do PR #18 foi alinhada aos resultados atuais nesta mesma atualização. Próxima decisão permanece separada: revisão/decisão formal sobre retirar Draft e eventual integração; nenhum merge está autorizado ou executado por esta atualização documental.

## 87. CI da atualização documental final do PR #18 — 18/11/2026

- O commit documental `5e1448e13f7ec45878409ccc6c31b37066087f64` atualizou a seção 86 e alinhou a descrição do PR #18.
- Comparação após esse commit: **19 commits à frente, 0 atrás** do head do PR #17 `fd0f73284039bacc4ec4e6b6a88def21f813ce0d`; merge base igual ao head da base. O diff próprio continua com quatro arquivos.
- CI GitHub Actions `SMR tests`, run #518 (`44267390443`), associado exatamente ao commit `5e1448e13f7ec45878409ccc6c31b37066087f64`: **completed/success**. Job `test`, etapas `Run unit tests` e `Compile source and tests` concluídas com sucesso.
- PR #18 continua aberto, Draft e não integrado. PR #17 continua aberto, Draft e não integrado. `main` permanece intacta.
- Nenhuma alteração de código foi feita nesta atualização documental. Nenhuma fixture RAW, banco de dados, importação, RPC/Helius, checkpoint ou operação on-chain foi tocada.

## 88. Confirmação final do CI #519 e estado do PR #18 — 18/11/2026

- Workflow GitHub Actions `SMR tests`, run #519 (`44267551234`), associado ao HEAD `ad8d9e84a7fd28e2d457ff90ffffe77f840fb210`: **completed/success**.
- Job `test`: sucesso. Etapas `Run unit tests` e `Compile source and tests` concluídas com sucesso.
- Comparação do HEAD PR #18 contra o HEAD da base PR #17 (`fd0f73284039bacc4ec4e6b6a88def21f813ce0d`): **20 commits à frente, 0 atrás**; merge base igual ao HEAD da base.
- Diff próprio da branch PR #18 contra a base: quatro arquivos — este Registro Mestre, documentação do decoder, módulo `token2022_transfer_fee_state.py` e seus testes. A correção CPI permanece na base PR #17, sem duplicação no diff próprio do PR #18.
- PR #18 permanece aberto, Draft e não integrado; PR #17 permanece aberto, Draft e não integrado. `main` permanece intacta.
- Esta confirmação não representa validação com fixture RAW mainnet, reconciliação econômica de swap, execução em tempo real ou prontidão operacional. Nenhum RPC/Helius, banco, importação, checkpoint, fixture RAW ou operação on-chain foi executado.

## 89. CI do registro atualizado — 18/11/2026

- O commit documental `e316669fdceb3cee7e31e55808d272ccbf3ef58f` registrou o resultado final do CI #519 e o compare de PR #18.
- CI GitHub Actions `SMR tests`, run #520 (`44268850500`), associado exatamente a esse commit: **completed/success**. Job `test`, etapa `Run unit tests` e etapa `Compile source and tests` concluídas com sucesso.
- A comparação permanece em **21 commits à frente, 0 atrás** do head da base PR #17; merge base igual ao head da base.
- PR #17 e PR #18 continuam abertos, Draft e não integrados. `main` permanece intacta.
- CI aprovado valida a suíte automatizada e compileall do repositório nesse commit; não substitui validação com fixtures RAW mainnet, nem demonstra reconciliação econômica DAMM v2 ou operação realtime.

## 90. Preparação da próxima camada — Meteora DAMM v2 EvtSwap2 (18/11/2026)

- CI #521 (`44268921382`) no HEAD `59d6ee91d6ffdd02929ae99fce7a4be7e8c156b0`: **completed/success**; job `test`, testes unitários e compileall aprovados.
- Criada Issue #19: `Implementar decoder isolado do evento Meteora DAMM v2 EvtSwap2`, para especificar o próximo módulo sem ampliar indevidamente o escopo do decoder Token-2022.
- Criada branch `feat/meteora-damm-v2-evtswap2-decoder` a partir do HEAD validado do PR #18 (`59d6ee91d6ffdd02929ae99fce7a4be7e8c156b0`). Ainda sem commits próprios ou alterações de código.
- Auditoria de documentação oficial confirmou que DAMM v2 emite `EvtSwap2` por Anchor event-CPI e documenta modos ExactIn/PartialFill/ExactOut, direção A→B/B→A, valores de taxa, transfer-fee fields e snapshots de reservas.
- Encontrada uma proteção de compatibilidade necessária: o changelog oficial registra a substituição de `partner_fee` por `claiming_fee` + `compounding_fee`. Parsers antigos com `partner_fee` não podem ser usados como schema atual.
- Antes de implementar, a revisão exata do IDL/código on-chain e os discriminators devem ser fixados e verificados. A documentação atual, isoladamente, não é suficiente para assumir layout binário deployed.
- Escopo da próxima camada: decoder offline e fail-closed do evento; associação ao swap externo somente com caminho CPI confiável. Sem reconciliação econômica, classificação BUY/SELL, persistência, RPC, RAW ou operação on-chain.
- PR #17 e PR #18 permanecem Draft, abertos e não integrados; `main` permanece intacta.

## 91. Correção de rota: decoder EvtSwap2 já existia; PR #20 encerrado sem merge (18/11/2026)

- Auditoria do repositório revelou que a implementação do evento DAMM v2 já existe em `src/smart_money_radar/data_sources/damm_v2_decoder.py`, fixada em `MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e`.
- O decoder existente já valida `EVENT_CPI_TAG` (`e445a52e51cb9a1d`), discriminator `EvtSwap2` (`bd4233a826507599`), tamanho total 196 bytes, Borsh bool, direção, collect_fee_mode e swap_mode; usa o schema atual `claiming_fee` + `compounding_fee`.
- O projeto também já possui `damm_v2_analyzer.py` para associação estrutural swap↔evento por grupo externo, stackHeight e caminho CPI; `damm_v2_accounts.py` valida que pool do evento corresponde à conta pool da instrução; `damm_v2_transfer_analyzer.py` atribui transferências descendentes e evita reutilização entre operações.
- Portanto, o novo decoder separado criado no branch `feat/meteora-damm-v2-evtswap2-decoder` era redundante e continha envelope Anchor em ordem de bytes incorreta. PR #20 foi fechado deliberadamente sem merge. Nenhum arquivo duplicado foi incorporado à base PR #18. A branch auxiliar fica abandonada; não usar como base de trabalho.
- Issue #19 foi renomeada para auditar e avançar a reconciliação econômica DAMM v2 usando os módulos existentes.
- Próximo trabalho correto: auditar invariantes de ponta a ponta entre `EvtSwap2`, transferências atribuídas, taxas Token-2022 por epoch e deltas de token accounts/vaults por operação. Não criar outro decoder.
- Nenhuma alteração em `main`, RAW fixtures, banco, imports, RPC/Helius, checkpoints ou operações on-chain.


## 92. Token-2022 TransferCheckedWithFee decodificado e testado — 18/11/2026

- Issue #19 foi refinada para suportar `TransferCheckedWithFee` antes da reconciliação econômica DAMM v2.
- Criado PR #21, Draft, branch `feat/token2022-transfer-checked-with-fee`, base PR #18.
- `solana_token_transfer_decoder.py` agora reconhece opcode Token-2022 26 + subdiscriminador 1, layout de 19 bytes, contas source/mint/destination/authority, amount u64, decimals u8 e fee u64; registra `instruction_type=TRANSFER_CHECKED_WITH_FEE` e `fee_amount_raw`.
- A variante só é reconhecida sob Token-2022. Outros subdiscriminadores permanecem ignorados. A variante jsonParsed só é aceita quando feeAmount está presente.
- `raydium_cpmm_transfer_reconciliation.py` trata o débito da origem pelo bruto e o crédito spendable do destino como `amount - fee`; `output_amount_raw` representa o valor líquido recebido pela carteira.
- A primeira execução CI #535 (`44269711111`) detectou um erro no teste de taxa inválida: a validação ocorria tarde demais e lançava ValueError. Corrigido no commit `931d82744a350bf94c4293b819f13497cb630830`, movendo a validação para o limite de entrada da reconciliação.
- CI #537 (`44269793991`) no HEAD `931d82744a350bf94c4293b819f13497cb630830`: **completed/success**; 352 testes aprovados e compileall aprovado.
- A taxa declarada em TransferCheckedWithFee é validada pelo próprio programa Token-2022 contra o epoch corrente; em transação executada com sucesso, o destino recebe amount-fee em saldo spendable e o withheld fica na extensão TransferFeeAmount. O decoder não infere epoch nem consulta estado de mint.
- Limites: TransferChecked padrão com taxa implícita continua sem fee explícita e deve falhar fechado se os deltas não reconciliarem. A atribuição DAMM v2 permanece ATTRIBUTED, não MATCHED; reconciliação econômica DAMM v2 ainda não foi implementada.
- Sem RPC/Helius, RAW fixtures, SQLite, checkpoints ou operações on-chain. PR #17, #18 e #21 permanecem Draft e não integrados; PR #20 foi fechado sem merge por duplicar decoder já existente. `main` intacta.


## 250. Integração das dependências CPMM e segurança do painel local — 19/11/2026

### Integrações concluídas em branches intermediárias

- PR #9 integrada: merge commit `802243877dc7f1350ab72b17565f8468785d1c29`; CI no head da PR #9 run `44434553632` passou (539 testes + compileall).
- PR #10 integrada: merge commit `a7e8a47a6ff29817d1ec13e2d2f965d6e857a425`; CI do merge commit run `44437095983` passou: **182 testes OK** + compileall.
- PR #12 integrada: merge commit `6ba4df2e50f24abfaafb69ff037d11b83cb479ca`; CI do merge commit run `44437214287` passou: **183 testes** + compileall.
- PR #13 integrada: merge commit `f4cbbd8d08438a9f01ab3bae1019fc9a027dd588`; CI do merge commit run `44437322311` passou: **196 testes** + compileall.
- PR #14 integrada: merge commit `c6f2687c519a691d953244b09b18ecf445bde52a`; CI do merge commit run `44437738900` passou: **225 testes** + compileall.
- Todas essas integrações ocorreram em branches de feature; nenhuma foi mergeada na `main`.

### Correção adicional do checkpoint no EventStore (PR #14)

Foi identificado que um replay tardio de assinatura pendente poderia marcar a assinatura como processada e regredir o checkpoint para um slot mais antigo. `mark_processed()` agora sempre registra a assinatura concluída, mas só avança o checkpoint quando a posição temporal comprovada não é anterior ao cursor atual; em slots iguais, preserva conservadoramente o checkpoint existente porque o EventStore não armazena índice de transação dentro do slot. Teste dedicado cobre processamento de slot 100, depois slot 200, seguido de replay do slot 100; checkpoint permanece no slot 200.

### PR #15 — diagnóstico e painel Android somente leitura

- PR #15 permanece OPEN/DRAFT, branch `feat/reconciliation-diagnostics`, base `integration/pr13-sqlite-persistence`.
- Foi necessário sincronizar a cadeia empilhada: branch-base estava quatro commits à frente. As alterações sobrepostas foram conciliadas preservando o EventStore/fixture do PR #14, os métodos de diagnóstico da PR #15 e o workflow que testa `integration/**`.
- Commit de merge de branches na head da PR #15: `298c33949b4e2086e054d121ec0170eaedb5eff3`, com a base `395fd0c72a4cc96f105cf65616f1c84a281d934e` como segundo parent. Compare posterior confirma base como ancestral, `behind_by=0`.
- CI final da head antes da documentação: run `44438224828`, commit `d78fc2db04ea1e691e6bd1e1b94e15cf49d08a3f`: **249 testes OK** e `python -m compileall -q src tests` aprovado.
- Foi encontrada uma falha de segurança no desenho inicial: o painel usaria `SQLiteEventStore` padrão, cujo construtor executa inicialização/migração. Isso contrariava a promessa de leitura somente. Corrigido com `read_only=True`: exige arquivo existente, valida esquema, abre via URI `mode=ro`, não chama `_initialize()`, não cria tabelas/índices, não migra e não habilita WAL. Tentativas de escrita são recusadas pelo SQLite.
- `dashboard_http.main()` agora usa explicitamente o modo somente leitura. O script Termux valida previamente o banco; a proteção efetiva também existe no EventStore, mesmo se o comando for chamado diretamente.
- Painel local: loopback-only, token Bearer, métodos de mutação rejeitados, conteúdo dinâmico inserido via `textContent`, sem Helius/RPC, sem coleta, sem assinatura ou envio de transações.
- Testes novos cobrem banco ausente sem criação, consulta permitida, escrita negada e esquema incompleto sem migração. CI final inclui esses casos.

### Estado atual e próximo passo

- PR #15 ainda não foi mergeada; documentação desta seção e do modo read-only foi adicionada depois do CI de código. Aguardar CI documental se disparado, então marcar ready e integrar #15 à sua base `integration/pr13-sqlite-persistence`; validar CI no merge commit.
- Próxima dependência da cadeia: PR #16, somente após fechar #15.
- PR #25 continua OPEN/DRAFT; `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Progresso: módulo CPMM/SQLite/diagnóstico **95%**; revisão técnica **96%**. Não significa produto em produção: ainda não há serviço iniciado, banco real validado no Android, integração final na `main` nem execução financeira.



## 251. Sincronização do PR #16 e endurecimento fail-closed — 19/11/2026

- PR #15 foi integrada à branch-base intermediária por merge commit `4951eaf30b3da3b357213016a5eff65156cccd42`; CI do merge run `44438389847`: 249 testes e compileall aprovados.
- PR #16 continua OPEN/DRAFT. Sua base é `feat/reconciliation-diagnostics` (`116eddecd956a3e283828e485580292afe6b46d0`); head antes da sincronização `7da1e2574f1d72f2618cc3cf13e33407d22883f1`.
- CI do head funcional atualizado do PR #16, run `44438946997`, passou com **314 testes OK** e compileall.
- Revisão da fonte oficial fixada `MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e` confirmou o layout do evento `EvtSwap2`, os 14 accounts da instrução swap e a ordem dos parâmetros/campos usados pelo decoder.
- Correção fail-closed: associação DAMM v2 não é produzida quando `meta.err` está ausente; somente `meta.err = null` prova sucesso explícito.
- Correção no planejador histórico: `meta.err` ausente resulta em `EXECUTION_STATUS_UNKNOWN`, nunca `READY_FOR_REVIEW`; campos de carteira inválidos resultam em `WALLET_MAPPING_INVALID` e declarações conflitantes em `WALLET_MAPPING_CONFLICT`.
- Correção de privacidade/localidade: o inspetor estrutural agora rejeita manifestos e RAW por symlink e exige que os caminhos resolvidos permaneçam dentro do diretório autorizado. Testes cobrem symlink de manifesto e de payload.
- CI final após essas correções: run `44438946997`, commit `075abfa56a957cd01c25dc220b46b22361248170`, **314 testes OK**, compileall aprovado. A atualização documental subsequente não alterou código.
- A sincronização com PR #15 preserva no mesmo resultado a camada de diagnóstico/painel read-only e os novos artefatos DAMM v2. O CI da árvore combinada ainda precisa ser executado e aprovado antes de integrar PR #16.
- Nenhum reconciliador econômico DAMM v2 foi implementado: associação swap↔EvtSwap2 e atribuição de transferências são evidências estruturais; cobertura de quatro deltas não prova igualdade econômica. Token-2022, fees, referral e exclusividade por operação continuam exigindo validação.
- Nenhuma importação histórica, acesso RPC/Helius, gravação SQLite, checkpoint, assinatura ou execução on-chain foi realizada.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. PR #16 ainda não integrada; PR #25 continua OPEN/DRAFT.

## 252. CI da árvore combinada PR #16 + PR #15 — 19/11/2026

- Após a sincronização explícita da base `feat/reconciliation-diagnostics` com a head da PR #16, o compare passou a `ahead_by=134`, `behind_by=0`; GitHub reporta `mergeable=true`.
- Merge commit de sincronização na head PR #16: `cebb8c76812147fc2af67759a3871c48da52ab6d`, com a base `116eddecd956a3e283828e485580292afe6b46d0` como segundo parent.
- CI da árvore combinada: run `44439231241`, job `135275637353`, SUCCESS; log confirma **318 testes**, `OK`, e `python -m compileall -q src tests`.
- Esse CI valida conjuntamente os artefatos DAMM v2/offline do PR #16 com EventStore read-only, dashboard e diagnósticos do PR #15. Nenhuma importação histórica ou execução foi feita.
- PR #16 permanece OPEN/DRAFT até a conversão para ready e merge autorizado; a próxima validação será o CI do merge commit na branch-base `feat/reconciliation-diagnostics`.

## 253. CI do merge PR #16 concluído — 19/11/2026

- PR #16 CLOSED/MERGED na branch intermediária `feat/reconciliation-diagnostics`.
- Merge commit: `24ccb262b52bda0f20dac0db1b3e499156f9fc51`.
- CI do merge commit: run `44439364246`, job `135276068763`, SUCCESS; log confirma **318 testes**, `OK`, e `python -m compileall -q src tests`.
- A base DAMM v2 offline, o planejador histórico dry-run, os auditores redigidos e a camada de painel read-only foram validados em conjunto.
- Nenhuma reconciliação econômica, importação histórica, RPC, gravação, checkpoint ou execução financeira foi habilitada.
- Próxima etapa da cadeia: auditar PR #17 (matemática econômica/fees DAMM v2), sem presumir que os campos de evento já equivalem a quantidades reconciliadas.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.



## 254. PR #17 — validação de aritmética e sincronização pendente — 19/11/2026

- A fonte Token-2022 foi fixada em `solana-program/token-2022@875693f53c77534b46f0d06bdf781430870f8177`; Meteora permanece fixada em `MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e`.
- Correção conforme a fonte oficial: `get_excluded_fee_amount` permite taxa AMM de 100% e retorna líquido zero; `get_included_fee_amount` rejeita 100% porque a inversão divide por denominador zero. Teste dedicado cobre a assimetria.
- Teste adicional verifica minimalidade da inversão Token-2022 numa grade de basis points, maximum_fee e net amounts.
- CI do head PR #17 após essas correções: run `44439675835`, job `135277096545`, SUCCESS; **330 testes OK** e compileall aprovado.
- A PR #17 também reforça o fail-closed do Raydium CPMM: swap interno exige `cpi_path_valid=True`; swap externo continua escopado pelo grupo `innerInstructions` da instrução externa. Testes cobrem ambos.
- PR #17 permanece OPEN/DRAFT. A base `feat/offline-fixture-inspector` avançou 26 commits após a criação da branch; será incorporada por merge commit controlado e validada em CI combinado antes de integrar a PR.
- Aritmética pura validada não é reconciliação econômica: ainda faltam decodificação de estado histórico de mint/epoch, leitura de TransferFeeAmount, cálculo de PartialFill, atribuição exclusiva de referral/transferências e conciliação com deltas e EvtSwap2.
- Nenhum RAW, mint state, RPC, SQLite, checkpoint ou execução on-chain foi acessado/alterado por esta etapa. `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

## 255. CI combinado PR #17 + PR #16 aprovado — 19/11/2026

- A branch `feat/damm-v2-economic-fee-math` foi sincronizada com a base `feat/offline-fixture-inspector` por merge commit `adddfac41326cf7061cf0e80f734ffb4ae26fc96`, com a base `533dbf1ef95aba0099ab1cfe797dafc33eece2d2` como segundo parent.
- Compare da árvore sincronizada: `ahead_by=20`, `behind_by=0`; GitHub reporta `mergeable=true`.
- CI da árvore combinada: runs `44439855614` (push) e `44439847810` (PR), ambos SUCCESS. Os logs confirmam **339 testes OK** e `python -m compileall -q src tests`.
- Os testes incluem aritmética Token-2022/DAMM, caso de taxa AMM 100%, minimalidade do gross-up, correção de proveniência CPI do Raydium e toda a base offline/painel do PR #16.
- PR #17 pode sair de Draft e ser integrada à branch-base intermediária `feat/offline-fixture-inspector`; depois validar CI no merge commit.
- A integração não habilita decodificação histórica de mint/epoch, PartialFill, reconciliação econômica, importação, RPC, SQLite write, checkpoint ou execução.



## 256. PR #18 — decoder Token-2022 alinhado ao parser oficial e CI local — 19/11/2026

- PR #18 continua OPEN/DRAFT, base `feat/damm-v2-economic-fee-math`, head `feat/token2022-transfer-fee-state-decoder`.
- CI final do código do PR #18: run `44440551264`, job `135280013271`, SUCCESS; **351 testes OK** e `python -m compileall -q src tests` aprovado.
- Fonte oficial fixada: `solana-program/token-2022@875693f53c77534b46f0d06bdf781430870f8177`. Decoder agora valida o estado base Mint/TokenAccount, tags COption, estado Frozen, padding, colisão de tamanho Multisig 355, tipos TLV conhecidos 0–28 e limites/duplicações.
- Tipos TLV conhecidos não alvo são preservados em `extension_types`; tipos desconhecidos falham fechados. O chamador deve inspecionar essa lista e bloquear extensões fora do escopo, como taxas confidenciais ou hooks.
- A seleção de taxa continua exigindo epoch explícito; o decoder não consulta Clock, RPC ou estado atual. O owner do account não é validado pelo parser e precisa ser comprovado pelo chamador.
- O decoder não associa TransferFeeAmount a uma transferência, não reconcilia bruto/líquido/withheld por operação e não persiste dados.
- Próxima ação: incorporar a base atual do PR #17 à branch #18 por merge commit controlado; rodar CI combinado antes de retirar Draft ou integrar.
- Nenhum acesso RPC, SQLite, importação histórica, checkpoint, assinatura ou operação financeira. `main` continua em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

## 257. CI combinado PR #18 + PR #17 aprovado — 19/11/2026

- Branch `feat/token2022-transfer-fee-state-decoder` sincronizada com a base `feat/damm-v2-economic-fee-math` pelo merge commit `f79278c8c80dd9d13ec075021f29c6c174c094ea`; a base `caffd20bdec5472097b6beca4dc647c2e2e4280a` é ancestral do resultado.
- Compare: `ahead_by=33`, `behind_by=0`; GitHub informa `mergeable=true`.
- CI combinado: runs `44440708372` (push) e `44440714225` (PR), ambos SUCCESS; logs confirmam **361 testes OK** e `python -m compileall -q src tests`.
- O CI inclui o decoder de estado Token-2022 estrito e a base de aritmética DAMM v2/Token-2022, além do painel e diagnósticos read-only.
- PR #18 pode sair de Draft e ser integrada à base intermediária `feat/damm-v2-economic-fee-math`; depois validar o CI do merge commit.
- Limite mantido: decoder não valida owner on-chain, não escolhe epoch automaticamente, não associa withheld amount a transferência nem reconcilia economicamente.



## 258. PR #21 — TransferCheckedWithFee e semântica bruta/líquida — 19/11/2026

- PR #21 continua OPEN/DRAFT; base `feat/token2022-transfer-fee-state-decoder`, head `feat/token2022-transfer-checked-with-fee`.
- Fonte oficial Token-2022 fixada em `solana-program/token-2022@875693f53c77534b46f0d06bdf781430870f8177`: opcode 26 (`TransferFeeExtension`), subdiscriminador 1 (`TransferCheckedWithFee`), layout compilado de 19 bytes; contas source, mint, destination, authority.
- Decoder reconhece a variante somente sob Token-2022, preserva bruto e fee, rejeita fee maior que bruto, valores fora de u64 e mistura de formatos em accountKeys.
- Reconciliador Raydium valida que a taxa explícita pertence ao Token-2022; a origem é debitada pelo bruto e o destino recebe líquido (`gross - fee`), reconciliado com os deltas spendable.
- Foi corrigido o construtor de domínio: antes rejeitava saída líquida porque comparava com o bruto da instrução. Agora aceita a variante com taxa, revalida fee/programa, compara saída líquida e registra bruto, taxa, débito bruto e crédito líquido na evidência.
- CI do head funcional atualizado do PR #21: run `44441367861`, job `135282737800`, SUCCESS; **363 testes OK** e `python -m compileall -q src tests` aprovado. Commits posteriores foram somente documentação.
- DAMM v2 pode atribuir TransferCheckedWithFee por CPI, mas permanece `ATTRIBUTED` com revisão de fee obrigatória; não há MATCHED econômico. Não se deve promover essa atribuição a observação.
- Próxima ação: sincronizar PR #21 com o head atualizado do PR #18 por merge commit controlado e executar CI combinado antes de integrar.
- Nenhuma RPC/Helius, importação histórica, escrita SQLite, checkpoint ou execução financeira foi realizada. `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

## 259. CI combinado PR #21 + PR #18 aprovado — 19/11/2026

- Branch `feat/token2022-transfer-checked-with-fee` sincronizada com a base `feat/token2022-transfer-fee-state-decoder` por merge commit `635c7fb86af18cabd4375717672b5f20a30e9449`; a base `9f6896ad6a73bebf86d72cdda58cf53a2e351b08` é ancestral do resultado.
- Compare da árvore sincronizada: `ahead_by=21`, `behind_by=0`; GitHub informa `mergeable=true`.
- CI combinado: runs `44441569790` (push) e `44441576528` (PR), ambos SUCCESS; logs confirmam **380 testes OK** e `python -m compileall -q src tests`.
- Os testes validam parser raw/parsed, fee<=gross, Token-2022 exclusivo, reconciliação de deltas spendable, output líquido e construção de SwapDomainBundle com evidência bruta/fee/líquida.
- PR #21 pode sair de Draft e ser integrada à base intermediária `feat/token2022-transfer-fee-state-decoder`; depois validar CI no merge commit.
- A variante TransferCheckedWithFee não habilita por si só a reconciliação DAMM v2; nela permanece atribuição estrutural com revisão de taxa obrigatória.

## 260. Merge PR #21 e início da atribuição de referral DAMM v2 — 19/11/2026

- PR #21 CLOSED/MERGED na base intermediária `feat/token2022-transfer-fee-state-decoder`.
- Merge commit: `30ad85a374c7a35b07fda092c81e4978e5050aca`.
- CI do merge commit: run `44441714786`, job `135283892091`, SUCCESS; **380 testes OK** e compileall aprovado.
- A base TransferCheckedWithFee está integrada em branch intermediária; `main` permanece intacta.
- Próxima dependência: PR #22, atribuição da transferência de referral DAMM v2. Fonte oficial `ix_p_swap.rs` confirma que a transferência referral sai do vault determinado por `FeeMode`, usa `swap_result.referral_fee` como valor bruto e ocorre antes da emissão de `EvtSwap2`.
- Revisão atual adiciona validação de tipo, amount u64 positivo, programa Token-2022 obrigatório para TransferCheckedWithFee, fee não superior ao bruto e rejeição de fee em transferências comuns. O resultado continua somente `ATTRIBUTED`, sem reconciliação econômica.


## 261. PR #22 sincronizada com a base atual após resolução controlada do conflito — 19/11/2026

- A PR #22 tinha sido criada sobre o commit-base `62b3f54b717cf0e6675610b8b88bdfd8c542581d`. A branch-base avançou até `46dcf389d4cb06973a5d82967ba99fa3965121be`, causando `mergeable_state=dirty`.
- Auditoria dos blobs confirmou que `damm_v2_transfer_analyzer.py` e `tests/test_damm_v2_transfer_analyzer.py` na base atual permaneciam byte a byte iguais ao ponto de divergência `62b3f54`; a divergência material compartilhada estava no Registro Mestre.
- Resolução planejada: manter integralmente o Registro Mestre mais recente da base (seções 254–260), preservar as alterações funcionais/testes da PR #22 e seu documento técnico, e criar merge commit com a base atual como primeiro parent e o HEAD anterior da PR como segundo parent.
- Código funcional da PR #22 permanece limitado à atribuição estrutural de input/output/referral; status `ATTRIBUTED` não é reconciliação econômica nem BUY/SELL.
- CI previamente aprovado: run #1455 (`44443611154`), commit funcional/teste `97c38c9434bc2e5ff2a5a91390cb4b9709a12e76`, **365 testes OK** e compileall aprovado. Esse CI antecede a sincronização com a base atual; novo CI combinado é obrigatório.
- A sincronização não deve alterar `main`, não deve integrar a PR #22 e não habilita RPC/Helius, RAW, SQLite, importação, checkpoint ou execução on-chain.
- Próximo passo: verificar o merge commit, confirmar `mergeable=true` e aguardar CI completo no novo HEAD antes de qualquer revisão final.


## 262. CI combinado após sincronização da PR #22 — 19/11/2026

- Merge commit de sincronização: `5bdcbfe6d1fb1c166c1eb5d609e239c61559cd5a`; primeiro parent é a base atual `46dcf389d4cb06973a5d82967ba99fa3965121be`, segundo parent é o HEAD anterior da PR #22 `9528618d7fb83b475a0a7f447c21ded620442844`.
- O Registro Mestre da base (seções 254–260) foi preservado integralmente e recebeu esta sequência de continuidade; os arquivos funcionais/testes e documento técnico da PR #22 foram reaplicados sobre a base atual.
- Compare da árvore: `ahead_by=15`, `behind_by=0`; GitHub reporta `mergeable=true`, `mergeable_state=clean`.
- CI combinado #1456 (`44444094172`) no HEAD `5bdcbfe6d1fb1c166c1eb5d609e239c61559cd5a`: **completed/success**. Suíte completa: **393 testes OK**; `python -m compileall -q src tests` aprovado.
- A PR #22 continua aberta e Draft; nenhum merge da PR foi realizado. `main` continua em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- O resultado comprova compatibilidade de código/testes com a base intermediária atual, mas não valida transações RAW mainnet nem reconciliação econômica DAMM v2. `ATTRIBUTED` permanece evidência estrutural, nunca `MATCHED`.
- Nenhuma operação RPC/Helius, leitura/escrita de RAW, SQLite, importação, checkpoint ou operação on-chain foi realizada.
- Próxima ação: revisão final dos invariantes e dos limites semânticos de referral antes de decidir se a PR pode sair de Draft.


## 263. Auditoria estática final da atribuição referral PR #22 — 19/11/2026

- A matriz `resolve_damm_fee_mode` seleciona token A apenas para `BOTH_TOKEN + B_TO_A`; nos demais modos/direções suportados, seleciona token B. Isso corresponde ao mapeamento FeeMode documentado para `BOTH_TOKEN`, `ONLY_B` e `COMPOUNDING`.
- A seleção da transferência exige mesma instrução externa, descendência CPI demonstrável, posição anterior ao EvtSwap2, origem no vault do token de cobrança e destino na referral token account.
- A validação posterior confere programa Token, mint, presença de decimals, tipo suportado, amount bruto positivo u64, coerência de `TransferCheckedWithFee`/fee explícita e igualdade do bruto com `EvtSwap2.swap_result.referral_fee`.
- A unicidade é verificada por papel e globalmente entre operações; duplicidade ou reutilização não é promovida a `ATTRIBUTED`.
- Casos ausentes, ambíguos, malformados, não executados ou inconsistentes permanecem fail-closed. O teste temporal pós-EvtSwap2 foi aprovado no CI.
- Limite semântico identificado e mantido explícito: o módulo exige `decimals` presente, mas não consulta o mint para comparar o número de casas decimais. Para transferências executadas, a validação de decimals é imposta pelo programa Token no processamento on-chain; a camada atual não decodifica estado do mint nem prova epoch. Essa prova pertence à reconciliação com estado histórico, não deve ser inferida da atribuição isolada.
- CI combinado #1456 no merge commit sincronizado: **393 testes OK** e compileall aprovado. O commit posterior `2fa5ed8856e48d7e474547fdaec10100dd57f10d` alterou somente este Registro Mestre.
- Resultado da auditoria: nenhum bloqueio estrutural adicional identificado dentro do escopo de atribuição; permanecem as limitações econômicas já declaradas. Isso não equivale a auditoria de transações RAW mainnet nem a aprovação para execução financeira.
- PR #22 permanece OPEN/DRAFT, mergeable/clean; não integrada. `main` permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Próxima etapa técnica após decisão de revisão: especificar reconciliação econômica por operação usando EvtSwap2, transfers input/output/referral, fees explícitas/implícitas, withheld histórico e deltas por conta/vault, sem dividir arbitrariamente deltas agregados entre swaps sequenciais.


## 264. Retomada e sincronização da PR #23 com a PR #22 atual — 19/11/2026

- PR #23 já continha a implementação de reconciliação em lote no módulo `damm_v2_economic_reconciliation.py`, com testes e documento próprios; não foi recriada.
- HEAD anterior da PR #23: `947c056e01bfc7b22037e19e3600a5248a29e281`; CI #588 (`44308645725`) no mesmo HEAD concluiu SUCCESS: **374 testes OK** e compileall aprovado. Validação local Termux registrada em `d6142ba37c55aae45f9756b9adec2e2be3520895`: 374/374 e compileall.
- A PR #23 estava baseada em `b350dca26a5bf0729f58b0770f07b85f5375b9e4`, enquanto a PR #22 avançou para `0567eb9c4981ba6ffc33e98a402292130667760a`; GitHub reportou PR #23 `mergeable_state=dirty`, 68 commits atrás.
- Sincronização controlada: usar o commit atual da base PR #22 como primeiro parent e o HEAD anterior da PR #23 como segundo parent; preservar integralmente a árvore atual da PR #22 e reaplicar somente os quatro arquivos próprios da PR #23 (módulo, testes, documento e Registro Mestre atualizado). Dependências compartilhadas são mantidas da base atual, não das cópias antigas da PR #23.
- Arquivos de dependência comparados antes da sincronização: `damm_v2_transfer_analyzer.py`, `damm_v2_fee_math.py`, `solana_token_transfer_decoder.py` e `damm_v2_analyzer.py` tinham diferenças entre a base atual e a branch antiga da PR #23; `solana_token_balance_delta_decoder.py`, `damm_v2_decoder.py` e `damm_v2_accounts.py` tinham blobs idênticos. As versões atuais da PR #22 são preservadas.
- A CI #588 valida o HEAD antigo da PR #23, não a combinação sincronizada. Novo CI obrigatório antes de qualquer aprovação.
- Limites permanecem: `RECONCILED` verifica transferências atribuídas e deltas agregados base por token account, mas não valida ainda snapshots históricos de withheld TransferFeeAmount, epoch/config histórico do mint nem todos os componentes de reserva/fee AMM. Não cria SwapObservation, BUY/SELL ou execução.
- Nenhuma alteração em `main`, RAW, SQLite, checkpoints, RPC/Helius ou estado on-chain.
- Próxima ação: validar o merge commit sincronizado e revisar os invariantes adicionais de ownership e reservas DAMM v2 antes de retirar Draft.


## 265. PR #23 sincronizada e CI combinado aprovado — 19/11/2026

- Sincronização da PR #23 com a base atual da PR #22 concluída no merge commit `232c11ac2f8b9a754446e10a3d74ec7dbc8c8688`; primeiro parent `0567eb9c4981ba6ffc33e98a402292130667760a`, segundo parent `947c056e01bfc7b22037e19e3600a5248a29e281`.
- A árvore da base PR #22 foi preservada integralmente; reaplicados somente os quatro arquivos próprios da PR #23: reconciliador, testes, documento e Registro Mestre.
- Compare após sincronização: 25 commits à frente, 0 atrás; quatro arquivos próprios. GitHub reportou `mergeable=true`, `mergeable_state=clean`.
- CI #1460 (`44445124525`) no HEAD sincronizado `232c11ac2f8b9a754446e10a3d74ec7dbc8c8688`: **408 testes OK**, compileall aprovado, workflow completed/success.
- A validação local anterior no Termux permanece registrada: 374 testes aprovados e compileall no commit `d6142ba37c55aae45f9756b9adec2e2be3520895`. A validação mais recente e combinada é o CI #1460.
- PR #23 continua Draft e não integrada; PR #22 continua Draft e não integrada; `main` intacta.

## 266. Ownership explícito e trilha de withheld fees na PR #23 — 19/11/2026

- `reconcile_damm_v2_economic_batch` agora exige `monitored_wallet`; owner das token accounts input/output deve ser a carteira monitorada e owner dos vaults A/B deve ser `pool_authority`. `payer` não é usado como proxy de owner econômico.
- Colisão entre as quatro contas principais (input user, input vault, output vault, output user) falha fechado; referral ativa não pode colidir com outra conta do swap.
- Transferências atribuídas para reconciliação devem ser `TRANSFER_CHECKED` ou `TRANSFER_CHECKED_WITH_FEE`, com amount bruto estritamente positivo. Isso corresponde ao caminho de transferência checked esperado no escopo.
- O resultado expõe `expected_withheld_fee_deltas`, agregados por conta destino e mint, derivados de bruto menos crédito spendable. `withheld_fee_status` distingue `NOT_REQUIRED` de `EXPECTED_NOT_VERIFIED`.
- Limite explícito: withheld esperado ainda não é prova do TLV `TransferFeeAmount.withheld_amount` pre/post. O estado histórico do mint, epoch aplicável e o delta TLV da conta ainda precisam ser obtidos e verificados; o estado atual do mint não pode substituir prestate histórico.
- Testes novos cobrem owner de carteira, owner dos vaults, withheld esperado não verificado e carteira monitorada ausente.
- Commits desta atualização: reconciliador `0c51441c6022ba6668d89bee78ea7af0e5ad4b85`; testes `24866016f041ac558af8a4d471a0aad6d2153be8` e `2a809c06451c485db87ea54d24afddea1182fed5`; documento `503fd0a825f9c16f3219d1e009c299a307b366fa`.
- CI #1460 valida o HEAD anterior à atualização de ownership/withheld. Novo CI é obrigatório para o HEAD final desta seção.
- Nenhuma alteração em `main`, RAW, SQLite, checkpoints, RPC/Helius ou estado on-chain.
- Próxima ação: executar CI no HEAD final e revisar eventuais falhas; depois planejar a camada histórica de mint/epoch e TLV withheld.


## 267. CI final da PR #23 após ownership/withheld e descrição atualizada — 19/11/2026

- CI #1466 (`44445338461`) no commit de código/testes `2a809c06451c485db87ea54d24afddea1182fed5`: completed/success, **412 testes OK**, compileall aprovado.
- CI #1468 (`44445369964`) no commit documental `503fd0a825f9c16f3219d1e009c299a307b366fa`: completed/success, **412 testes OK**, compileall aprovado.
- A seção 266 e o commit `67feff6c6949ebfa3481b944ef9ed304f25c58e3` alteraram somente o Registro Mestre; nenhum código/teste mudou depois do commit funcional validado. A descrição da PR #23 foi atualizada para refletir a sincronização, os 412 testes e os limites de withheld.
- PR #23 continua OPEN/DRAFT, mergeable/clean; compare contra o HEAD atual da PR #22: 30 commits à frente, 0 atrás, quatro arquivos próprios. PR #22 continua Draft. `main` permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- O estado `RECONCILED` deve ser lido como reconciliação dos deltas base pre/post e transferências atribuídas. Os valores withheld esperados são expostos, mas o estado TLV histórico ainda não foi observado; epoch/config histórica do mint e withheld pre/post continuam pendentes.
- Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain foi realizada.
- Próxima etapa: desenhar e implementar a camada de prova histórica de TransferFeeConfig/epoch e TransferFeeAmount pre/post, sem usar estado atual como substituto histórico.


## 268. Decoder TLV de withheld pre/post e CI 416/416 — 19/11/2026

- Criado `TransferFeeAmountDelta` e `decode_transfer_fee_amount_delta(pre_account_data, post_account_data)` em `token2022_transfer_fee_state.py`.
- O decoder lê o TLV `TransferFeeAmount` nos dois lados, exige a extensão presente em ambos e conjunto de extensões estável, e retorna `pre_withheld_amount`, `post_withheld_amount` e delta assinado. Delta negativo é permitido para capturar harvest; extensão ausente não vira zero.
- Testes novos cobrem aumento, redução/harvest, mudança no conjunto de extensões e extensão ausente.
- Limite: o decoder valida estrutura dos bytes, não prova que os snapshots correspondem ao instante imediatamente anterior/posterior à transação. Assinatura, slot, ordenação e proveniência precisam vir do coletor; `getTransaction.pre/postTokenBalances` não contém o TLV withheld.
- Commits: decoder `bfdfc01c4333ea267ec96c10153b8d2ef61ae358`; testes `be1695ec8896855aa1748ad19c59fa3848d25ac2`; documentação `bc8623e5cdae0d1292d1cf22b8da07a1a7842aa7`.
- CI #1473 (`44445631405`) e #1474 (`44445639117`) no HEAD de código/testes `be1695ec8896855aa1748ad19c59fa3848d25ac2`: completed/success, **416 testes OK**, compileall aprovado.
- Commit documental `bc8623e5cdae0d1292d1cf22b8da07a1a7842aa7` e atualização desta seção não alteram código/testes após o CI aprovado.
- Descrição da PR #23 atualizada para incluir ownership, withheld esperado, decoder TLV e limites de proveniência.
- PR #23 permanece OPEN/DRAFT, mergeable/clean, sem merge; PR #22 permanece Draft; `main` continua `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima ação: desenhar o contrato de snapshots TLV com assinatura/slot/ordem verificáveis e integrá-lo ao resultado da reconciliação, sem confundir bytes válidos com proveniência histórica comprovada.


## 269. Verificação de withheld vinculada à transação — 19/11/2026

- Adicionado `DammV2WithheldFeeSnapshot` e `verify_damm_v2_withheld_fee_deltas` ao módulo de reconciliação econômica.
- O verifier exige que a reconciliação base esteja `RECONCILED`, recebe snapshots TLV decodificados e exige correspondência de token account/mint, assinatura, slot e ordem da transação.
- Exige `pre_snapshot_order < transaction_order < post_snapshot_order` no mesmo domínio de ordenação, refs pre/post distintos e fonte identificada. Os valores TLV precisam vir de `TransferFeeAmountDelta` produzido pelo decoder.
- Compara o delta observado `post_withheld - pre_withheld` com `expected_withheld_fee_deltas`. Correspondência integral resulta em `withheld_fee_status=VERIFIED`; ausência/divergência resulta em `INCOMPLETE`; snapshots duplicados resultam em `AMBIGUOUS`.
- Testes usam bytes TLV de conta decodificados pelo `decode_transfer_fee_amount_delta`, e cobrem correspondência, divergência, snapshot ausente, assinatura errada, ordem temporal inválida e duplicidade.
- Commits: verifier `277d1e3e9ddf3d2955d5ad9d830df6e64b56bd2c`; endurecimento de metadados `8891627bf164ee175fb7a2bb1190b4e82c93dc1b`; testes `eaec0c945c3e21942cffcdd8301a3c957357c622` e `934bc0f20b78fa189e67b1a08ebb11074f846739`; documentação `0f72ecbcadb93856c07dffe5afa1debabb9b8d0c`.
- CI #1487 (`44445935062`) e #1488 (`44445941647`) no HEAD funcional `8891627bf164ee175fb7a2bb1190b4e82c93dc1b`: completed/success, **422 testes OK**, compileall aprovado.
- Limite de proveniência: os refs/ordem são contrato do coletor, não prova criptográfica automática. Nenhum adapter real de arquivo histórico/Geyser foi conectado nesta etapa. A configuração histórica do mint/epoch também permanece pendente.
- PR #23 continua OPEN/DRAFT, mergeable/clean, sem merge; PR #22 Draft; `main` intacta.
- Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima etapa: definir a fonte de dados real que consegue fornecer snapshots account-data exatos e ordenados em torno da transação, e ligar esse adapter ao verifier sem aceitar `getAccountInfo` atual como estado histórico.


## 270. Verificação histórica de TransferFeeConfig/epoch por transferência — 19/11/2026

- Adicionado `decode_transfer_fee_config_optional(mint_data)`: valida mint base e TLV e retorna `None` quando TransferFeeConfig não existe; `decode_transfer_fee_config` permanece estrito e lança erro quando ausente.
- Cada transferência Token-2022 reconciliada agora gera `DammV2ExpectedTransferFee` com identidade outer/inner, mint, bruto e taxa esperada derivada do líquido confirmado pelo evento/TransferCheckedWithFee.
- Criado `DammV2MintFeeConfigSnapshot` e `verify_damm_v2_mint_fee_config`: exige snapshot por transferência específica, mesma identidade de mint/instrução, epoch/slot/ordem, prestate anterior e confirmação do adapter de que o mint não mudou antes da transferência dentro da transação.
- Com TransferFeeConfig presente, seleciona older/newer fee pelo epoch fornecido e recalcula a taxa com `calculate_transfer_fee` (arredondamento ceil e cap). Sem extensão, a taxa calculada é zero.
- `mint_fee_config_status=VERIFIED` só quando todas as transferências Token-2022 do lote conferem. O verifier não deriva epoch do slot; o adapter precisa fornecer epoch historicamente correto.
- Referral Token-2022 por TransferChecked padrão continua fail-closed na reconciliação base, pois o líquido ainda precisa ser calculado com a configuração histórica antes de agregar os deltas; isso permanece próximo trabalho.
- Testes novos cobrem extensão ausente/presente, configuração divergente, snapshot faltante/duplicado, prestate que não antecede a transação, mudança de mint antes da transferência e seleção older/newer por epoch.
- Commits: decoder opcional `fe00a88a57b5a5a3b71dab142e268efb8551dced`; testes decoder `0f8a2f446a27bd89fed3179c4b47c77dfc8ced7a`; verifier inicial `8ff00ddfe9aa1423242f4f52ac7cf808c90c4daa`; validação estrita `7bb619375c6817788b821db9d57728cac977c8d8`; testes `892fab8a6a84d30188be2ccbb2fef56c2324be51` e `e5b2c43f5607fbe9083eb38c77363de72ae90e87`; documentação `2337d74a559ea33c3a0004d6493cc662dd20c014`.
- CI #1503 (`44446452613`) e #1504 (`44446458291`) no HEAD funcional/teste `e5b2c43f5607fbe9083eb38c77363de72ae90e87`: completed/success, **431 testes OK**, compileall aprovado.
- CI #1505 (`44446566545`) no HEAD `2337d74a559ea33c3a0004d6493cc662dd20c014`: completed/success, **431 testes OK**, compileall aprovado.
- PR #23 permanece OPEN/DRAFT, sem merge; PR #22 permanece Draft; `main` intacta. Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima ação: usar a configuração histórica validada para calcular o crédito líquido da referral Token-2022 padrão e só então fechar os deltas agregados por conta.


## 271. Referral Token-2022 TransferChecked padrão com mint prestate — 19/11/2026

- A reconciliação base agora recebe opcionalmente `mint_fee_snapshots`, `transaction_epoch`, `transaction_slot` e `transaction_order`.
- Para referral Token-2022 em `TRANSFER_CHECKED` padrão (fee implícita no payload), exige exatamente um snapshot de mint para a identidade outer/inner e mint da transferência.
- Calcula fee com `TransferFeeConfig` prestate e epoch, deriva `referral_net = gross - fee`, agrega o crédito líquido da referral account e inclui a transferência em `expected_transfer_fees` e `expected_withheld_fee_deltas`.
- Cada `DammV2ExpectedTransferFee` agora declara a origem do fee: `EVT_SWAP2_NET`, `TRANSFER_CHECKED_WITH_FEE` ou `MINT_PRESTATE`.
- `verify_damm_v2_mint_fee_config` continua revalidando todos os snapshots por transferência, inclusive input/output/referral; o adapter deve garantir que o mint não mudou antes da instrução. Sem snapshot ou com identidade/proveniência inválida, fail-closed.
- Teste integrado: input Token-2022 fee 5, output gross 90/net 81 fee 9 e referral gross 5/net 4 fee 1; deltas agregados dos vaults e token accounts conferem, e as três taxas passam pela validação do mint prestate/epoch.
- Teste adicional confirma que referral Token-2022 padrão sem snapshot histórico não é reconciliada.
- Commits: cálculo referral `4e9ec1a82faf32cba2e1c3bb999e84bdd29cb000`; validação estrita `e512bbc850a00ecbca263197c9b74ec2d8ac667c`; testes `3cb04506dcaf36dc9d58911cfbd67c97874faf35`; ajuste de asserção `1c0c038360b662d64f3884507bc3461d097c8772`; documentação `9062a882e5714551daf9ec1473f5fff378eaeb2a`.
- CI #1514 (`44446949702`) e #1515 (`44446955433`) no HEAD `1c0c038360b662d64f3884507bc3461d097c8772`: completed/success, **433 testes OK**, compileall aprovado.
- CI #1507–#1512 falharam apenas porque um teste ainda esperava a mensagem antiga de fail-closed; a asserção foi atualizada. A implementação de referral foi aprovada no CI #1514/#1515.
- Limite restante: `mint_state_unchanged_before_transfer` é atualmente declaração do adapter; falta decodificar completamente instruções de alteração de TransferFeeConfig para produzir essa prova automaticamente. Fonte/adapter de snapshots históricos também não está conectado.
- PR #23 continua OPEN/DRAFT, sem merge; PR #22 Draft; `main` intacta. Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima ação: substituir a declaração booleana de estabilidade do mint por inventário verificável de instruções de alteração de TransferFeeConfig, com posições antes/depois da transferência.


## 272. Inventário explícito de inicialização de TransferFeeConfig — 19/11/2026

- Adicionado `TransferFeeConfigMutationInstruction` e `decode_transfer_fee_config_mutation_instruction` no decoder Token-2022.
- O decoder reconhece prefixo externo `TransferFeeExtension=26`, subtag `0=InitializeTransferFeeConfig` e `5=SetTransferFee`; valida COption, tamanho, basis points e maximum fee.
- `DammV2MintFeeConfigSnapshot` substitui `mint_state_unchanged_before_transfer` por `transfer_fee_config_init_positions` e `transfer_fee_init_inventory_complete`.
- O cálculo/verifier exige inventário completo das posições de inicialização para aquele mint e rejeita qualquer `InitializeTransferFeeConfig` anterior ou na mesma posição da transferência.
- `SetTransferFee` não invalida o fee do epoch corrente: no código Token-2022 fixado, agenda a nova taxa para `current_epoch + 2` e preserva a taxa ativa anterior em `older_transfer_fee`. A taxa efetiva segue `fee_for_epoch(transaction_epoch)`.
- O inventário ainda é fornecido pelo adapter; o scanner de instruções externas/CPI que resolve o mint e popula as posições ainda não foi implementado.
- Commits: decoder mutation `c001ca24c723b5038738666ce024b9d193267bfb`; testes decoder `b164b0f14e87b8e822c7827add495ad4db74dbf1`; substituição da flag `1028cceb7ad35a58b66e6bfbd9a868c6e12eb834`; testes `531a2dc9a98ee7c82bb269796d58c3a048c0ec84` e `b51411a8fba50a8cdbf94cad67d15c6ecefbdf30`; documentação `4d444bff357adb579716b3241bb6fedf2f0394a3`.
- CI #1525 (`44447328127`) e #1526 no HEAD de testes `b51411a8fba50a8cdbf94cad67d15c6ecefbdf30`: completed/success, **440 testes OK**, compileall aprovado.
- CI #1527 (`44447361606`) no HEAD `4d444bff357adb579716b3241bb6fedf2f0394a3`: completed/success, **440 testes OK**, compileall aprovado.
- PR #23 permanece OPEN/DRAFT, mergeable/clean, sem merge; PR #22 Draft; `main` intacta. Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima ação: implementar scanner de instruções Token-2022 externas e CPI, mapear account index do mint e gerar automaticamente o inventário completo de inicialização por mint.


## 273. Scanner de instruções externas/CPI para inicialização de TransferFeeConfig — 19/11/2026

- Adicionado `SolanaInstructionRecord`, `SolanaInstructionInventory` e `decode_solana_instruction_inventory(raw_transaction)` ao decoder de instruções Solana.
- O inventário resolve program IDs e contas de instruções externas e inner/CPI, preserva posição outer/inner, dados compilados ou parsed type e registra stackHeight/CPI path.
- Falha fechado se `meta.innerInstructions` estiver ausente, a transação falhar, programId/account index não puder ser resolvido ou dados Token-2022 relevantes estiverem ausentes/inválidos.
- Adicionado `TransferFeeConfigInitInventory` e `collect_transfer_fee_config_init_positions(inventory, mint)`: filtra Token-2022 com a primeira conta igual ao mint, reconhece `InitializeTransferFeeConfig` 26/0 e retorna posições `(outer, inner)`; `-1` representa instrução externa.
- `SetTransferFee` 26/5 é validada, mas não adicionada como inicialização; sub-tags desconhecidas da extensão causam inventário incompleto. A saída fornece diretamente posições e flag de completude para o snapshot de mint.
- Testes cobrem instruções externas e CPI, mint distinto, SetTransferFee, parsed initialize, lista interna ausente, subtag desconhecida, init malformada e transação falha.
- Commits: inventory decoder `53d93545cd781427a69e1ec068ef8a2774c4304b`; testes scanner `5c82ea891582d046551ca2e7262c2bc7ba0b3ce4`; rejeição de transação falha `ba82ef52499087c1fab376133b08ec6fba628f49`; teste de falha `7057c5611a20e122c7b3bfbe6ed0491ee87151e9`; documentação `4240c070c928a09243abf2721bdb0a9fd09786bc`.
- CI #1537 (`44447770956`) e #1538 no HEAD funcional/teste `7057c5611a20e122c7b3bfbe6ed0491ee87151e9`: completed/success, **448 testes OK**, compileall aprovado.
- CI #1539 (`44447862941`) no HEAD `4240c070c928a09243abf2721bdb0a9fd09786bc`: completed/success, **448 testes OK**, compileall aprovado.
- A saída do scanner ainda não foi conectada automaticamente ao adapter que monta `DammV2MintFeeConfigSnapshot`; o coletor também ainda não fornece snapshots históricos de mint/account em produção.
- PR #23 permanece OPEN/DRAFT, mergeable, sem merge; PR #22 Draft; `main` intacta. Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima ação: criar um construtor/adapter que receba o inventário, a saída por mint, o epoch/slot e os snapshots prestate e gere `DammV2MintFeeConfigSnapshot` com proveniência verificável, sem aceitar dados atuais como históricos.


## 274. Construtor de snapshots históricos de mint por transferência — 19/11/2026

- Adicionado `DammV2MintPrestate` e `build_damm_v2_mint_fee_config_snapshots(evidence, mint_prestate_by_mint, instruction_inventory, ...)`.
- O construtor percorre as evidências input/output/referral e cria um `DammV2MintFeeConfigSnapshot` por transferência Token-2022 (outer/inner/mint), incluindo assinatura da transação, slot, epoch, ordem, config state, posições de inicialização, fonte e state ref.
- Exige que `SolanaInstructionInventory.transaction_signature/slot` correspondam exatamente à transação alvo e que o inventário esteja completo.
- Exige bytes prestate de mint do mesmo slot, ordem anterior à transação e fonte/state ref não vazios; decodifica `TransferFeeConfig` opcionalmente e gera posições de init via `collect_transfer_fee_config_init_positions`.
- A assinatura da transação foi adicionada também ao `DammV2MintFeeConfigSnapshot`, ao builder, à reconciliação de referral Token-2022 padrão e ao verifier, evitando misturar snapshot de outra transação.
- O construtor conecta scanner + decoder + evidências, mas ainda não busca snapshots históricos por conta própria. O adapter de origem histórica (bytes prestate de mint e TLV de token account) continua pendente; `getAccountInfo` atual não é aceito como histórico.
- Commits: builder inicial `faa121a8742a7de191b8ab7ebf603d667bf5ad47`; assinatura/inventory binding `ec0831c27d7f7021f9b721c90387ba382d4401b1`; fixtures `b80a7a71d540cee4ebbe9122dcfe4164e658fb88`; builder tests `a6c43e885f741b02b009ec58027796877704bbd0`; correção de asserção `25c7f8253a42bb1b6b74c06cceebe7b788b45807`; documentação `762f91ce60b5542da91776562c8b5865c18df5ab`.
- CI #1555 (`44448400017`) e #1556 no HEAD `25c7f8253a42bb1b6b74c06cceebe7b788b45807`: completed/success, **451 testes OK**, compileall aprovado.
- CI #1557 (`44448535055`) no HEAD documental atual `762f91ce60b5542da91776562c8b5865c18df5ab`: completed/success, **451 testes OK**, compileall aprovado.
- PR #23 continua OPEN/DRAFT, mergeable, sem merge; PR #22 Draft; `main` intacta. Nenhuma RPC/Helius, RAW, SQLite, checkpoint, importação ou operação on-chain.
- Próxima ação: conectar uma fonte histórica que forneça bytes de mint e token account no estado exato pre/post da transação, e construir os objetos `DammV2MintPrestate` e `DammV2WithheldFeeSnapshot` com proveniência verificável.


## 275. Pesquisa da fonte de snapshots históricos e arquitetura de coleta — 19/11/2026

- Fontes oficiais/documentação consultadas: Solana RPC JSON Structures/Indexing; Helius LaserStream/Preprocessed Transactions; Yellowstone Geyser `geyser.proto`.
- Yellowstone `SubscribeUpdateAccountInfo` expõe `data`, `write_version` e `txn_signature` opcional; `SubscribeUpdateAccount` expõe slot. Esses campos permitem vincular um post-state à assinatura e ordenar atualizações da mesma conta.
- Helius LaserStream é compatível com Yellowstone e oferece replay recente/reconexão. A documentação indica que em `processed` account updates chegam em ordem do validator e podem existir múltiplas atualizações da mesma conta no slot; em `confirmed`, assinantes recebem apenas estado final. Logo, capturar pre/post exige observar `processed` e depois confirmar a assinatura em commitment superior.
- Preprocessed Transactions oferece transação assinada/slot/instruções antes da execução, mas não contém meta, inner instructions/CPI, balances ou resultado. Serve como alerta antecipado, nunca como prova econômica.
- RPC `getAccountInfo` consulta estado atual no slot de contexto; `getTransaction` contém pre/post token balances, mas não o TLV bruto `TransferFeeAmount` de cada token account. `getTransactionsForAddress` é opção de backfill de transações, não substituto de account-state history.
- Arquitetura candidata: timeline por pubkey com account updates `processed` contendo bytes, slot, write_version e txn_signature; parear o update associado à assinatura com o estado imediatamente anterior da mesma conta; armazenar refs/hash; confirmar/finalizar e descartar forks revertidos.
- Helius LaserStream é candidato técnico, não foi contratado/conectado; a página oficial indica disponibilidade em planos Business ou superiores. Manter adapter provider-neutral e validar preço/limites antes de contratação.
- Limite de código atual: `DammV2MintPrestate` e `DammV2WithheldFeeSnapshot` são contratos tipados; o construtor ainda depende de bytes prestate fornecidos por um adapter externo. Não existe coletor LaserStream/Geyser operacional.
- Próxima ação: implementar normalizador provider-neutral de `GeyserAccountUpdate` e timeline/pairer por pubkey/write_version/txn_signature, com testes de startup baseline, lacunas/replay, updates múltiplos no mesmo slot e rollback antes de conectar um provider.


## 276. Fonte candidata de snapshots e validação documental CI — 19/11/2026

- Pesquisa confirmou que o schema Yellowstone Geyser `SubscribeUpdateAccountInfo` fornece `data`, `write_version` e `txn_signature` opcional, enquanto `SubscribeUpdateAccount` fornece `slot`. LaserStream declara compatibilidade com Yellowstone.
- Helius documenta que account updates em `processed` chegam na ordem do validator e podem conter várias atualizações da mesma conta no slot; em `confirmed`, a assinatura de conta recebe somente o estado final. Portanto, snapshots pre/post exigem captura `processed` e confirmação posterior da transação.
- Preprocessed Transactions entrega a mensagem assinada antes da execução, mas não inclui meta, CPI/inner instructions, balances nem resultado. Não é fonte de reconciliação.
- Solana RPC `getAccountInfo` é leitura do estado no slot de contexto; `getTransaction` fornece pre/post token balances, não o TLV bruto withheld de token accounts. Helius `getTransactionsForAddress` é útil para backfill de transações, não para estado bruto histórico de contas.
- Arquitetura recomendada: timeline persistente por pubkey, armazenando bytes, slot, write_version, txn_signature e stream sequence; parear update com assinatura-alvo ao último estado anterior da mesma conta; confirmar/finalizar e descartar forks revertidos. LaserStream replay recente auxilia recuperação, mas persistência própria é obrigatória.
- Helius LaserStream permanece candidato, não contratado/conectado. A disponibilidade anunciada é Business ou superior; manter adapter provider-neutral.
- Documentação atualizada no commit `803aec1307436db9f39dcad321122eceacb467ba`; CI #1559 (`44448848178`) no mesmo HEAD: completed/success, **451 testes OK**, compileall aprovado.
- Este trabalho foi apenas pesquisa documental e atualização do Registro Mestre; nenhuma credencial, RPC, Helius, RAW, SQLite ou operação on-chain foi usada.
- Próxima ação: implementar normalizador provider-neutral de mensagens Geyser e timeline/pairer por pubkey/write_version/txn_signature, incluindo startup baseline, lacunas/replay, múltiplos updates no mesmo slot e rollback.


## 277. CI final da pesquisa de snapshots e estado atual da PR23 — 19/11/2026

- PR #23 HEAD: `e80c9179eb8c0587a47d0cb4425c5171449b0358`; base `feat/damm-v2-referral-transfer-attribution`.
- CI #1561 (`44448957990`) no HEAD atual: completed/success, **451 testes OK**, compileall aprovado.
- PR #23 permanece OPEN/DRAFT, `mergeable=true`, `mergeable_state=clean`; não integrada. PR #22 continua Draft.
- Compare da PR #23: 85 commits à frente, 0 atrás, oito arquivos próprios. `main` permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Nenhum código/teste foi alterado após a validação #1561; as atualizações finais são apenas descrição da PR/registro.
- Nenhuma RPC/Helius, RAW, SQLite, importação, checkpoint ou operação on-chain foi executada.
- Próxima etapa de implementação: normalizador de account updates Yellowstone/Geyser e timeline por pubkey, usando `write_version`, `txn_signature`, slot e stream sequence; parear pre/post, preservar startup baseline e detectar lacunas/replay/rollback antes de qualquer reconciliação real.


## 278. CI final da cadeia de snapshots históricos — 19/11/2026

- HEAD funcional/documental da PR #23 após sincronização de continuidade: `ee95cd298a1704391b3b62245dbf4fc410eefe64`.
- CI #1562 (`44449119065`) e CI #1563 (`44449252412`) no HEAD validado: completed/success, **451 testes OK**, compileall aprovado.
- O último ajuste após CI #1561 foi documental; nenhum código/teste mudou após a suíte de 451 testes.
- PR #23 continua OPEN/DRAFT, `mergeable=true`, `mergeable_state=clean`, sem merge; PR #22 permanece Draft.
- `main` continua `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Próxima implementação definida: normalizador provider-neutral de Yellowstone/Geyser account updates e timeline por pubkey, preservando slot, write_version, txn_signature e stream sequence; construir pareamento pre/post, startup baseline, recuperação de lacunas/replay e descarte de forks antes de conectar Helius ou outro provider.


## 279. Implementação inicial da timeline histórica Geyser — 19/11/2026

- CI #1567 (run `44454181573`) validou o normalizador provider-neutral de account updates: **464 testes OK** e `compileall` aprovado.
- Na branch `feat/damm-v2-economic-reconciliation`, foram adicionados:
  - `src/smart_money_radar/data_sources/geyser_account_timeline.py`: timeline em memória por pubkey; ordenação ledger por `(slot, write_version)`; separação de transporte por `stream_id/stream_sequence`; deduplicação; conflitos de identidade; detecção de gaps/reconexão; pareamento conservador pre/post; rollback explícito com preservação de updates órfãos.
  - `tests/test_geyser_account_timeline.py`: 12 testes para ordenação, replay, colisões, gaps, reconexão, assinatura ausente, rollback e independência entre contas.
  - `docs/GEYSER-ACCOUNT-TIMELINE.md`: contrato, semântica e limitações.
- CI #1571 (run `44455090010`) no commit de testes: completed/success, **476 testes OK**, compileall aprovado.
- CI #1572 (run `44455118052`) no HEAD documental `5bd3e7f91c693dbb37563db7d874702675bd8ad1`: completed/success, **476 testes OK**, compileall aprovado.
- Commits: timeline `68d4533b5fdc5f69004577b64536fdaff7ac0405`; testes `e3000d0d727625dc71debf54fdc6d851b1824041`; documentação `5bd3e7f91c693dbb37563db7d874702675bd8ad1`.
- PR #23 continua OPEN/DRAFT, mergeable e sem merge; base `feat/damm-v2-referral-transfer-attribution`. `main` continua em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Limites importantes: timeline somente em memória; sem adapter protobuf Yellowstone oficial; sem commitment/blockhash/parent slot/fork identity; rollback é entrada explícita de um tracker externo, não detecção automática. Nenhuma conexão RPC/Helius, RAW, SQLite ou operação on-chain foi executada.
- Próxima etapa: revisar o contrato do adapter Yellowstone com o schema oficial e definir como transportar commitment, blockhash/parent slot e sinais de rollback/replay sem confundir write_version com ordenação de instruções. Depois disso, desenhar baseline/backfill persistente antes de qualquer integração de provider. Não conectar serviço pago nem alterar SQLite/RAW sem autorização.


## 280. Revisão do schema oficial Yellowstone — 19/11/2026

- Revisada a definição oficial `yellowstone-grpc-proto/proto/geyser.proto` do projeto rpcpool/yellowstone-grpc: https://github.com/rpcpool/yellowstone-grpc/blob/master/yellowstone-grpc-proto/proto/geyser.proto.
- Além de `slot`, `write_version` e `txn_signature`, `SubscribeUpdateAccount` contém `is_startup` e `bank_id` opcional; `SubscribeUpdateSlot` contém `parent`, `status`, `dead_error` e `bank_id` opcional. O enum `SlotStatus` inclui `SLOT_DEAD` e `SLOT_CREATED_BANK`.
- O schema atual também define `SubscribeUpdateEntryUpdateParent`, que invalida dados do `cleared_bank_id` e informa `parent_slot`/ `parent_block_id`; a atualização `SLOT_CREATED_BANK` informa o banco substituto. `SubscribeUpdateBlock` fornece `blockhash`, `parent_slot` e `parent_blockhash`.
- Implicação: rollback apenas por limiar de slot é insuficiente para distinguir forks/branches. A timeline implementada continua conservadora e só executa rollback quando recebe sinal externo explícito; ainda não resolve bank lineage automaticamente.
- Próxima etapa de arquitetura: estender o envelope canônico para preservar `is_startup` e `bank_id`; normalizar slot lifecycle e invalidações de bank; associar account updates a block/bank lineage sem usar `write_version` como índice de instrução ou assumir canonicalidade por ordem de chegada. Só depois habilitar pareamento entre bancos distintos quando a relação pai/filho estiver demonstrada.
- Nenhum código foi alterado nesta revisão documental; sem adapter protobuf, RPC/Helius, RAW ou SQLite.


## 281. Identidade de bancos Yellowstone e linhagem de forks — 19/11/2026

### Implementado na branch da PR23
- `NormalizedAccountUpdate` agora preserva `bank_id` opcional e `is_startup`; startup com bank_id é rejeitado. O fingerprint inclui source, bank_id e is_startup.
- `ordering_key` é somente `(slot, write_version)`; `stream_sequence` não é usada como desempate da ordem do ledger.
- Novo módulo `src/smart_money_radar/data_sources/geyser_bank_lineage.py`:
  - normalizadores provider-neutral para `SubscribeUpdateSlot`, `SubscribeUpdateBlockMeta` e `SubscribeUpdateEntryUpdateParent`;
  - identidade do banco `(source_id, slot, bank_id)`; source_id é namespace estável entre reconexões e stream_id representa apenas transporte;
  - `SLOT_CREATED_BANK` exige bank_id; FIRST_SHRED_RECEIVED/COMPLETED podem ficar sem banco;
  - `SLOT_DEAD` com bank_id invalida aquele banco específico; sem bank_id invalida os bancos conhecidos e futuros do source/slot;
  - `EntryUpdateParent` invalida o `cleared_bank_id`, preserva `parent_block_id` como bytes opacos e liga o banco substituto ao próximo CREATED_BANK apenas se houver exatamente um candidato;
  - `parent_slot` isolado não escolhe fork. Link pai/filho só é estabelecido com correspondência exata `(parent_slot, parent_blockhash)` de block metadata;
  - blockhashes ou parent metadata incompatíveis e substituições ambíguas viram conflitos sem mutação parcial;
  - `is_ancestor` retorna None para linhagem incompleta; só retorna False quando a cadeia observada chega à raiz conhecida (slot 0).
- A timeline linear falha fechada: não gera pre/post para account updates com bank_id ou startup, e não expõe um único current_state quando o histórico inclui bancos/forks ou apenas startup.
- Testes novos em `tests/test_geyser_bank_lineage.py`, além da cobertura de account normalizer e timeline.
- Contrato documentado em `docs/GEYSER-ACCOUNT-TIMELINE.md`.

### Validação comprovada
- CI #1609 — run `44455853310`, HEAD `06f41fe054ce2b51d5c804e431a84ed1f056d1b4`: **495/495 testes OK**, `compileall` aprovado; job completed/success.
- CI #1608 — push para o mesmo HEAD: completed/success.
- O CI #1584/#1583 falhou em uma expectativa de teste de ancestralidade incompleta; a regra foi corrigida para retornar None, e execuções posteriores passaram. O CI #1597 também capturou a mudança de assinatura de ordering_key antes da atualização do teste; corrigido no commit subsequente e validado. Não ocultar essas falhas históricas; os commits posteriores aprovados são a referência.

### Estado do repositório
- PR #23: OPEN, Draft, mergeable, sem merge; head `06f41fe054ce2b51d5c804e431a84ed1f056d1b4`; base `feat/damm-v2-referral-transfer-attribution`.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; nenhuma alteração ou merge em main.
- PR #22 continua separada. Nenhum serviço Geyser/Helius conectado; sem adapter protobuf oficial; sem RAW/SQLite/persistência e sem operações on-chain.
- Schema de referência: rpcpool/yellowstone-grpc `yellowstone-grpc-proto/proto/geyser.proto`, consultado em 19/11/2026.

### Próxima etapa
Implementar adapter de fronteira para mensagens protobuf Yellowstone (ou mapping testável equivalente) que converta os campos binários pubkey/owner/signature e os eventos de slot/block/entry-parent para os contratos normalizados. Fixar a versão/schema de protocolo em fixtures; testar mensagens reais serializadas/deserializadas e replay/reconnect. Ainda não conectar endpoint nem habilitar captura contínua. Depois, integrar BankLineageTracker à timeline para reconstruir pre/post somente dentro da cadeia de bancos verificada; só então desenhar backfill e persistência.


## 282. Fechamento e endurecimento da camada de forks — 19/11/2026

- Ajustes finais após revisão dos testes:
  - `rollback_from_slot` agora rejeita histórico que contenha `bank_id`; rollback amplo por slot poderia apagar bancos concorrentes.
  - `current_state` não retorna um estado único para histórico fork-scoped nem para snapshot startup ainda não sucedido por estado observável.
  - `is_ancestor` retorna `None` para cadeia incompleta ou banco não observado; só retorna `False` quando a cadeia alcança a raiz conhecida no slot 0.
  - Conflitos em substituição ambígua, parent_slot ou blockhash não deixam criação parcial de nós.
  - Testes cobrem a rejeição de rollback por slot em histórico com bank_id e startup não promovido.
- CI final da camada: #1615, run `44455986697`, HEAD de código/documentação `0c662e00c8161a708eda7e5fbf40ac2a96b6783e`: **496/496 testes OK**, `compileall` aprovado, job completed/success.
- CI #1614 (run `44455975278`) também passou em 496/496 no commit imediatamente anterior, antes da atualização documental final.
- PR #23 permanece OPEN/DRAFT, sem merge, mergeable; head na atualização deste registro: `0c662e00c8161a708eda7e5fbf40ac2a96b6783e`; base `feat/damm-v2-referral-transfer-attribution`.
- `main` permanece intacta em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Próxima ação aprovada pelo plano: implementar adapter de fronteira para protobuf Yellowstone com fixtures versionadas e mensagens binárias reais; não conectar endpoint, não persistir RAW/SQLite e não usar a timeline para decisões financeiras. Depois, integrar o tracker de bancos à reconstrução de pre/post com testes de forks concorrentes.


## 283. Adapter de fronteira Yellowstone protobuf — 19/11/2026

### Implementação preparada na branch da PR23
- Novo `src/smart_money_radar/data_sources/geyser_proto_adapter.py`: converte mensagens protobuf decodificadas para os contratos provider-neutral existentes.
- Eventos suportados no dispatcher `SubscribeUpdate.update_oneof`: Account, Slot, BlockMeta e EntryUpdateParent. Ping/pong, transactions, block e entry comum ficam fora do escopo deste adapter.
- Account: valida pubkey/owner com 32 bytes e assinatura opcional com 64 bytes; converte essas identidades binárias para Base58; preserva `data` como bytes; transporta `slot`, `write_version`, `bank_id`, `is_startup` e ausência de `txn_signature`.
- Slot: mapeia enum numérico SlotStatus e preserva parent, bank_id e dead_error opcionais.
- BlockMeta: preserva blockhash, parent_slot, parent_blockhash e bank_id.
- EntryUpdateParent: preserva parent_block_id como bytes opacos.
- source_id estável, stream_id de conexão e stream_sequence são fornecidos pelo chamador; o adapter não inventa ordem nem faz reconnect/replay.
- Dependência protobuf adicionada para desserialização e testes wire-level.

### Schema e fixtures versionados
- Schema fixado em rpcpool/yellowstone-grpc tag `v16.1.5+solana.4.3.2`, arquivo `yellowstone-grpc-proto/proto/geyser.proto`, Git blob SHA `d0f96616d515c978a07b16e6409c7706f4429a5a`.
- Manifesto: `tests/fixtures/yellowstone/v16.1.5+solana.4.3.2/manifest.json`.
- Fixtures protobuf serializadas/desserializadas cobrem account update, startup, SLOT_CREATED_BANK, SLOT_DEAD, BlockMeta e EntryUpdateParent; hashes SHA-256 são verificados no teste.
- O descriptor de teste é um subconjunto wire-compatible com os field numbers, enum values e wire types do schema fixado. O adapter de produção recebe os objetos gerados pelo cliente Yellowstone, sem importar o descriptor de teste.

### Limites preservados
- Sem endpoint Yellowstone/Geyser, cliente gRPC, captura contínua, reconnect/replay automático, RAW/SQLite, backfill ou operações on-chain.
- Sem promoção de commitment/canonicalidade. Sem integração do BankLineageTracker à timeline; pareamento pre/post bank-aware continua bloqueado até essa integração e testes de forks concorrentes.


## 284. Validação do adapter protobuf Yellowstone — 19/11/2026

- CI #1617, run `44456501557`, no commit de implementação `060f922ccd6b3852e4415f62227d0c983b16c81d`: completed/success; **502/502 testes OK** em 4,064 s; `compileall -q src tests` concluído com sucesso.
- O CI #1618 (evento pull_request) foi iniciado para o mesmo HEAD; a validação de referência já aprovada é o CI #1617 de push no mesmo SHA.
- PR #23 permanece OPEN/DRAFT, `merged=false`, `mergeable=true`; HEAD de implementação `060f922ccd6b3852e4415f62227d0c983b16c81d`, base `feat/damm-v2-referral-transfer-attribution`.
- `main` permanece intacta em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; nenhuma integração/merge foi feita.
- Próxima etapa: integrar `BankLineageTracker` à timeline com reconstrução pre/post condicionada à relação pai/filho de bancos verificada; cobrir forks concorrentes, updates fora de ordem, replay/reconnect e rollback exato. Ainda sem endpoint Geyser, captura contínua ou persistência RAW/SQLite.


## 285. Integração BankLineageTracker com AccountUpdateTimeline — 19/11/2026

### Implementação na branch da PR23
- `AccountUpdateTimeline` agora recebe um `BankLineageTracker` injetável e cria um tracker próprio por padrão.
- Adicionados métodos de ingestão `add_slot_update`, `add_block_meta` e `add_entry_update_parent`, encaminhando eventos normalizados ao tracker.
- `transition_for(signature)` mantém o comportamento linear antigo somente quando ambos os eventos não têm bank_id. Não mistura estados com/sem bank_id.
- Para eventos bank-scoped, exige bancos observados e utilizáveis; pares no mesmo banco usam a identidade exata (source, slot, bank_id); pares entre bancos exigem `is_ancestor(pre_bank, post_bank) == True`, estabelecido por correspondência exata de parent_slot + parent_blockhash.
- Seleciona o estado anterior mais recente na cadeia verificada, respeitando slot/write_version; empate na chave ledger não escolhe arbitrariamente.
- Dead bank, cleared bank e ancestrais conhecidos invalidados não podem contribuir para transições. Histórico permanece para auditoria; não é apagado.
- Eventos de metadados podem chegar após account updates; o pareamento é reavaliado dinamicamente quando `transition_for` é chamado.
- Adicionada `BankLineageTracker.is_bank_usable`; `is_ancestor` agora falha fechado quando encontra banco morto/inválido, ciclo ou cadeia incompleta.
- Testes novos em `tests/test_geyser_bank_aware_timeline.py`: mesma bank, cadeia cross-bank comprovada, forks irmãos, parent_slot sem blockhash, EntryUpdateParent, ancestral morto, metadados fora de ordem, reconexão e replay.

### Validação
- Validação final registrada na seção 286: CI #1633/#1634, 515/515 testes e compileall aprovados no commit funcional `d5b21774e8210096dc5c41e842c3c2d0a9434054`.

### Limites
- Não há endpoint Yellowstone conectado, captura contínua, replay/reconnect de rede, persistência RAW/SQLite, backfill ou operações on-chain.
- Não há promoção de commitment nem seleção de fork canônico. Transição é evidência de estados observados em banco/linhagem verificados, não decisão de compra/venda.

### Próxima etapa
Concluída na seção 286: invalidação de descendants, updates fora de ordem, replay/reconnect e rollback exato foram implementados e testados. A próxima frente é o contrato de persistência/backfill.


## 286. Validação final da integração bank-aware e proteção de forks — 19/11/2026

### Estado final do código
- Commit funcional validado: `d5b21774e8210096dc5c41e842c3c2d0a9434054` (código e testes). Commit HEAD atual da branch: `a09a18c834c5cea0ff7920d55c56e0a57a51d862` (somente documentação/Registro após a validação de código).
- `AccountUpdateTimeline` integra o `BankLineageTracker` por padrão ou por injeção; recebe Slot, BlockMeta e EntryUpdateParent através de métodos explícitos.
- Transição bank-scoped exige banco pre e post observado/utilizável, mesma fonte estável e:
  - identidade exata do mesmo banco; ou
  - cadeia ancestral verificada por parent_slot + parent_blockhash exatos.
- A seleção do pre-state escolhe a escrita anterior mais recente na cadeia verificada; não escolhe entre candidatos empatados.
- Forks irmãos, parent_slot sem blockhash, bancos mortos, bancos limpos por EntryUpdateParent e descendants ligados a ancestrais mortos/invalidados não geram transição.
- Histórico invalidado permanece disponível para auditoria; nenhuma exclusão física nem rollback global por slot é usada para histórico com bank_id.
- Account writes fora de ordem podem ser reconciliados após ordenação por (slot, write_version), desde que cheguem na mesma continuity epoch e a linhagem prove a relação.
- Gap/reconnect cria continuity baseline. Um update ancestral atrasado não atravessa essa fronteira; a reconstrução só retoma a partir do novo baseline.
- Testes adicionados em `tests/test_geyser_bank_aware_timeline.py`, cobrindo same-bank, cross-bank, forks irmãos, parent metadata incompleta, EntryUpdateParent, SLOT_DEAD, ancestor invalidation, late metadata, account updates fora de ordem, replay, reconnect, gap e rollback exato.

### Validação CI comprovada
- CI #1633 — run `44457364018`, push no HEAD funcional: completed/success; **515/515 testes OK** em 4,058 s; `python -m compileall -q src tests` aprovado.
- CI #1634 — run `44457372356`, pull_request no mesmo HEAD: completed/success; **515/515 testes OK** em 4,107 s; compileall aprovado.
- CI intermediário #1621/#1622 encontrou dois problemas nas fixtures de teste (replay com estado alterado e write_version repetido no reconnect); as fixtures foram corrigidas. As execuções #1625–#1634 passaram; os dois últimos runs acima validam o HEAD final.

### Estado GitHub e segurança
- PR #23: OPEN, Draft, `merged=false`; HEAD atual `a09a18c834c5cea0ff7920d55c56e0a57a51d862`; base `feat/damm-v2-referral-transfer-attribution`. O código/testes validados estão no pai `d5b21774e8210096dc5c41e842c3c2d0a9434054`; o commit HEAD seguinte alterou apenas docs/Registro.
- `main` intacta: `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Nenhum merge.
- Nenhum endpoint Yellowstone/Helius conectado; sem captura contínua, reconnect/replay de rede, RAW/SQLite, backfill ou execução on-chain/financeira.

### Próxima etapa
Desenhar o contrato de persistência histórica e backfill (RAW imutável + timeline derivada), incluindo chaves de idempotência, checkpoints por source/stream, retenção de eventos órfãos e reconstrução após reinício. Antes de qualquer conexão real, revisar como o adapter de transporte fornecerá stream_sequence e eventos de reconnect/discard-bank. Nenhum provider pago deve ser contratado/conectado sem autorização.


## 287. Contrato documental de persistência histórica Geyser e backfill — 19/11/2026

### Estado da entrega
- Criado `docs/GEYSER-PERSISTENCE-BACKFILL.md` na branch `feat/damm-v2-economic-reconciliation`.
- Commit do documento técnico: `b03711063f59727f9402c1037545ec7fa3cf9a90`.
- Esta entrega é exclusivamente especificação/documentação. Nenhum schema SQLite, migração, classe de persistência, cliente gRPC, captura contínua, checkpoint durável ou backfill foi implementado.

### Contrato registrado
- Três camadas: RAW imutável, eventos normalizados provider-neutral e timeline/projeções reconstruíveis.
- Banco dedicado proposto: `smr_geyser.sqlite`, separado de `smr_events.sqlite`; EventStore e checkpoints de carteira existentes permanecem inalterados.
- RAW e deliveries separados: conteúdo identificado independentemente de stream/sequence; cada replay/entrega mantém proveniência própria.
- Proveniência de bytes explícita: o adapter atual recebe protobuf decodificado; bytes wire só podem ser declarados quando capturados antes da decodificação. Representações reconstruídas devem ser rotuladas corretamente.
- Projeções persistentes propostas para eventos normalizados, account writes, bank events, gerações da timeline e eventos órfãos/invalidados.
- Três checkpoints independentes: transporte por (source_id, stream_id), continuidade comprovada por epoch e progresso/cobertura do backfill.
- Gap não pode ser pulado: evento posterior é preservado, lacuna registrada, checkpoint contíguo não avança e continuidade fica interrompida até recuperação comprovada.
- Backfill separado da captura viva, com cobertura COMPLETE/PARTIAL/UNKNOWN; estado atual de conta não substitui histórico de account writes.
- Atomicidade de RAW, delivery, normalização, conflitos/gaps e checkpoint de transporte; checkpoint só avança após commit durável.
- Reconstrução determinística/versionada, preservação de forks/órfãos, backup/restore testado e sem retenção automática inicial.
- Sequência de implementação e critérios de aceitação documentados, incluindo crash injection, replay, conflitos, reconnect, overlap live/backfill e falhas de reconstrução.

### Confirmação do estado GitHub antes da documentação
- Consulta direta da PR #23 confirmou: OPEN, Draft, merged=false, mergeable=true.
- Base: `feat/damm-v2-referral-transfer-attribution`.
- HEAD confirmado antes desta entrega: `135af1caefe406e3fedbab765ef65706b244a165`.
- A comparação entre `a09a18c834c5cea0ff7920d55c56e0a57a51d862` e `135af1caefe406e3fedbab765ef65706b244a165` confirmou 1 commit à frente e 0 atrás; a única alteração desse commit foi o Registro Mestre.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; nenhuma alteração ou merge em main.
- O commit funcional de código/testes continua `d5b21774e8210096dc5c41e842c3c2d0a9434054`; CI #1633/#1634: 515/515 testes e compileall aprovados nesse commit.

### Próxima etapa
Revisar o contrato documental e, em etapa separada, iniciar apenas os contratos de schema/migração e testes de persistência offline. Não conectar provider, não contratar infraestrutura, não implementar backfill real e não alterar a main sem autorização explícita.


## 288. Primeira implementação offline de persistência RAW Geyser — 19/11/2026

### Escopo executado
- Implementação restrita à branch `feat/damm-v2-economic-reconciliation`, PR #23.
- Criado `src/smart_money_radar/storage/geyser_raw_store.py`.
- Criado `tests/test_geyser_raw_store.py`.
- Atualizado `docs/GEYSER-PERSISTENCE-BACKFILL.md` para separar o que está implementado das próximas camadas ainda pendentes.

### Implementação comprovada no código
- `SQLiteGeyserRawStore` usa banco dedicado informado pelo chamador; não altera nem reutiliza `SQLiteEventStore` ou checkpoints de carteira.
- Migração versionada v1 cria `geyser_raw_events`, `geyser_raw_deliveries`, `geyser_raw_conflicts` e `geyser_schema_migrations`, com índices para fonte/tipo, stream/sequence, evento e conflito.
- Arquivo SQLite usa WAL e `synchronous=FULL`; modo `:memory:` é suportado para testes offline.
- Evento RAW é separado de cada entrega. Replay de conteúdo idêntico cria nova delivery e mantém um único RAW.
- Reutilização de `event_id` com source, tipo, schema, encoding ou bytes incompatíveis preserva o RAW original e registra conflito com hash e bytes recebidos, além de registrar a delivery conflitante.
- SHA-256 é calculado sobre os bytes exatos recebidos. O storage não serializa protobuf nem declara origem wire por conta própria.
- Inserção RAW nova + delivery ocorre na mesma transação. Teste com trigger que força falha ao inserir delivery confirma rollback do RAW.
- A identidade estável `event_id` ainda é fornecida pelo chamador; derivação determinística por tipo de evento não foi implementada.

### Commits da implementação
- `1d29fc6` — módulo inicial de persistência RAW.
- `79d5a88` — testes de RAW, replay, conflitos, reabertura e validação.
- `e7714bb` — migração de schema tornada explicitamente atômica.
- `92ba36d494e23932d11ec4b7c25ffd9afebe2916` — teste de rollback transacional; HEAD funcional validado.
- `7bdb07a5379e8c552af8e7f6e3ca40800aed10dc` — atualização documental de status e validação.

### Validação CI comprovada
- CI #1645 — run `44462300540`, evento push, commit `92ba36d494e23932d11ec4b7c25ffd9afebe2916`: completed/success; **522/522 testes OK** em 4,033 s; `python -m compileall -q src tests` aprovado.
- CI #1646 — run `44462306301`, evento pull_request, mesmo commit: completed/success; **522/522 testes OK**; compileall aprovado.
- O CI valida o código/testes no commit `92ba36d...`; commits posteriores alteraram somente documentação.

### Estado GitHub e limites
- PR #23 permanece OPEN, Draft, `merged=false`, base `feat/damm-v2-referral-transfer-attribution`.
- Nenhuma alteração ou merge na `main`.
- Nenhum cliente gRPC, captura wire, conexão Yellowstone/Helius, credencial, VPS, captura contínua, checkpoint de transporte/continuidade, gap recovery, timeline persistida ou backfill foi implementado.
- Não há autorização de execução financeira ou operação on-chain.

### Próxima etapa técnica
Revisar e formalizar derivação de identidade por tipo de evento; depois implementar checkpoints de transporte e gaps com transação atômica, sem conectar provider. Só após essa camada devem entrar persistência normalizada e reconstrução da timeline.


## 289. Checkpoints de transporte Geyser e gaps persistentes — 19/11/2026

### Escopo implementado
- Continuação da seção 288, exclusivamente na branch `feat/damm-v2-economic-reconciliation`, PR #23.
- Evoluída a migração do banco Geyser para schema v2 em `src/smart_money_radar/storage/geyser_raw_store.py`.
- Adicionadas tabelas `geyser_transport_checkpoints`, `geyser_transport_gaps` e `geyser_transport_anomalies`.
- Mantido o banco dedicado; nenhum checkpoint de carteira do `SQLiteEventStore` foi reutilizado.

### Semântica comprovada
- Checkpoint por `(source_id, stream_id)`, separado de identidade RAW e de ledger order.
- `register_stream(source_id, stream_id, initial_sequence)` permite declarar o primeiro número esperado antes da ingestão.
- Se a stream não for registrada previamente, o primeiro sequence observado vira baseline `first_observed_unverified`; isso não prova cobertura de sequência anterior.
- `contiguous_sequence` só avança através de deliveries persistidas sem lacunas. Sequence posterior é preservado, gap é registrado e checkpoint contíguo não salta o intervalo.
- Eventos fora de ordem podem preencher gaps. Registros substituídos e resolvidos permanecem auditáveis.
- Replay do mesmo evento na mesma sequence não cria colisão. Evento diferente reutilizando sequence, conflito de identidade RAW não identificável ou sequence anterior ao baseline declarado gera anomalia aberta e interrompe checkpoint.
- Anomalias exigem resolução explícita com nota. Resolver uma anomalia não remove interrupção enquanto houver gap ou outra anomalia aberta.
- RAW, delivery, gap/anomalia e atualização do checkpoint são atômicos na mesma transação SQLite. Teste com trigger de falha na inserção do gap prova rollback conjunto.
- Reconnect deve usar novo `stream_id`; semântica de reset de sequence não é inferida.

### Testes e CI
- Adicionados testes de checkpoints, baseline, sequência fora de ordem, fechamento de gaps, replay, colisão, resolução de anomalia, rollback atômico e upgrade de schema v1 para v2.
- CI #1660 — run `44508678117`, push, commit `b470a5eb02025512569d83d667d82ddc55a33ec5`: completed/success; **530/530 testes OK** em 3,839 s; `python -m compileall -q src tests` aprovado.
- CI #1661 — run `44508689458`, pull_request, mesmo commit: completed/success; **530/530 testes OK** em 4,090 s; compileall aprovado.
- Teste adicional comprova migração de banco existente v1 para v2.
- CI #1664 — run `44508979168`, push, commit `5d66bd1b50559ed9f4ede06461c2b4cf0ac9cf9b`: completed/success; **531/531 testes OK** em 3,834 s; compileall aprovado.
- CI #1665 — run `44508987457`, pull_request, mesmo commit: completed/success; **531/531 testes OK** em 3,954 s; compileall aprovado.
- Runs #1654–#1659 tiveram falha apenas na asserção do texto esperado para registro tardio de baseline; mensagem/validação foi corrigida e os runs finais passaram.

### Commits desta etapa
- `99a6773` — schema v2 e primeira implementação de checkpoint/gap.
- `d4d4f06` — correção crítica para impedir avanço do checkpoint através de gap aberto.
- `32cf299` — testes de checkpoints, gaps, replay e rollback.
- `a72d782` — conflitos RAW passam a interromper transporte.
- `be8b20e` — cobertura de conflito de identidade RAW.
- `b470a5eb02025512569d83d667d82ddc55a33ec5` — correção do registro tardio de baseline; CI 530/530.
- `5d66bd1b50559ed9f4ede06461c2b4cf0ac9cf9b` — teste de upgrade v1→v2; HEAD funcional validado por CI 531/531.
- `f1f9dec33d7abd05fa598d7da665bb2f0b936478` — atualização inicial do contrato técnico.
- `73f47b4c8c4edd5b48b18c36499c41be425c1255` — documentação final da migração e CI 531/531.

### Limites e estado GitHub
- PR #23 permanece OPEN, Draft, sem merge, base `feat/damm-v2-referral-transfer-attribution`.
- Nenhuma alteração na `main`; nenhuma conexão Geyser/Helius, credencial, VPS, captura contínua ou operação on-chain/financeira.
- Não implementados: identidade determinística automática de evento, checkpoint de continuidade/epoch, persistência normalizada, account writes, timeline persistente, backfill e recuperação de reinício.

### Próxima etapa técnica
Formalizar a derivação determinística de `event_id` por tipo de evento e versão do schema, com tratamento de colisão e compatibilidade. Depois, em etapa separada, implementar persistência de eventos normalizados. Não conectar provider.


## 290. Identidade determinística versionada para eventos Geyser — 19/11/2026

### Escopo implementado
- Implementação offline na branch `feat/damm-v2-economic-reconciliation`, PR #23.
- Criado `src/smart_money_radar/data_sources/geyser_event_identity.py`.
- Criado `tests/test_geyser_event_identity.py`.
- Contrato versionado `IDENTITY_VERSION = "geyser-event-id:v1"`; API `derive_event_identity(event, schema_version=...)`.

### Chaves lógicas por tipo
- Account: source_id, pubkey, slot, write_version, bank_id e is_startup.
- Slot: source_id, slot, status e bank_id.
- BlockMeta: source_id, slot e bank_id.
- EntryUpdateParent: source_id, slot e cleared_bank_id.
- `stream_id` e `stream_sequence` são excluídos da identidade; pertencem à delivery.
- A versão explícita do schema upstream e a versão do contrato de identidade entram no JSON canônico antes do SHA-256.
- Campos de conteúdo excluídos da chave (por exemplo account data, parent hashes, parent_block_id, parent_slot e dead_error) não são descartados: permanecem protegidos pela comparação de bytes/hash do RAW store. Reutilizar o mesmo event_id com payload diferente deve resultar em conflito preservando o RAW original.
- A identidade é de evento normalizado provider-neutral. Não é identidade byte-for-byte do protobuf wire; o adapter atual recebe mensagens decodificadas.

### Testes adicionados
- Determinismo entre streams/reconnects e alterações de stream_sequence.
- Independência de campos de conteúdo que devem gerar conflito no RAW, em vez de novo evento.
- Separação por schema version, tipo de evento, slot/write_version/bank.
- Rejeição de tipo não suportado e schema_version vazio.
- Integração de teste com `SQLiteGeyserRawStore`: mesmo event_id + bytes alterados gera conflito e mantém payload original imutável.

### Limites
- Atualização pela seção 291: o helper agora é chamado pelo coordenador offline `data_sources/geyser_ingestion.py`; ainda não está acoplado automaticamente ao adapter protobuf nem a um worker de transporte.
- Atualização pela seção 291: conteúdo normalizado já é arquivado como `normalized_json` no RAW store. Ainda faltam projeções/tabelas normalizadas dedicadas, timeline persistente, continuidade/epoch e backfill.
- Sem endpoint/cliente Yellowstone/Helius, captura wire, credenciais, VPS, operação on-chain ou execução financeira.
- PR #23 continua Draft e sem merge; `main` permanece intocada.

### Validação
- CI #1674 — run `44510167848`, evento pull_request, HEAD `bde85727630b4f37994852c67594a9c70887d1a3`: completed/success; **539/539 testes OK** em 3,843 s; `python -m compileall -q src tests` aprovado.

### Próxima etapa
Integrar o helper ao contrato de ingestão RAW sem acoplar identidade a transporte; depois implementar persistência normalizada com versionamento e diagnósticos. Não conectar provider.


## 291. Coordenador offline de ingestão normalizada para RAW Geyser — 19/11/2026

### Escopo implementado
- Criado `src/smart_money_radar/data_sources/geyser_ingestion.py`.
- Criado `tests/test_geyser_ingestion.py`.
- API pública: `ingest_normalized_event(store, event, schema_version=..., delivery_kind=...)`.
- Suporta os quatro contratos provider-neutral existentes: Account, Slot, BlockMeta e EntryUpdateParent.
- Deriva `event_id` por `derive_event_identity`, serializa conteúdo normalizado em JSON canônico UTF-8 e persiste via `SQLiteGeyserRawStore` com `payload_encoding=normalized_json`.
- Account data é codificado em Base64 sem perda; parent_block_id opaco é codificado em hexadecimal. Não são bytes originais protobuf.
- `stream_id` e `stream_sequence` aparecem apenas em `RawDeliveryInput`; não entram na identidade lógica nem no payload normalizado.
- Replay em outra stream mantém o mesmo event_id e adiciona delivery; alteração do conteúdo sob a mesma identidade vira conflito RAW imutável.
- Versão do schema upstream altera o event_id e permanece registrada no payload.
- O coordenador não altera o adapter protobuf, não cria cliente gRPC e não conecta provider.

### Testes específicos adicionados
- Persistência de JSON canônico e separação de delivery.
- Replay entre reconnects com deduplicação RAW.
- Conflito quando conteúdo muda sob mesma identidade.
- Cobertura de Slot, BlockMeta e EntryUpdateParent.
- Isolamento por versão de schema.
- CI #1686 — run `44515088642`, pull_request, código HEAD `0beb6c26f2ac6833cb7ebff5861d208c2a1c307b`: completed/success; **544/544 testes OK** em 4,035 s; `python -m compileall -q src tests` aprovado.
- Runs #1680 e #1684 falharam em asserções dos testes recém-criados (contrato de retorno de conflito e representação Base64); expectativas corrigidas antes do CI aprovado #1686.

### Limites
- Este é um coordenador offline chamado explicitamente pelo consumidor; não há loop/worker de stream nem conexão Yellowstone/Helius.
- A camada normalizada agora é serializada e arquivada no RAW store como normalized_json; ainda não há projeções/tabelas normalizadas dedicadas, account-write index, timeline persistente, backfill ou recuperação de reinício.
- Nenhum wire-byte capture; dados recebidos já decodificados não podem ser rotulados como protobuf_wire.
- PR #23 permanece Draft e sem merge; main intocada.

### Próxima etapa
Construir projeções normalizadas dedicadas e versionadas (começando por account writes), mantendo RAW como fonte imutável e permitindo reconstrução. Não conectar provider.


## 292. Projeção persistente e reconstruível de Geyser account writes — 19/11/2026

### Entrega
- Implementado na branch `feat/damm-v2-economic-reconciliation`, PR #23.
- Arquivos:
  - `src/smart_money_radar/storage/geyser_account_write_projection.py`
  - `tests/test_geyser_account_write_projection.py`
- Classe `SQLiteGeyserAccountWriteProjection`; APIs `rebuild()`, `get_checkpoint()`, `list_writes()`.
- A projeção compartilha o banco Geyser dedicado, sem tocar no EventStore de transações.
- Lê apenas RAW `account` em `normalized_json`; não finge decodificar wire bytes.
- Preserva a identidade do RAW e campos de conta/ledger; dados binários permanecem reversíveis via Base64 e são acompanhados de tamanho e SHA-256.
- Checkpoint próprio/versionado e geração de rebuild, independente do checkpoint de transporte.
- Rebuild integral em uma transação: substitui projeção e checkpoint juntos; erro de validação preserva a geração anterior.
- Estratégia full rebuild deliberada para não perder RAW tardio/backfill devido a cursor lexical; `source_max_event_id` é apenas diagnóstico.

### Validação remota
- CI #1693 — run `44516277804`, commit `b62e8660b4bc32c9d921e5fcf09bdfdb428fbb67`: SUCCESS; **550/550 testes OK** em 4,216 s; compileall aprovado.
- Seis testes específicos aprovados: bytes/metadata, idempotência e geração, chegada tardia, eventos ignorados, rollback em payload inválido e isolamento do checkpoint de transporte.

### Estado e limites
- PR #23 permanece OPEN, Draft, sem merge; base `feat/damm-v2-referral-transfer-attribution`.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; nenhuma alteração na main.
- Nenhum provider conectado, nenhum wire capture, backfill real, timeline persistente, seleção canônica de fork, transições econômicas ou execução financeira.
- A reconstrução integral é a primeira versão e ainda precisa de avaliação de desempenho/escala.

### Próxima etapa
Persistir/reconstruir a timeline de conta e os vínculos de banco/fork a partir do RAW e da projeção, mantendo histórico órfão e sem inferir canonicalidade por ordem de chegada. Antes de implementar, definir geração, atomicidade, rollback e checkpoints próprios dessa timeline. Não conectar provider.


## 293. Timeline persistente e reconstruível de contas/bancos — 19/11/2026

### Entrega
- Implementado na branch `feat/damm-v2-economic-reconciliation`, PR #23.
- Arquivos:
  - `src/smart_money_radar/data_sources/geyser_account_timeline.py` — snapshot público `timeline_records()`.
  - `src/smart_money_radar/storage/geyser_account_timeline_projection.py`.
  - `tests/test_geyser_account_timeline_projection.py`.
- Classe `SQLiteGeyserAccountTimelineProjection`; APIs `rebuild()`, `get_checkpoint()`, `list_account_writes()`, `list_banks()`, `list_gaps()`, `list_conflicts()`.
- Usa `smr_geyser.sqlite`; RAW continua fonte imutável e `smr_events.sqlite` permanece isolado.
- Rebuild reproduz primeira entrega sequenciada por evento lógico, ordenada por delivery_id. Timelines isoladas por source_id, evitando falso reconnect entre provedores.
- Persiste continuidade de account writes (epoch, baseline, continuity_baseline), status do banco, nós de banco, vínculos exatos por blockhash, statuses, invalidações, substituições, gaps e conflitos.
- Preserva banco invalidado e account writes relacionados; não apaga histórico nem declara fork canônico por ordem de chegada.
- Checkpoint/generation versionados e separados dos checkpoints de transporte. Rebuild integral atômico; falha preserva geração anterior.
- RAW sem entrega sequenciada é preservado no RAW, mas ignorado na timeline e contabilizado no checkpoint.

### Validação
- CI #1706 — run `44517573857`, commit `6bf265be4f9f7cd48ba1044ad19272c8b1a4095b`: SUCCESS; **559/559 testes OK**; compileall aprovado.
- Nove testes novos específicos aprovados: persistência de timeline e bancos, vínculo pai exato, parent_block_id opaco, invalidação, checkpoint, chegada tardia, rollback por payload malformado, gap e isolamento de fontes.

### Limites
- Offline; nenhuma conexão Geyser/Helius, captura wire ou backfill real.
- Não há seleção canônica automática, rollback canônico automático, tabela persistente de transições econômicas pre/post, BUY/SELL nem execução financeira.
- Rebuild integral ainda requer avaliação de escala.
- Eventos sem sequência de transporte conhecida não entram na timeline nesta versão.

### Próxima etapa
Projetar recuperação/backfill com checkpoints granulares, cobertura auditável e reconciliação de eventos RAW sem sequência. Continuar offline; não conectar provider.


## 294. Recuperação de backfill e checkpoints granulares — 19/11/2026

### Implementação
- Criado `src/smart_money_radar/storage/geyser_recovery_store.py`.
- Criado `tests/test_geyser_recovery_store.py`.
- Classe `SQLiteGeyserRecoveryStore`, usando o mesmo `smr_geyser.sqlite`, isolado do `smr_events.sqlite`.
- Migração de recovery versionada separadamente do schema RAW.
- Tabelas:
  - `geyser_backfill_jobs`: fonte, intervalo de slots, provider/adapter/schema, semântica da consulta, cursores opacos, estado, cobertura, contadores, tentativas, erro, evidência e timestamps.
  - `geyser_backfill_attempts`: histórico imutável por tentativa, cursor inicial/final, estado, timestamps e erro.
  - `geyser_projection_checkpoints`: checkpoint por nome/versão da projeção e `source_id`, geração, maior delivery/evento, contagens, eventos sem sequência, cobertura dos inputs e continuidade interrompida.
- APIs de job: `create_backfill_job()`, `start_backfill_job()`, `update_backfill_progress()`, `finish_backfill_job()`, `recover_interrupted_jobs()`, `get_backfill_job()`, `list_backfill_jobs()`, `list_backfill_attempts()`.
- API de projeção: `record_projection_checkpoint()` e `get_projection_checkpoint()`.
- Estados de job PENDING/RUNNING/PARTIAL/COMPLETED/FAILED; cobertura COMPLETE/PARTIAL/UNKNOWN.
- Retomada preserva o último cursor durável e cria número de tentativa crescente. Jobs RUNNING abandonados são marcados PARTIAL quando já receberam dados ou FAILED quando ainda vazios; cobertura nunca é promovida automaticamente.
- Contadores não podem regredir. Apenas jobs RUNNING aceitam progresso/finalização. COMPLETE exige evidência estruturada de contrato confirmado, intervalo coberto, paginação esgotada, retenção verificada e semântica idêntica à consulta registrada.
- Checkpoints de projeção são por fonte e versão. Geração e delivery_id não podem regredir. Cobertura COMPLETE é recusada quando há continuidade interrompida ou eventos sem sequência ignorados.
- Checkpoint de projeção deve ser gravado somente depois do commit da geração. Se houver interrupção entre os dois commits, o checkpoint fica atrasado (seguro) e pode ser refeito; não se avança checkpoint antes da projeção.

### Limites
- Camada offline de persistência/controle; não há cliente, paginação, scheduler ou executor real de backfill.
- Evidência de cobertura é fornecida pelo futuro adapter e registrada para auditoria; o store não prova independentemente as garantias do provider.
- Cursores são opacos e não são comparados/interpretados.
- O rebuild atual da timeline continua integral e ainda não chama automaticamente o novo checkpoint granular.
- RAW e deliveries continuam imutáveis; não são sintetizados eventos ausentes, canonicalidade, BUY/SELL ou ordens.
- Nenhum endpoint/credencial/cliente Yellowstone ou Helius, VPS, serviço pago ou operação on-chain foi conectado.

### Testes e CI
- Dez testes específicos adicionados para lifecycle, prova de cobertura, divergência de semântica, contadores monotônicos, recuperação após interrupção, retomada de cursor/tentativa, isolamento de fonte, cobertura fail-closed, monotonicidade do checkpoint e validação de estado/intervalo.
- CI #1733 — run `44519550364`, commit `f90fd43bbbd03c7c03bfbf7b23ca5907e5d60066`: SUCCESS; **569/569 testes OK** em 4,343 s; `python -m compileall -q src tests` aprovado.
- Runs #1727 e #1731 falharam em dois testes da etapa (expectativa incorreta sobre iniciar job PENDING e atualização do attempt interrompido); ambos corrigidos antes do CI #1733 aprovado.

### Estado
- PR #23 permanece Draft e sem merge; branch `feat/damm-v2-economic-reconciliation`.
- `main` não foi alterada.
- Próxima ação: definir uma política auditável para RAW sem sequência, sem inventar ordem, e medir o custo do full rebuild com volume representativo. A integração do checkpoint por fonte ao rebuild foi concluída na seção 295.


## 295. Integração do checkpoint granular ao rebuild da timeline — 19/11/2026

### Implementação
- Modificado `src/smart_money_radar/storage/geyser_account_timeline_projection.py`.
- Modificado `tests/test_geyser_account_timeline_projection.py`.
- `SQLiteGeyserAccountTimelineProjection.rebuild()` grava checkpoint de recovery para cada `source_id` somente depois do commit bem-sucedido da geração derivada.
- Checkpoint registra nome/versão da projeção, geração, último delivery observado, último event reproduzido, contagem de deliveries, eventos projetados, entradas ignoradas, cobertura e continuidade interrompida.
- Checkpoints são isolados por fonte. Contagem e maior delivery_id consideram todas as entregas da fonte, inclusive as que não apontam para evento RAW; last_event_id é o último evento sequenciado reproduzido.
- A geração derivada continua sendo reconstruída integralmente e substituída atomicamente: account writes, bank lineage, gaps, conflitos e checkpoint global permanecem na mesma transação SQLite.
- Depois do commit dessa geração, o recovery store grava os checkpoints por fonte em transação separada. Interrupção entre as fases deixa o checkpoint atrasado, nunca adiantado; novo full rebuild pode reconciliar.
- Associação dos account writes aos event IDs RAW passou a usar chave determinística construída durante replay, evitando varredura repetida de todos os RAWs para cada escrita.

### Política de cobertura
- COMPLETE: todos os streams observados têm baseline declarado pelo adapter, sem checkpoint interrompido, gap/anomalia aberta, gap da timeline ou input ignorado.
- PARTIAL: há baseline declarado, mas foi observada lacuna, interrupção, anomalia ou entrada ignorada.
- UNKNOWN: não há checkpoint de transporte ou algum stream usa baseline first_observed_unverified.
- COMPLETE significa continuidade de transporte desde baseline declarado; não prova completude do histórico do provider nem de intervalo de backfill.
- RAW sem entrega sequenciada continua preservado e contabilizado, sem ordem artificial ou projeção na timeline.

### Testes e CI
- Quatro testes de integração: checkpoint por fonte após rebuild; UNKNOWN para baseline não verificado; PARTIAL para gap; isolamento entre fontes.
- Teste de payload RAW malformado também confirma que falha no rebuild não avança checkpoint de recovery.
- CI #1743 — run `44520328616`, commit de código `979e6841f348ae74de40d65b14411eb883b5cc64`: SUCCESS; **573/573 testes OK** em 5,904 s; `python -m compileall -q src tests` aprovado.

### Limites
- Full rebuild continua como mecanismo de recuperação/fallback; não há replay incremental.
- RAW sem sequência ainda não entra na timeline; política específica para reconciliação permanece pendente.
- COMPLETE não é prova de histórico integral do provider; backfill histórico permanece separado.
- Offline: nenhum RPC, endpoint, cliente, credencial, serviço, VPS ou backfill ao vivo foi conectado.

### Estado
- PR #23 permanece Draft e sem merge; branch `feat/damm-v2-economic-reconciliation`.
- `main` permanece sem alteração.
- Próxima ação: especificar e implementar política auditável para RAW sem sequência; depois medir o full rebuild com volume representativo, sem abandonar o fallback integral.


## 296. Contrato inicial SolanaTransactionEvidenceBundle — 19/11/2026

### Objetivo e decisão
- Formalizada a necessidade de impedir que evidências de transações Solana distintas sejam combinadas na reconciliação econômica DAMM v2.
- A identidade raiz é composta por `transaction_signature`, `slot`, `source_id` e SHA-256 do payload RPC canonicalizado.
- O envelope deve ser construído a partir de um único payload original; decoders não devem receber listas independentes como se a origem comum estivesse garantida.
- Evidências históricas (por exemplo, prestate de mint e snapshots withheld-fee) mantêm identidade/proveniência próprias e precisam de vínculo temporal demonstrável com a transação-alvo. Não devem ser forçadas a compartilhar a assinatura da transação-alvo.

### Implementação inicial nesta branch
- Branch: `feat/solana-transaction-evidence-bundle`.
- Base: branch `feat/damm-v2-economic-reconciliation`, commit `4a517ca15499746ddd3f5522f112c80aaac1433b` (HEAD confirmado na consulta de 19/11/2026).
- Criado `src/smart_money_radar/data_sources/solana_transaction_evidence_bundle.py`.
- Criado `tests/test_solana_transaction_evidence_bundle.py`.
- `build_solana_transaction_evidence_bundle()` recebe um único payload RPC e `source_id`; valida assinatura Solana em Base58 com 64 bytes, calcula SHA-256 sobre JSON canonicalizado e executa internamente os decoders de inventário de instruções, transfers SPL/Token-2022 e deltas pre/post.
- A identidade do inventário é comparada com a assinatura e o slot do envelope.
- Resultados incompletos dos decoders são preservados; `structurally_complete` permanece falso quando inventário ou deltas estão incompletos.
- A camada é apenas de evidência: não classifica BUY/SELL, não reconcilia economia e não autoriza execução.

### Testes adicionados
- Payload válido e hash determinístico.
- Wrapper padrão RPC `result`.
- `source_id` ausente.
- Assinatura ausente ou que não seja Base58 de 64 bytes.
- Slot ausente/inválido, incluindo boolean.
- Evidência de delta incompleta preservada como inelegível.
- Payload não JSON rejeitado em vez de gerar hash de representação arbitrária.

### Estado e limites
- Commits da branch incluem contrato inicial `263c119d6f7fb6195e214062229096da629ae359`, testes `febb9ec60d5465077f1fe292ae11023644ddd67f`, validação de assinatura `8599339ea1e30c3c21db44a0f2607c45aa6920dd` e fixture de assinatura válida `aafa0fe6f52001d7382b86650395669f73d996a1`.
- Registro Mestre atualizado nesta branch; validação CI ainda não consultada nesta atualização.
- Ainda não existe integração deste envelope com `reconcile_damm_v2_economic_batch()`, contexts DAMM v2 ou snapshots históricos.
- Ainda não há prova tipada de associação de contexts/eventos DAMM v2 ao envelope; essa integração deve ser uma etapa seguinte, com testes de mistura de assinatura, slot, fonte e payload.
- Nenhum decoder existente foi modificado.
- PR #34 criada como Draft contra `feat/damm-v2-economic-reconciliation`; nenhum merge foi realizado e `main` permanece intocada.

### Próxima etapa
Validar os testes e compileall em CI no HEAD desta branch. Em seguida, revisar o contrato contra os casos de proveniência DAMM v2 e desenhar a integração com contexts, transfer evidence e snapshots históricos antes de conectar o reconciliador econômico.


### Atualização de CI e correção — PR #34 (19/11/2026)
- Primeiro CI observado no HEAD `4eb9a90876f7d9a5f7712c7331bc92df3f6909de`: workflow `SMR tests`, run `44599405464`, job `135826377268`, FAILURE.
- O job instalou o projeto e iniciou `PYTHONPATH=src python -m unittest discover -s tests -v`; foram executados 580 testes e 9 erros ficaram concentrados no novo módulo.
- Causa confirmada nos logs: `_transaction_identity()` chamava `_is_valid_signature()`, mas a função não estava definida no arquivo naquele HEAD, gerando `NameError`.
- Correção aplicada: definição explícita de `_is_valid_signature()` antes de `_transaction_identity()`, validando Base58 e comprimento decodificado de 64 bytes.
- Commit corretivo: `4199bdc0dcc75956a5709ac635fd188d16e41a4b`.
- CI do novo HEAD ainda precisa ser consultado; a correção não é considerada validada até o workflow correspondente terminar com sucesso.
- PR #34 permanece Draft e sem merge; `main` não foi alterada.


### CI após correção — PR #34 (19/11/2026)
- HEAD validado: `63fe7019d365fe6fc51b50eeb2d2c3a53a24bb9e`.
- Workflow `SMR tests`, run `44599723147`, job `135827505295`: SUCCESS.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: 580 testes executados em 4,506 s, sem falhas.
- `python -m compileall -q src tests`: etapa concluída com sucesso.
- A execução anterior com 9 erros foi corrigida pela inclusão efetiva de `_is_valid_signature()`; o HEAD validado inclui o código corretivo e este registro.
- Esta validação confirma testes unitários e compilação no runner GitHub Actions/Python 3.12; não comprova integração econômica DAMM v2, proveniência de snapshots históricos, dados RPC reais ou execução em produção.
- PR #34 continua Draft, aberta e sem merge. `main` permanece intocada.


## 297. Integração inicial de associações e contexts DAMM v2 ao bundle — 19/11/2026

### Objetivo
Evitar que o chamador monte manualmente `contexts`, `transfers`, `evidence` e `balance_deltas` independentes e os entregue ao reconciliador como se sua origem comum estivesse comprovada.

### Implementação nesta branch
- Branch: `feat/solana-transaction-evidence-bundle`; PR #34 Draft, base `feat/damm-v2-economic-reconciliation`.
- `DammV2SwapEventAssociation` passou a preservar `resolved_accounts`, resolvidas no próprio analyzer a partir da lista de contas da instrução DAMM v2 e do account-key table do mesmo payload. Índices booleanos, inválidos ou fora do intervalo não são aceitos como contas resolvidas.
- A factory `build_solana_transaction_evidence_bundle()` agora executa `analyze_damm_v2_swap_events()` sobre o mesmo payload original usado pelos decoders de transfers e balance deltas.
- Para cada associação MATCHED, a factory usa as contas resolvidas e o EvtSwap2 para chamar `decode_damm_v2_swap_accounts()`, construindo `DammV2SwapTransferContext`.
- A factory chama `analyze_damm_v2_transfer_evidence()` com os contexts e a lista de transfers derivados do mesmo payload.
- Associações não resolvidas, contas ausentes/inválidas ou inconsistência de contexto são registradas em `damm_v2_issues`; a camada não inventa contextos parciais.
- `damm_v2_complete` exige cobertura de todas as associações por contexts e transfer evidence ATTRIBUTED.
- Adicionada `reconcile_solana_transaction_damm_v2_bundle()`: recebe o bundle, não listas independentes; usa signature e slot da identidade raiz e bloqueia bundles sem associação, estruturalmente incompletos, com issues ou transfer evidence não atribuída.
- O wrapper exige bundle criado pela factory validada (token privado interno), reduzindo composição acidental de objetos independentes. Isto é uma proteção de contrato interno, não uma fronteira criptográfica contra código hostil no mesmo processo.

### Testes e validação
- Teste positivo da cadeia de construção: payload -> associação DAMM -> contas resolvidas -> context -> transfer evidence.
- Teste negativo para índice de conta inválido, que não cria context e deixa o bundle inelegível.
- Testes do wrapper: ausência de transferências impede reconciliação; ausência de associações DAMM também bloqueia; bundle recomposto manualmente é rejeitado.
- Uma execução intermediária teve 1 falha no fixture de teste por codificação incorreta de bytes zero na função Base58 de teste; o fixture foi corrigido. Não foi identificada falha equivalente no código de produção.
- HEAD de código validado: `fee487e9da7522a6025b9c70df5dbd703dd129bd`.
- CI `SMR tests`, run `44601037164`, job `135832185607`: SUCCESS; 584 testes em 4,448 s; `python -m compileall -q src tests` aprovado.
- O CI comprova testes unitários e compilação no runner GitHub Actions; não comprova tráfego RPC real nem execução em produção.

### Limites ainda existentes
- Não há ainda fixture positivo de reconciliação econômica completa passando pela nova factory até resultado RECONCILED.
- Snapshots históricos de mint/withheld continuam recebidos como evidências externas e precisam manter sua própria identidade, proveniência e vínculo temporal com a transação-alvo.
- O envelope ainda não prova a proveniência externa dos snapshots históricos nem substitui a validação específica já implementada no reconciliador.
- Não foi conectado a adapter operacional/RPC nem a execução financeira.
- A PR #34 permanece Draft e sem merge; `main` permanece intocada.

### Próxima etapa
Criar fixture sintético de ponta a ponta que percorra factory -> associação -> contexts -> transfer evidence -> reconciliação econômica, incluindo snapshots históricos quando aplicável. O teste deve provar o caso RECONCILED e os bloqueios para assinatura/slot/payload divergentes antes de qualquer integração operacional.


## 298. Fixture positivo end-to-end DAMM v2 e integridade do bundle — 19/11/2026

### Fixture sintético positivo
- Criado payload RPC sintético com swap DAMM v2 na instrução externa, duas transferências Token-2022 descendentes e EvtSwap2 descendente.
- A instrução DAMM usa 14 contas resolvidas pelo account-key table.
- Transfer input: bruto 100, fee explícita 5, crédito líquido 95.
- Transfer output: bruto 90, fee 0, crédito líquido 90.
- EvtSwap2 fixture consistente: included input 95, bruto input 100, output 90 e net output 90.
- Snapshots pre/post incluem as quatro token accounts e owners esperados: carteira monitorada nos lados do usuário e pool authority nos vaults.
- O teste atravessa a factory real: payload -> inventário -> transfer decoders -> balance deltas -> swap/EvtSwap2 association -> resolved accounts -> context -> transfer evidence -> bundle-only economic reconciler.
- Resultado observado: `RECONCILED`, uma operação, quatro expected account deltas. Withheld fee e mint fee config permanecem `EXPECTED_NOT_VERIFIED`, corretamente sem alegação de verificação TLV.

### Fixture negativo econômico
- Alterada a quantidade post do token account do usuário de 900 para 901 sem mudar transfer/event evidence.
- O reconciliador retorna `INCOMPLETE` por divergência de delta; nenhuma promoção indevida para RECONCILED.

### Endurecimento de integridade do bundle
- Durante a criação dos testes de identidade foi identificado que `dataclasses.replace()` preservava o token privado de factory e permitia substituir campos do bundle, inclusive signature/slot/hash e evidências, sem perder o token.
- Corrigido com snapshot interno de referências imutáveis aos componentes produzidos pela factory; o wrapper verifica que identidade, inventário, transfers, balance deltas, associações, contexts, transfer evidence e issues são exatamente os objetos selados na construção.
- Testes negativos confirmam bloqueio ao substituir assinatura, slot, payload SHA-256, transfers, contexts ou balance deltas.
- Proteção é integridade de contrato contra recomposição acidental/uso normal de dataclasses; não é fronteira criptográfica contra código hostil com acesso introspectivo ao mesmo processo Python.

### CI
- HEAD de código validado: `1c9e6da69bf573f03b61d7da809fb8c6220affc3`.
- Workflow `SMR tests`, run `44601942485`, job `135835372820`: SUCCESS.
- 588 testes em 4,511 s; `python -m compileall -q src tests` aprovado.
- A execução anterior no HEAD `22ba642eadfcc5b06d3e73b07b5443d72a007a75` também passou com 587 testes e provou os dois novos cenários end-to-end; a validação atual acrescenta os testes de substituição do bundle.
- CI valida fixtures/unit tests e compilação; não comprova tráfego mainnet, estado TLV real ou integração provider.

### Estado e pendências
- PR #34 permanece Draft, aberta e sem merge; main intacta.
- A fixture positiva econômica agora existe e passa.
- Continuam pendentes snapshots históricos de mint/withheld com proveniência independente e validação temporal; especialmente teste de verificação TLV realista.
- Ainda faltam testes dedicados de divergência de source_id dentro de um envelope de origem comum e auditoria final do diff completo antes de considerar PR pronta.
- Não ligar a adapter RPC operacional nem execução financeira nesta etapa.

### Próxima ação
Revisar e formalizar o contrato de proveniência dos snapshots históricos de mint/withheld, incluindo vínculo inequívoco de source, assinatura, slot, ordem e referências pre/post; adicionar testes negativos de mistura e só então avaliar uma fixture positiva com fee state verificado.

## 299. Proveniência vinculada de snapshots históricos mint/withheld — 19/11/2026

### Contrato implementado
- Snapshots históricos de mint e withheld agora carregam `source_id`, `ordering_domain_id` e `transaction_payload_sha256`, vinculando a evidência à mesma origem, ao mesmo domínio de ordenação e ao payload transacional usado no bundle.
- `build_damm_v2_mint_fee_config_snapshots()` exige `source_id` e `ordering_domain_id` do prestate iguais aos da transação, além de SHA-256 válido do payload RPC. Calcula o SHA-256 dos bytes brutos do mint prestate, preserva esses bytes no snapshot e deriva `config_state` diretamente deles.
- `verify_damm_v2_mint_fee_config()` exige source ID, ordering domain e payload hash esperados; compara assinatura, fonte, domínio, payload hash, epoch, slot, ordem, mint e posição exata da transferência.
- O verifier recalcula o hash dos bytes do mint e decodifica novamente o TLV; rejeita bytes alterados ou config_state que não corresponda aos bytes.
- `DammV2WithheldFeeSnapshot` preserva bytes brutos pre/post, SHA-256 individuais, source ID, hash do payload e referências separadas.
- `verify_damm_v2_withheld_fee_deltas()` recalcula os hashes, redecodifica TransferFeeAmount dos bytes brutos e compara com `decoded_delta`; também exige source ID, ordering domain e hash do payload iguais aos da transação, assinatura/slot/ordem e `pre < transaction < post`.
- `reconcile_solana_transaction_damm_v2_bundle()` propaga source ID e payload SHA-256 da identidade raiz para a reconciliação econômica. O caminho de cálculo de fee (`_calculate_fee_from_mint_snapshot`) também recalcula o hash e redecodifica os bytes brutos antes de usar a configuração.

### Testes negativos adicionados
- Snapshot de mint com source ID diferente.
- Snapshot de mint com ordering domain diferente.
- Snapshot withheld com ordering domain diferente.
- Builder de mint rejeita prestate de outro ordering domain.
- Snapshot withheld com source ID diferente.
- Hash do payload transacional divergente para mint.
- Hash do payload transacional divergente para withheld.
- Bytes brutos do mint alterados sem atualizar o digest.
- Bytes brutos withheld alterados sem atualizar o digest.
- Builder de mint rejeita prestate de outra origem.
- Testes anteriores de assinatura, slot, ordem, posição de inicialização, configuração e divergência de taxas continuam ativos.

### Validação
- HEAD de código validado: `7d6d30efd683668a258b8764d35e2585b80224ba`.
- Workflow `SMR tests`, run `44606196108`, job `135850416062`: SUCCESS.
- 598 testes em 4,818 s; `python -m compileall -q src tests` aprovado.
- A validação inclui a distinção explícita entre fonte e domínio de ordenação; streams/conexões diferentes não podem ser comparadas apenas por compartilhar `source_id`.
- O CI valida testes sintéticos/unitários e compilação; não comprova autenticidade do provider, coleta Geyser real, ordering real, mainnet ou execução em produção.

### Limites explícitos
- SHA-256 prova consistência dos bytes apresentados, não autenticidade do provider nem correção da ordem atribuída pelo adapter.
- `source_id` precisa ser estável e representar o domínio real de origem/ordenação; a camada de ingestão ainda deve provar essa semântica.
- Ainda não há adapter operacional que capture mint/account pre/post snapshots em mainnet e demonstre ordenação real.
- Nenhuma execução financeira foi conectada.
- PR #34 continua Draft e sem merge; `main` permanece intacta.

### Próxima ação
Auditar o diff completo da PR #34 e verificar se o contrato de snapshots, o bundle e a documentação estão coerentes. Depois, definir o contrato do adapter de ingestão Geyser/provider-neutral, sem conectar execução financeira.
## 300. Contrato do adapter provider-neutral de snapshots históricos — 19/11/2026

### Decisão de arquitetura
- Criado `docs/SOLANA-HISTORICAL-SNAPSHOT-INGESTION-CONTRACT.md`.
- Separadas três identidades: `source_id` (namespace estável provider/node), `ordering_domain_id` (domínio em que números de ordem são comparáveis) e `stream_id` (conexão/transporte).
- Mesmo `source_id` não autoriza comparar sequência de streams diferentes. Para snapshots, `transaction_order`, `pre_snapshot_order` e `post_snapshot_order` precisam pertencer ao mesmo `ordering_domain_id`.
- Em uma stream Yellowstone multiplexada, o domínio pode corresponder à conexão/stream; reconnect cria novo domínio, salvo prova de cursor global comum fornecida pelo provider.
- `stream_sequence` não pode ser inferida de slot, write_version, timestamp, delivery_id, índice de instrução ou sequência de outra stream. `slot/write_version` permanecem metadados de ordem de ledger/account writes, com semântica distinta.
- Builder e verifiers de mint/withheld agora exigem e comparam o domínio de ordenação. O caminho de cálculo de fee de mint também rejeita domínio diferente.
- `reconcile_solana_transaction_damm_v2_bundle()` aceita `transaction_ordering_domain_id` explicitamente e propaga ao reconciliador.

### Contrato do adapter definido
- Normalizar transaction observations e account updates preservando payload/bytes originais, signature, slot, pubkey, owner, write_version, bank/fork metadata, source ID, ordering domain, stream ID e sequência.
- Construir mint prestate apenas com bytes capturados antes da transação, mesma fonte/domínio, ordem menor e inventário de instruções completo; a versão atual também exige mesmo slot.
- Construir withheld pre/post apenas de transição de token account vinculada à assinatura exata, mesma fonte/domínio e ordem `pre < transaction < post`; sem poststate vinculado, não inferir.
- Gap, reconnect, baseline, fork não resolvido, conflito, owner/mint/pubkey divergente ou stream/domain diferente tornam a evidência inelegível.
- A política de commitment/finality ainda precisa ser formalizada e representada de forma tipada antes de promover snapshots a VERIFIED em produção.
- O documento define critérios de aceitação e testes de streams diferentes, gaps/reconnects, forks, assinatura, owner/mint, bytes adulterados e replay.
- Nenhum provider foi conectado; Yellowstone/Helius continuam fontes candidatas, não dependências operacionais.

### Validação
- HEAD de código validado: `7d6d30efd683668a258b8764d35e2585b80224ba`.
- CI `SMR tests`, run `44606196108`, job `135850416062`: SUCCESS; 598 testes em 4,818 s; compileall aprovado.
- Commits posteriores desta seção são documentação apenas; nenhum código alterado após o HEAD validado.

### Estado
- PR #34 continua Draft, aberta, mergeable e sem merge.
- `main` permanece intocada.
- Próxima ação: auditar o contrato do adapter contra os normalizadores/timeline Geyser existentes e especificar a representação tipada de commitment/finality antes de qualquer adapter operacional.

## 301. Política de commitment/finality e bloqueio de transições não finalizadas — 19/11/2026

### Decisão
- Estados de commitment não são equivalentes: PROCESSED e CONFIRMED são observações não finais; FINALIZED é somente declaração reportada pelo provider.
- `commitment_state()` expõe `UNKNOWN`, `PROVIDER_REPORTED_PROCESSED`, `PROVIDER_REPORTED_CONFIRMED`, `PROVIDER_REPORTED_FINALIZED`, `DEAD`, `INVALIDATED` e `CONFLICTED`.
- A elegibilidade de uma transição bank-scoped exige o banco do prestate e do poststate em estado provider-reported finalized.
- Para transições entre bancos, cada ancestral explicitamente ligado na cadeia precisa estar finalizado e utilizável; ancestralidade ausente não é inferida.
- Conflitos de blockhash/parent metadata contaminam a identidade do banco e invalidam o nó existente ou sua materialização posterior. Uma mensagem FINALIZED posterior não reabilita banco conflitante.
- SLOT_DEAD, EntryUpdateParent e rollback permanecem bloqueios; RAW/orphaned evidence é preservada sem promoção.
- FINALIZED não autentica criptograficamente o provider nem comprova consenso independente. Adapter operacional ainda exige política de autenticação, identidade de endpoint, integridade de transporte, reconnect e rollback.

### Implementação
- Branch: `fix/geyser-finalized-evidence-gate`, criada a partir do HEAD exato da PR #34 `e3d3cba59c57a9947010dd241bb2ddb2c0b76fe7`.
- Arquivos de código/teste: `src/smart_money_radar/data_sources/geyser_bank_lineage.py`, `src/smart_money_radar/data_sources/geyser_account_timeline.py`, `tests/test_geyser_bank_lineage.py`, `tests/test_geyser_account_timeline.py`.
- Documento: `docs/GEYSER-COMMITMENT-FINALITY-POLICY.md`.
- Testes adicionados para progressão de commitment, ancestral finalizado, conflito de metadados e bloqueio de transição até finalização dos dois lados.

### Estado de validação
- Implementação enviada à branch isolada; CI ainda não executado/confirmado.
- Nenhum provider foi conectado. Nenhuma execução financeira foi habilitada.
- PR #34 e main não foram alteradas; nenhuma integração/merge foi feita.

### Próxima etapa
Executar CI na branch isolada, corrigir qualquer falha e auditar o diff final. Não promover FINALIZED a VERIFIED operacional até implementar confiança/autenticação do provider.


### CI inicial e atualização dos fixtures — PR #35
- Primeira execução `SMR tests`, run `44609714040`, job `135862746101`: FAILURE em 603 testes; 5 falhas estavam em `tests/test_geyser_bank_aware_timeline.py`, que ainda esperava transições com bancos apenas observados.
- A falha confirmou a alteração semântica pretendida: os cenários positivos antigos precisavam declarar `SLOT_FINALIZED` nos bancos relevantes.
- Fixtures atualizados para finalizar bancos e ancestrais nos casos positivos; adicionado teste de que `SLOT_DEAD` posterior revoga a elegibilidade mesmo após finalização.
- Novo CI ainda pendente. Nenhum resultado de sucesso pode ser declarado até consulta ao run do HEAD atualizado.


### Validação final da PR #35 — 19/11/2026
- HEAD exato validado: `77b6702f1961c4591544b1c0a7f69da2fafa3cb4`.
- Workflow `SMR tests`, run `44610018989`, job `135863814877`: SUCCESS.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: 604 testes executados em 4,133 s, sem falhas.
- `python -m compileall -q src tests`: etapa concluída com sucesso.
- A primeira execução no código antes da atualização dos fixtures falhou em 5 testes antigos que esperavam transições sem SLOT_FINALIZED; os fixtures foram corrigidos para refletir a nova regra. A validação final ocorreu no HEAD documental exato informado acima.
- CI valida testes unitários e compilação; não autentica provider, não prova finalização em mainnet e não valida adapter operacional.
- PR #35 continua Draft, aberta, mergeable e sem merge; PR #34 permanece sem alteração/merge; main não foi alterada.


## 302. Auditoria de segurança final da PR #35 — 19/11/2026

### Escopo revisado
- Diff completo da PR #35: 7 arquivos, 247 adições e 2 remoções.
- `geyser_bank_lineage.py`, `geyser_account_timeline.py` e testes bank-aware/lineage/timeline.
- Estado do PR: OPEN, Draft, mergeable, sem merge; base `feat/solana-transaction-evidence-bundle`; HEAD de código validado `25279630ac0310343ac55425232ad65f68064efd`.

### Resultado: achado que impede considerar a política completa
- `AccountUpdateTimeline.transition_for()` preserva o caminho legado para updates sem `bank_id`: aceita predecessor linear imediato dentro do mesmo continuity_epoch.
- Esse caminho não exige commitment/finality, como esperado para compatibilidade histórica, mas retorna a mesma estrutura `AccountStateTransition` usada pelo caminho bank-scoped, sem campo de proveniência/nível de confiança que distinga `LEGACY_UNSCOPED` de `BANK_PROVIDER_REPORTED_FINALIZED`.
- Risco: um consumidor pode interpretar todas as transições retornadas como igualmente verificadas, apesar de as transições legadas não terem identidade bancária nem prova de finalização.
- Não foi comprovado neste escopo que algum consumidor downstream esteja de fato promovendo tais transições a evidência operacional. Portanto, é uma lacuna de contrato/rotulagem, não um bug downstream observado.
- Correção recomendada antes de adapter operacional: tipar a proveniência/confiança da transição (p.ex. `BANK_PROVIDER_REPORTED_FINALIZED` vs `LEGACY_UNSCOPED_UNVERIFIED`) ou separar APIs/coleções; qualquer consumidor que exija evidência finalizada deve rejeitar explicitamente o estado legado. Não inferir finalização para dados sem `bank_id`.

### Propagação de conflitos e ancestrais
- `_conflict()` marca a identidade afetada como conflicted e invalidated, inclusive quando o nó já existe; `_node()` também aplica a contaminação se o conflito preceder a materialização.
- `is_bank_usable()` percorre os ancestrais explicitamente vinculados e retorna falso se encontrar nó morto/inválido; `is_bank_finalized()` também exige finalização e usabilidade de cada ancestral ligado.
- `transition_for()` exige ambas as verificações para target e predecessor e, em pares cross-bank, exige `is_ancestor(...) is True`.
- Revisão estática indica que conflito em ancestral ligado bloqueia a elegibilidade do descendente. Entretanto, a suíte atual não possui teste direto dedicado que crie descendente ligado, contamine depois o ancestral e prove que a transição deixa de ser retornada. Recomenda-se adicionar esse teste de regressão.
- `SLOT_DEAD` mantém dead persistente; `EntryUpdateParent` invalida o banco específico; a transição legada não atravessa updates bank-scoped intermediários e respeita continuity_epoch/reconnect.

### Conclusão
- A regra bank-scoped está fail-closed para estados não finalizados e ancestrais explicitamente ligados, conforme o código revisado.
- A PR #35 ainda não deve ser considerada completa para uso operacional até distinguir explicitamente transições legadas sem bank_id e adicionar o teste de taint de ancestral para descendente.
- Nenhuma alteração de código foi feita nesta auditoria; apenas este registro foi acrescentado.
- Nenhum provider foi conectado; nenhuma evidência foi promovida a VERIFIED; nenhuma execução financeira habilitada.

### Próxima ação
- Propor alteração mínima de contrato para rotular transições legadas como não verificadas e adicionar teste de regressão para conflito histórico de ancestral. Manter PR #35 Draft e sem merge até nova CI e revisão.


## 303. Correções da auditoria PR #35 — implementação — 19/11/2026

### Alterações implementadas na branch da PR #35
- `AccountStateTransition` agora carrega `evidence_classification` explícito:
  - `BANK_PROVIDER_REPORTED_FINALIZED` para transições bank-scoped que passaram os gates de usabilidade e finalização de ambos os bancos e ancestrais explicitamente ligados.
  - `LEGACY_UNSCOPED_UNVERIFIED` para pareamento linear legado sem `bank_id`; preserva compatibilidade, mas não é evidência finalizada nem pode ser promovido a `VERIFIED`.
- Docstrings e `docs/GEYSER-COMMITMENT-FINALITY-POLICY.md` esclarecem que consumidores que exigem evidência finalizada devem aceitar explicitamente apenas `BANK_PROVIDER_REPORTED_FINALIZED`.
- Teste positivo verifica classificação bank-scoped.
- Novo teste prova que transição sem `bank_id` retorna `LEGACY_UNSCOPED_UNVERIFIED`.
- Novo teste de regressão constrói cadeia pai/filho finalizada, confirma inicialmente a transição e depois injeta blockhash conflitante no ancestral; a identidade ancestral é contaminada e a transição do descendente deixa de ser retornada.
- Arquivos alterados: `src/smart_money_radar/data_sources/geyser_account_timeline.py`, `tests/test_geyser_bank_aware_timeline.py`, `docs/GEYSER-COMMITMENT-FINALITY-POLICY.md` e este Registro Mestre.

### Estado de validação
- Alterações gravadas na branch `fix/geyser-finalized-evidence-gate` por commits sequenciais.
- HEAD atual da PR após as correções e atualização do registro: `19669153c460d49c5133653b7be8b79c05c45c5a`.
- A revisão do diff confirmou a classificação mutuamente exclusiva no construtor: `LEGACY_UNSCOPED_UNVERIFIED` apenas quando `bank_id` está ausente; caso contrário, `BANK_PROVIDER_REPORTED_FINALIZED` somente após os gates bancários.
- Workflow `SMR tests`, run `44611738575`, job `135869848269`: SUCCESS no merge ref da PR `8eb6d0136d35369f020ab76557e98d40a2f9aab1`, que incorpora o HEAD `19669153c460d49c5133653b7be8b79c05c45c5a` sobre a base `e3d3cba59c57a9947010dd241bb2ddb2c0b76fe7`.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: 606 testes executados em 4,133 s, todos aprovados; `python -m compileall -q src tests` também aprovado.
- CI valida o conjunto integrado da PR, não provider mainnet nem adapter operacional.
- PR #35 permanece Draft e sem merge; `main` permanece intacta.

### Próxima ação
- Fazer revisão final de segurança do diff após a CI aprovada; manter PR #35 Draft e sem merge até autorização explícita.


## 304. Auditoria dos consumidores downstream de AccountStateTransition — 19/11/2026

### Escopo e método
- Revisado o snapshot da branch fix/geyser-finalized-evidence-gate, HEAD 4dc6b8bf8e70d2d26a0d80ebf7f1007e710e1e0a.
- Inventário recursivo do Git tree: 54 módulos Python sob src/ e 60 arquivos de teste sob tests/.
- Inspecionadas as referências de produção a AccountStateTransition, transition_for(), evidence_classification, is_bank_finalized(), is_bank_usable() e commitment_state(), além dos módulos de ingestão, storage/projections, serviços e CLI.

### Resultado
- Nenhum módulo Python de produção fora de data_sources/geyser_account_timeline.py referencia ou consome AccountStateTransition ou chama transition_for().
- Nenhum consumidor downstream de produção atual foi encontrado que possa ignorar evidence_classification.
- Chamadas transition_for() encontradas estão na própria implementação da Timeline e nos testes Geyser.
- Os módulos de storage/projection, ingestão, serviços, dashboard e CLI revisados não promovem transições da Timeline a VERIFIED nem as consomem como autorização operacional.
- Portanto, a classificação explícita adicionada na PR #35 não tem consumidor de produção atual que a ignore neste snapshot.

### Limites
- Esta conclusão é limitada ao snapshot e ao código versionado inspecionado; não prova comportamento de processos externos, forks ou código futuro.
- Ainda não existe adapter operacional/provider integrado. Qualquer adapter futuro deve exigir explicitamente evidence_classification == BANK_PROVIDER_REPORTED_FINALIZED para caminhos que demandem evidência finalizada, e deve implementar separadamente autenticação do provider, identidade do endpoint, integridade do transporte, reconnect/rollback e controles de finalização.
- PROVIDER_REPORTED_FINALIZED permanece uma declaração do provider, não prova criptográfica independente de consenso.
- Nenhum arquivo de produção foi alterado nesta auditoria; apenas o Registro Mestre foi atualizado.

### Conclusão e próxima ação
- Auditoria downstream atual: sem achados de consumidores produtivos que ignorem a classificação.
- PR #35 permanece Draft e sem merge; main intacta.
- Próxima ação recomendada: revisão final do diff completo e confirmação do CI da implementação; depois, apresentar estado para decisão explícita sobre eventual merge, sem executá-lo automaticamente.


## 305. Avaliação de integração PR #35 sobre PR #34 — 19/11/2026

### Relação entre branches e PRs
- PR #34: base `feat/damm-v2-economic-reconciliation`, HEAD `e3d3cba59c57a9947010dd241bb2ddb2c0b76fe7`, Draft, aberta, sem merge, mergeable.
- PR #35: base `feat/solana-transaction-evidence-bundle`, HEAD `71acfdd603cf92d34b78298e6e8b9c524c48bae1`, Draft, aberta, sem merge, mergeable.
- Comparação GitHub entre a base da PR #35 e seu HEAD: `ahead_by=19`, `behind_by=0`, `merge_base=e3d3cba59c57a9947010dd241bb2ddb2c0b76fe7`, idêntico ao HEAD/base atual da PR #34. Relação linear confirmada: PR #35 está diretamente construída sobre o HEAD da PR #34, sem divergência da base.
- Diff específico da PR #35 contra a base PR #34: sete arquivos; política de finality, lineage, timeline, testes e Registro Mestre. Os arquivos e commits próprios da PR #34 permanecem como ancestralidade/base, não são reintroduzidos como mudanças da PR #35.

### CI e compatibilidade
- Após o commit documental da auditoria downstream, o workflow `SMR tests` executou no HEAD exato `71acfdd603cf92d34b78298e6e8b9c524c48bae1`: run `44612471809`, job `135872388784`, SUCCESS.
- Etapas `Run unit tests` e `Compile source and tests` concluídas com sucesso. Esta consulta confirma o sucesso do workflow completo; não foi obtido nesta consulta um total de testes distinto do registro anterior de 606.
- O workflow é evento `pull_request` para PR #35 contra o HEAD/base `e3d3cba...` da PR #34, portanto valida a combinação proposta PR #34 + PR #35 no contexto de merge do GitHub.
- A PR #35 preserva as alterações do bundle da PR #34 como ancestralidade e adiciona a política Geyser de finality; não foi observada divergência de base nem conflito reportado pelo GitHub.

### Conclusão da avaliação
- Integração proposta tecnicamente coerente: PR #35 é uma continuação direta da PR #34, sem commits da base ausentes ou divergentes.
- O GitHub reporta ambas as PRs `mergeable=true`; PR #35 está Draft e não mergeada.
- Isto é uma avaliação de compatibilidade, não autorização nem execução de merge. Nenhuma branch foi movida, nenhuma PR foi retargeted ou merged e `main` permanece intacta.
- Sequência de integração, caso seja autorizada depois: integrar PR #35 na branch-base da PR #34 (não em `main`); confirmar o novo HEAD da PR #34 e executar/confirmar CI nesse HEAD atualizado; só então revisar a PR #34 como unidade antes de qualquer decisão posterior sobre `main`.

### Estado
- Avaliação concluída sem bloqueio estrutural identificado para a integração PR #35 -> PR #34.
- Próxima ação: aguardar autorização expressa para integrar/mergear PR #35 na branch da PR #34. Não executar automaticamente.


## 306. Integração da PR #35 na branch da PR #34 — 19/11/2026

### Autorização e execução
- Usuário autorizou explicitamente integrar a PR #35 à branch da PR #34; a autorização não incluiu merge em `main`.
- Antes da integração, CI no HEAD exato da PR #35 `b1afc4b36d300a7f246c6d979ea7d96de23a3058` foi confirmado SUCCESS: workflow `SMR tests`, run `44612741281`.
- PR #35 estava Draft; foi marcada Ready for review para permitir o merge autorizado.
- PR #35 foi mergeada na sua base `feat/solana-transaction-evidence-bundle` usando merge commit, com expected head SHA `b1afc4b36d300a7f246c6d979ea7d96de23a3058`.
- Merge commit: `bfba2128b47178d106723d7e284018923524a02e`.

### Verificação posterior
- PR #35: CLOSED/MERGED; merge commit confirmado `bfba2128b47178d106723d7e284018923524a02e`.
- PR #34: continua OPEN/DRAFT, não mergeada; novo HEAD `bfba2128b47178d106723d7e284018923524a02e`, mergeable=true.
- `main` verificada após o merge e permanece no SHA `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; não foi alterada.
- CI do merge commit foi iniciado no evento PR #34; na consulta inicial, check `test` estava IN_PROGRESS. Não declarar a combinação final validada até concluir com SUCCESS.

### Escopo e segurança
- A integração ocorreu somente na branch da PR #34, conforme autorização.
- Nenhuma alteração foi feita diretamente em `main`; nenhuma execução financeira ou conexão de provider foi habilitada.
- PR #34 continua Draft para revisão do conjunto integrado. A integração da PR #35 não autoriza merge da PR #34 em `main`.

### Próxima ação
- Aguardar e verificar CI no HEAD `bfba2128b47178d106723d7e284018923524a02e` da PR #34. Se aprovado, revisar o conjunto integrado e atualizar este registro com o resultado. Nenhum merge adicional sem autorização expressa.


## 307. Integração da PR #34 — SolanaTransactionEvidenceBundle e finality — 19/11/2026

### Autorização e merge
- O usuário autorizou explicitamente a integração em 19/11/2026.
- PR #34: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/34
- Branch de origem: `feat/solana-transaction-evidence-bundle`.
- Branch de destino configurada na PR: `feat/damm-v2-economic-reconciliation` (não `main`).
- HEAD aprovado: `268c5d523a9e1ae45b10b504de1cfe440fefa14b`.
- CI pré-merge no HEAD exato: workflow `SMR tests`, run `44613188412`, SUCCESS.
- PR #34 marcada Ready for review e mergeada pelo método merge.
- Merge commit: `6d120e6b250a57539c39037843741442229c855e`.
- GitHub confirmou PR #34 CLOSED/MERGED em 19/11/2026 20:56:20Z.
- Branch `feat/damm-v2-economic-reconciliation` passou a apontar para o merge commit acima.
- PR #23 continua como PR de integração subsequente; a atualização do HEAD da sua branch não equivale a merge da PR #23.

### Validação pós-merge
- Workflow `SMR tests`, run `44613711343`, executado no merge commit exato `6d120e6b250a57539c39037843741442229c855e`.
- Conclusão: SUCCESS.
- Job `test` (`135876655534`): SUCCESS.
- Passos Install project, Run unit tests e Compile source and tests: SUCCESS.
- A validação comprova o estado integrado no commit acima; não comprova integração com provider live, coleta de snapshots mainnet ou execução financeira.

### Escopo integrado e limites preservados
- Bundle transacional Solana com identidade por assinatura, slot, source_id e SHA-256 do payload canonicalizado; inventário de instruções, transfers e balance deltas derivados do mesmo payload.
- Associação DAMM v2, contas resolvidas, contexts e transfer evidence vinculados ao bundle; reconciliação econômica recebe o bundle e falha fechado quando a evidência está incompleta ou inconsistente.
- Snapshots históricos de mint/withheld preservam bytes brutos, hashes, source_id e ordering_domain_id; ordens de streams/domínios distintos não são comparadas sem garantia explícita.
- Política Geyser commitment/finality integrada: PROCESSED/CONFIRMED não autorizam transição; bank-scoped transitions exigem estados e ancestrais explicitamente vinculados como PROVIDER_REPORTED_FINALIZED e utilizáveis; conflitos e SLOT_DEAD mantêm evidência inelegível.
- `PROVIDER_REPORTED_FINALIZED` continua sendo declaração do provider, não autenticação criptográfica nem prova independente de consenso.
- Nenhum adapter Geyser/provider live, snapshot mainnet capturado, sinal BUY/SELL, autorização de execução ou execução financeira foi criado por esta integração.

### Estado das branches e próxima ação
- PR #34: CLOSED/MERGED.
- PR #35: CLOSED/MERGED dentro da PR #34.
- Branch `feat/damm-v2-economic-reconciliation`: HEAD `6d120e6b250a57539c39037843741442229c855e`.
- PR #23 permanece aberta/Draft, com destino `feat/damm-v2-referral-transfer-attribution`; não foi mergeada.
- `main` verificada após o merge: permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Próxima ação: revisar a integração da PR #23 no seu destino configurado, sem alterar `main` e sem merge sem autorização explícita.


## 308. Revisão técnica da PR #23 após integração PR #34/#35 — 19/11/2026

### Snapshot revisado e CI
- PR #23: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/23
- Título: Reconcile DAMM v2 swap economics against token account deltas.
- Estado durante a revisão: OPEN/DRAFT, mergeable=true, sem merge.
- Branch head: `feat/damm-v2-economic-reconciliation`, snapshot revisado `8735ff4bd54b801925146df34825ee353efea54c`.
- Branch base: `feat/damm-v2-referral-transfer-attribution`, HEAD `0567eb9c4981ba6ffc33e98a402292130667760a`.
- Compare entre branch base e head: 298 commits à frente, 0 atrás; merge base igual ao HEAD da base.
- CI no HEAD exato `8735ff4bd54b801925146df34825ee353efea54c`: workflow `SMR tests`, run `44613829010`, job `135876655534`, SUCCESS.
- Log do job confirma 606 testes aprovados em 4,859s e `python -m compileall -q src tests` aprovado.
- CI comprova suíte automatizada e compilação no snapshot; não comprova provider live, ingestão mainnet nem integridade operacional em produção.

### Achados bloqueadores para aprovação técnica
1. **Timeline persistida não aplica taint histórico de anomalias de transporte.**
   - Em `src/smart_money_radar/storage/geyser_account_timeline_projection.py`, `rebuild()` seleciona a primeira delivery sequenciada de cada evento RAW (`MIN(delivery_id)` com `stream_sequence IS NOT NULL`) e reproduz o evento sem consultar a elegibilidade da sequência em `geyser_transport_anomalies`.
   - A consulta de anomalias abertas é usada posteriormente apenas para calcular o checkpoint/coverage; não remove do replay os eventos afetados.
   - Assim, uma sequência reutilizada por eventos distintos ou marcada por conflito de identidade pode deixar o primeiro evento da sequência dentro da Timeline, inclusive se a anomalia for posteriormente RESOLVED. O status administrativo RESOLVED não deve reabilitar evidência histórica.
   - `AccountUpdateTimeline.transition_for()` não recebe a auditoria de anomalias de transporte; a classificação de banco/finality, por si só, não compensa a falta desse gate.
   - Correção necessária: construir a projeção a partir de deliveries elegíveis segundo auditoria histórica por sequência, preservando taint mesmo após resolução administrativa; nenhuma sequência afetada pode fornecer transição elegível. Adicionar testes de colisão de sequência, conflito RAW, resolução administrativa posterior e ausência de transição para todas as deliveries afetadas.

2. **A projeção não valida o SHA-256 armazenado do payload RAW antes de decodificar.**
   - O SELECT de `rebuild()` lê `payload_bytes`, mas não seleciona `payload_sha256`; `_decode_event()` valida envelope/campos e Base64, mas não recalcula o digest contra o hash persistido.
   - Um payload normalizado alterado para outro JSON ainda estruturalmente válido pode ser projetado apesar de divergir do hash registrado na linha RAW.
   - O teste atual `test_bad_raw_payload_rolls_back_previous_generation` cobre Base64 inválido, mas não mutação válida que preserve a estrutura.
   - Correção necessária: verificar SHA-256 dos bytes exatos antes de qualquer decode/projeção e falhar sem substituir a geração anterior; adicionar teste com alteração semântica válida e hash original preservado.

### Achado de consistência/replay a resolver
3. **Replay em ordem de chegada não recupera uma lacuna preenchida tardiamente.**
   - A projeção ordena por `delivery_id`; `AccountUpdateTimeline.add()` classifica uma sequência menor/igual à última observada como conflito.
   - O RAW store permite que a chegada tardia de uma sequência ausente feche a lacuna do checkpoint de transporte, mas o rebuild continua vendo a ordem de chegada e pode manter conflito/gap na Timeline.
   - Exemplo a cobrir: sequência 1, depois 3, depois chegada tardia da 2. Definir explicitamente se backfill/replay pode reconstruir a ordem lógica pela sequência dentro do mesmo stream; se não puder, documentar a perda de elegibilidade como política, sem declarar continuidade completa. Não misturar streams/domínios diferentes.

### Pontos aprovados nesta revisão
- Bundle Solana vincula inventory, transfers e balance deltas ao mesmo payload canonicalizado e não produz classificação BUY/SELL.
- Reconciliação DAMM v2 agrega deltas por token account e falha fechado diante de transferências não atribuídas que afetem contas do swap.
- Snapshot de mint/withheld exige proveniência, hashes, assinatura/slot/ordem e ordering_domain_id compatíveis.
- Estado withheld permanece EXPECTED_NOT_VERIFIED até conferência de TLV pre/post; VERIFIED depende de snapshots vinculados.
- Política de finality preserva a distinção entre declaração PROVIDER_REPORTED_FINALIZED e prova criptográfica independente.
- Storage RAW e recovery permanecem offline; nenhum adapter/provider live foi encontrado nesta etapa.

### Decisão da revisão e estado
- **PR #23 não aprovada para merge neste snapshot.** CI verde e mergeable=true não resolvem os achados de integridade acima.
- Nenhum arquivo de produção foi alterado nesta revisão.
- Registro Mestre atualizado nesta seção para preservar os achados e evitar reauditoria.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; nenhum merge, retarget ou alteração de main foi executado.
- Próxima ação recomendada: corrigir os dois bloqueadores de integridade em branch de trabalho, adicionar testes de regressão, validar CI no novo HEAD e então repetir a revisão focada. O achado de replay tardio deve ser resolvido/documentado antes de qualquer promoção operacional.


## 309. Correções de integridade da Timeline Geyser — PR #36 — 19/11/2026

### Branch isolada e escopo
- Usuário autorizou explicitamente implementar os achados da revisão da PR #23 em 19/11/2026.
- Para preservar a branch da PR #23 e a `main`, foi criada branch isolada `fix/geyser-timeline-raw-integrity` a partir do snapshot revisado `0d1188370d622aee34b3f2ea7060c8f606aa7034`.
- PR stacked Draft #36: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/36
- Destino da PR #36: `feat/damm-v2-economic-reconciliation`, que é a branch HEAD da PR #23; a PR #36 não foi mergeada.
- PR #23 permanece aberta/Draft; sua branch não foi alterada por esta implementação.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

### Implementação
- `src/smart_money_radar/storage/geyser_account_timeline_projection.py`:
  - `PROJECTION_VERSION` incrementada de 1 para 2.
  - Antes de decodificar payload normalizado selecionado para projeção, recalcula SHA-256 sobre os bytes RAW exatos e exige igualdade com `payload_sha256`; divergência lança ValueError dentro da transação, preservando a geração anterior.
  - Delivery só é elegível se não existir anomalia histórica para a tupla exata `(source_id, stream_id, stream_sequence)`, independentemente de status OPEN ou RESOLVED.
  - Evento lógico com qualquer conflito persistido em `geyser_raw_conflicts` é excluído da Timeline derivada; RAW e registros de conflito permanecem intactos.
  - Delivery elegível é ordenada por `source_id, stream_id, stream_sequence, delivery_id`; sequência só é ordenada dentro da mesma stream. Troca de stream permanece fronteira de continuidade, sem comparação numérica entre streams.
- `tests/test_geyser_account_timeline_projection.py` adiciona cobertura para: sequência contaminada mesmo após RESOLVED; identidade RAW conflitante excluída; mutação JSON estruturalmente válida com hash antigo causa rollback da geração; sequência tardia 2 reconstruída entre 1 e 3 no replay integral.
- `docs/GEYSER-ACCOUNT-TIMELINE.md` documenta o contrato persistente v2, taint histórico, integridade SHA-256 e semântica de replay.

### Evidência de CI
- Commit de código/testes: `ceeaf82f1873dfdbe873120789d16dc08a79750b`.
- Workflow `SMR tests`, run `44614876540`, job `135880748123`: SUCCESS.
- Log do job: 609 testes aprovados em 4,712s; `python -m compileall -q src tests` aprovado.
- Testes novos confirmados individualmente no log:
  - `test_resolved_transport_anomaly_still_taints_every_delivery_of_sequence`
  - `test_raw_identity_conflict_taints_original_event_from_timeline`
  - `test_valid_json_payload_mutation_fails_raw_hash_and_rolls_back_generation`
  - `test_late_arriving_sequence_is_replayed_in_stream_order`
- CI push no commit de código/testes `ceeaf82f1873dfdbe873120789d16dc08a79750b`: run `44614876540`, job `135880748123`, SUCCESS, 609 testes em 4,712s e compileall SUCCESS. CI pull_request após a atualização da política documental: run `44615009546`, head `48b58391f4e091a85a742e06166ec62cca1d9259`, job `135881222296`, SUCCESS; log confirma os mesmos 609 testes em 4,713s, os quatro testes novos e compileall SUCCESS. O HEAD final da branch passou depois a `4e699dd1f57c967c0e00566c77b803580b766a93` apenas por atualização do Registro Mestre; nenhum arquivo de código ou teste foi alterado após o snapshot validado.

### Limites e pendências
- A revisão não cria adapter live nem consulta provider; não altera RAW; não infere sequência ausente; não declara fork canônico; não habilita execução financeira.
- A projeção continua agrupando timelines por source; ao alternar streams, o modelo cria uma fronteira de continuidade conservadora. Não há comparação de sequência entre streams.
- PR #36 está OPEN/DRAFT, sem merge. PR #23 está OPEN/DRAFT e ainda não aprovada para merge até a correção ser integrada e reavaliada.
- Próxima ação: confirmar CI no HEAD final da PR #36, revisar o diff completo e os testes; então reavaliar se os bloqueadores da PR #23 foram resolvidos. Nenhum merge sem autorização explícita.


## 310. Integração da PR #36 na branch da PR #23 — 19/11/2026

### Autorização e merge
- Em resposta ao pedido explícito de autorização para integrar a PR #36 na branch da PR #23, o usuário respondeu “Continua”, autorizando essa integração específica.
- PR #36: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/36.
- Branch de origem: `fix/geyser-timeline-raw-integrity`.
- Branch de destino: `feat/damm-v2-economic-reconciliation`, HEAD da PR #23.
- Antes do merge, PR #36 estava OPEN, Ready for review, mergeable=true, com HEAD exato `96ac001d8dc25b83a70fea6e171479f2a5cfbb25`.
- CI no HEAD exato da PR #36: workflow `SMR tests`, run `44615167545`, SUCCESS; etapas Run unit tests e Compile source and tests SUCCESS.
- PR #36 foi mergeada com método `merge`, usando expected_head_sha `96ac001d8dc25b83a70fea6e171479f2a5cfbb25`.
- Merge commit: `5e61f7ac45d4ac205082b3cf638746d7b9359874`.
- GitHub confirmou PR #36 CLOSED/MERGED em 19/11/2026.
- PR #23 passou a apontar para o merge commit `5e61f7ac45d4ac205082b3cf638746d7b9359874`; segue OPEN/DRAFT, sem merge.

### CI pós-merge e estado da PR #23
- Dois checks `test` executaram no merge commit exato `5e61f7ac45d4ac205082b3cf638746d7b9359874`:
  - workflow run `44616027232`, job `135884828901`: SUCCESS.
  - workflow run `44616038524`, job `135884866313`: SUCCESS.
- Em ambos os jobs, Run unit tests e Compile source and tests concluíram SUCCESS. Não registrar total de testes deste snapshot sem log que o confirme.
- Após a conclusão, GitHub reportou PR #23 OPEN/DRAFT, mergeable=true.
- Compare da PR #23: branch head `feat/damm-v2-economic-reconciliation` está 305 commits à frente e 0 atrás da base `feat/damm-v2-referral-transfer-attribution`; merge base `0567eb9c4981ba6ffc33e98a402292130667760a`.
- `main` foi consultada após o merge e permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; nenhuma alteração em main.

### Efeito e limites
- Os dois bloqueadores identificados na revisão anterior da PR #23 foram corrigidos na Timeline persistida: taint histórico de anomalias/conflitos RAW e verificação SHA-256 dos bytes RAW, com rollback.
- Replay de sequência tardia foi definido e testado por ordenação dentro da mesma stream, sem comparar sequências entre streams.
- As correções permanecem offline. Não houve integração de provider live, captura mainnet, autorização de BUY/SELL ou execução financeira.
- A aprovação técnica anterior foi específica para as correções da PR #36; não equivale a aprovação final de todo o conjunto da PR #23 nem autorização para merge da PR #23 em sua base ou em `main`.

### Próxima ação
- Fazer revisão integrada focada da PR #23 no novo HEAD `5e61f7ac45d4ac205082b3cf638746d7b9359874`, com atenção às interfaces entre DAMM v2, SolanaTransactionEvidenceBundle, Token-2022 snapshots e Timeline/finality Geyser.
- Apresentar achados e decisão técnica antes de qualquer merge da PR #23. `main` permanece intocada.

## 311. Revalidação focada da PR #23 após integração PR #36 — 19/11/2026

### Snapshot e evidências
- Código integrado revisado no merge commit da PR #36: `5e61f7ac45d4ac205082b3cf638746d7b9359874`.
- PR #23 permaneceu OPEN/DRAFT e não mergeada; branch de destino `feat/damm-v2-referral-transfer-attribution`.
- CI pós-merge no commit `5e61f7ac45d4ac205082b3cf638746d7b9359874`: runs `44616027232` e `44616038524`, ambos SUCCESS; em ambos, Run unit tests e Compile source and tests SUCCESS.
- Compare da PR #23: 305 commits ahead, 0 behind, merge base `0567eb9c4981ba6ffc33e98a402292130667760a`.
- GitHub reportou PR #23 mergeable=true após atualização de estado; continua Draft.
- HEAD documental posterior do Registro Mestre: `c4514e42c10b8a2a39bdefe25db7537f877393a3`. Esse commit altera apenas este registro; CI de código comprovado permanece no merge commit `5e61f7ac...`.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

### Revalidação dos achados anteriores
- O gate de replay agora exclui qualquer delivery cuja tupla `(source_id, stream_id, stream_sequence)` tenha anomalia histórica, sem reabilitação por status RESOLVED.
- Identidades de evento RAW com conflito registrado são excluídas da Timeline derivada.
- SHA-256 é recalculado sobre os bytes persistidos exatos antes de decodificação; divergência aborta a transação e preserva a geração anterior.
- Replay integral ordena por source/stream/sequence, permitindo inserir sequência tardia dentro da mesma stream sem comparar números de sequência entre streams.
- Quatro testes de regressão específicos cobrem os casos anteriores; CI do merge commit concluiu com sucesso.
- Os dois bloqueadores de integridade da revisão da PR #23 e o achado de replay tardio foram resolvidos no snapshot integrado.

### Decisão e limites
- Revisão focada pós-integração: os bloqueadores previamente registrados para a Timeline persistida foram eliminados; não foi identificado bloqueio novo decorrente da integração da PR #36.
- A PR #23 pode avançar para a etapa de decisão de integração, mas permanece OPEN/DRAFT. Esta conclusão não executa aprovação formal no GitHub nem merge.
- Ainda não existe adapter/provider live integrado, ingestão mainnet contínua, pipeline operacional de snapshots históricos, geração de SwapObservation/BUY/SELL ou execução financeira. A aprovação da camada offline não deve ser confundida com prontidão operacional do SMR.
- Nenhuma alteração de código foi feita durante esta revalidação; somente este Registro Mestre foi atualizado.

### Próxima ação
- Apresentar ao usuário a decisão técnica e aguardar autorização expressa separada antes de marcar a PR #23 como Ready for review ou fazer merge na branch-base. `main` continua protegida e não autorizada para integração.

## 312. Integração da PR #23 na branch-base da PR #22 — 19/11/2026

### Autorização e merge
- Usuário autorizou continuar com a integração da PR #23 na branch-base `feat/damm-v2-referral-transfer-attribution` em 19/11/2026.
- PR #23 foi revalidada no HEAD `d08c146cb4f517842b1a950c08e27aad6f0bbd6b`; check `test` run `44616249711`, job `135885605685`, SUCCESS. Run unit tests e Compile source and tests: SUCCESS.
- Compare imediatamente antes do merge: 307 commits ahead, 0 behind; merge base `0567eb9c4981ba6ffc33e98a402292130667760a`.
- PR #23 foi marcada Ready for review e mergeada pelo método merge, com expected_head_sha `d08c146cb4f517842b1a950c08e27aad6f0bbd6b`.
- Merge commit: `e45d9483f852b832bea81530e3a404578953a0de`.
- GitHub confirmou PR #23 CLOSED/MERGED em 19/11/2026 21:12:16Z.
- Branch de destino `feat/damm-v2-referral-transfer-attribution`, que é a head da PR #22, foi atualizada para `e45d9483f852b832bea81530e3a404578953a0de`.
- PR #22 não foi mergeada; `main` não foi alterada.

### CI pós-merge
- No commit exato `e45d9483f852b832bea81530e3a404578953a0de`, GitHub iniciou dois checks `test`: run `44616389430` (job `135886106076`) e run `44616402476` (job `135886150325`).
- Na última consulta, ambos estavam IN_PROGRESS. Não declarar CI pós-merge aprovado até confirmação SUCCESS.
- CI aprovado no HEAD pré-merge da PR #23 permanece run `44616249711`; isso não substitui a validação do merge commit.

### Estado e limites
- PR #23: CLOSED/MERGED na branch da PR #22.
- PR #22: permanece como PR de integração subsequente, sem merge.
- `main` consultada após o merge e permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- A integração reúne a reconciliação econômica DAMM v2, bundle de evidências Solana, política de finality e correções de integridade da Timeline Geyser na branch de trabalho.
- Não há, por esta integração, provider live habilitado, ingestão mainnet contínua, sinal BUY/SELL, autorização de execução ou operação financeira.

### Próxima ação
- Aguardar e verificar os dois checks no merge commit `e45d9483f852b832bea81530e3a404578953a0de`; se ambos SUCCESS, atualizar o Registro Mestre e seguir com revisão integrada da PR #22. Não fazer merge da PR #22 sem autorização expressa.

### Complemento da validação pós-merge — 19/11/2026
- Os dois checks no merge commit `e45d9483f852b832bea81530e3a404578953a0de` foram concluídos SUCCESS:
  - Run `44616389430`, job `135886106076`: SUCCESS; Run unit tests e Compile source and tests SUCCESS.
  - Run `44616402476`, job `135886150325`: SUCCESS; Run unit tests e Compile source and tests SUCCESS.
- PR #22 consultada após a integração: OPEN/DRAFT, sem merge. GitHub reportou `mergeable=false` no snapshot consultado; isso precisa ser investigado na revisão da PR #22, não deve ser tratado como aprovado ou como conflito específico sem diagnóstico adicional.
- `main` novamente verificada: permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Registro Mestre atualizado para refletir a conclusão dos dois checks. Este commit é exclusivamente documental.

## 313. Diagnóstico de mergeability e revisão técnica integrada da PR #22 — 19/11/2026

### Diagnóstico do estado de merge
- Após a integração PR #23 → branch da PR #22, uma leitura inicial reportou `mergeable=false` no estado da PR #22.
- Nova consulta direta ao endpoint GitHub da PR #22 confirmou `mergeable=true` e `mergeable_state=clean`; a consulta normalizada também retornou `mergeable=true`.
- Compare atual entre base `feat/token2022-transfer-checked-with-fee` e head `feat/damm-v2-referral-transfer-attribution`: 327 commits ahead, 0 behind; merge base `46dcf389d4cb06973a5d82967ba99fa3965121be`.
- Conclusão: o `mergeable=false` anterior era um estado transitório/desatualizado de cálculo do GitHub; não foi encontrado conflito ativo no snapshot posterior. Não foi necessário resolver conflitos nem alterar código.

### CI no HEAD exato da PR #22
- HEAD consultado: `d9ab2fbf78579449e3ed96639c9aa9a49b8d3f76`.
- Workflow run `44616500146`, job `135886496789`: SUCCESS.
- Logs confirmam `Ran 609 tests in 4.697s`, `OK`; `python -m compileall -q src tests` também SUCCESS.

### Revisão técnica integrada
- Escopo revisado: atribuição DAMM v2 input/output/referral, matriz FeeMode, inventário de instruções externas/CPI, decoders Token-2022, bundle de evidências Solana, reconciliação econômica por lote, snapshots de mint/withheld, Timeline Geyser, projeção persistida, RAW integrity e política de finality.
- Referral: código exige descendência CPI confiável no mesmo outer instruction e anterior ao EvtSwap2; seleciona vault pela matriz FeeMode; valida destino referral, mint, Token Program, tipo checked, amount u64 positivo, fee explícita quando aplicável e não reutilização de transferências.
- Testes de FeeMode cobrem as seis combinações collect_fee_mode/trade_direction; testes de referral cobrem vault token A/B, ausência, duplicidade, divergência de amount, flag incompatível, fee inválida e ordenação CPI.
- Reconciliação econômica é por lote completo de swaps e por token account; não reparte arbitrariamente deltas entre swaps sequenciais; rejeita transferências não atribuídas que toquem contas envolvidas, snapshots incompletos, owner divergente e incompatibilidade bruto/líquido.
- Bundle Solana deriva inventário, transfers, deltas, associações e contextos do mesmo payload canonicalizado; a reconciliação recebe o bundle de factory, sem listas independentes.
- Correções PR #36 permanecem presentes: hash SHA-256 RAW verificado antes de projeção, taint histórico de anomalias/conflictos e replay em ordem de sequência dentro da stream.
- Política Geyser mantém distinção entre provider-reported finalized e prova independente de consenso; estados legacy sem bank_id não podem ser promovidos a VERIFIED.
- Não foi identificado novo bloqueador técnico no escopo revisado que impeça a conclusão desta fatia de atribuição/reconciliação offline.

### Limites e decisão
- Resultado da revisão: tecnicamente consistente para integração na cadeia de branches de desenvolvimento; não equivale a declarar o SMR operacional ou pronto para capital real.
- `ATTRIBUTED` continua distinto de `MATCHED`; `RECONCILED` valida deltas base do lote, mas withheld/mint fee permanecem `EXPECTED_NOT_VERIFIED` até os verificadores históricos apropriados.
- Não existe adapter live de provider validado nesta etapa; provenance fields e ordering domain dependem de implementação e garantias do coletor futuro.
- PR #22 permanece OPEN/DRAFT. Esta revisão não alterou o estado da PR, não submeteu aprovação formal GitHub e não executou merge.
- `main` permanece protegida e sem alteração; último SHA verificado `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

### Próxima ação
- Próximo passo é decidir separadamente se a PR #22 deve ser marcada Ready for review e integrada à sua branch-base `feat/token2022-transfer-checked-with-fee`. Nenhum merge está autorizado por esta revisão.

## 314. Integração da PR #22 na branch Token-2022 — 19/11/2026

### Autorização e pré-condições
- Usuário autorizou expressamente o merge da PR #22 em 19/11/2026 às 21:15:49Z.
- PR #22 foi reconsultada antes do merge: OPEN/DRAFT, head `f19894d845b413c312bcdde870713e2d2facda14`, base `feat/token2022-transfer-checked-with-fee`, `mergeable=true`, `mergeable_state=clean`.
- Compare pré-merge: 328 commits ahead, 0 behind; merge base `46dcf389d4cb06973a5d82967ba99fa3965121be`.
- Check no HEAD documental exato `f19894d845b413c312bcdde870713e2d2facda14`: `test` SUCCESS. O código funcional desse HEAD havia sido validado no HEAD de código `d9ab2fbf78579449e3ed96639c9aa9a49b8d3f76`, run `44616500146`, 609 testes OK e compileall SUCCESS; o commit documental subsequente não alterou código/testes.

### Merge
- PR #22 marcada Ready for review após a revisão técnica integrada registrada na seção 313.
- Merge executado com método `merge` e `expected_head_sha=f19894d845b413c312bcdde870713e2d2facda14`.
- Merge commit: `aa173f7bc13158d641e04d571173763df4962052`.
- PR #22 CLOSED/MERGED em 19/11/2026 às 21:16:03Z.
- Branch destino `feat/token2022-transfer-checked-with-fee` atualizada para `aa173f7bc13158d641e04d571173763df4962052`.
- `main` consultada após o merge permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; não foi alterada.

### CI pós-merge
- Check `test` no merge commit `aa173f7bc13158d641e04d571173763df4962052`: workflow run `44617037258`, job `135888377740`.
- Na última consulta, status IN_PROGRESS. Não declarar CI pós-merge aprovado até conclusão SUCCESS.

### Estado e limites
- PR #22 integrada à branch intermediária Token-2022; nenhuma integração foi feita à `main`.
- A cadeia de desenvolvimento agora contém atribuição de referral DAMM v2 por FeeMode, reconciliação econômica DAMM v2, bundle de evidências Solana, política de finality e correções Geyser.
- Atribuição permanece `ATTRIBUTED`, não `MATCHED`; isso não cria BUY/SELL nem autorização de execução.
- Provider live, ingestão mainnet contínua e execução financeira não foram habilitados por este merge.

### Próxima ação
- Aguardar e verificar CI pós-merge no commit `aa173f7bc13158d641e04d571173763df4962052`. Após SUCCESS, atualizar o Registro Mestre e avaliar tecnicamente a próxima etapa de integração da branch Token-2022, sem merge para `main` sem autorização expressa.

### Complemento CI pós-merge — 19/11/2026
- CI no merge commit exato `aa173f7bc13158d641e04d571173763df4962052` concluiu SUCCESS.
- Workflow run `44617037258`, job `135888377740`: SUCCESS.
- Logs: `Ran 609 tests in 4.821s`, `OK`; `python -m compileall -q src tests` SUCCESS.
- A branch `feat/token2022-transfer-checked-with-fee` permanece no merge commit `aa173f7bc13158d641e04d571173763df4962052` antes desta atualização exclusivamente documental.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

## 315. Contrato inicial de observação de transações Yellowstone — 19/11/2026

### Implementação
- Branch isolada: `feat/geyser-transaction-observation`, criada a partir do HEAD documental validado da branch Token-2022 `f688d290115ada8067ea0b1465076ff99f2e5f7c`.
- Criado `src/smart_money_radar/data_sources/geyser_transaction_updates.py` com `NormalizedTransactionObservation` e `normalize_transaction_update()`.
- O normalizador trata o wrapper Yellowstone `SubscribeUpdateTransaction`: slot vem do wrapper; assinatura, Transaction, meta, is_vote e índice vêm de TransactionInfo.
- Assinatura de 64 bytes é convertida para Base58 e comparada com a primeira assinatura da Transaction; divergência falha fechado.
- Preserva payload serializado de Transaction e TransactionStatusMeta, índice opcional, is_vote, assinatura, slot, source_id, stream_id, ordering_domain_id e stream_sequence.
- Meta ausente permanece ausente e marca `evidence_complete=false`; não há inferência.
- Bytes recebidos exatos podem ser fornecidos em `raw_message_bytes`; nesse caso provenance é `WIRE`. Sem bytes do transporte, usa serialização protobuf determinística marcada `PROTOBUF_DETERMINISTIC_RESERIALIZATION`, não wire RAW original.
- `geyser_proto_adapter.py` agora despacha o oneof transaction para o novo normalizador. A sequência não é atribuída pelo adapter: o receptor deve sequenciar todas as mensagens SubscribeUpdate em um único contador por stream antes da dispatch; o mesmo ordering_domain_id deve ser fornecido para transaction/account updates correlacionáveis.
- Criado `tests/test_geyser_transaction_updates.py` com testes para normalização, metadados, assinatura divergente, ausência de meta, bytes wire, validação de slot/sequência e dispatch.
- Atualizado `docs/SOLANA-HISTORICAL-SNAPSHOT-INGESTION-CONTRACT.md`, seção 10.

### Limites explícitos
- Esta fatia não implementa cliente gRPC, provider, sequenciador, persistência RAW, replay/reconnect, decodificação de instruções/CPI, transaction_order, snapshots históricos, classificação BUY/SELL ou execução.
- A integração efetiva com account updates ainda depende de um receptor que compartilhe sequência e ordering_domain_id e de persistência auditável. Nenhum snapshot se torna elegível por esta implementação isolada.
- Nenhum merge foi autorizado ou executado; a branch Token-2022 e `main` permanecem intactas.

### Validação
- Aguardando CI da PR draft no HEAD final; não declarar testes aprovados antes do resultado SUCCESS no commit correspondente.

### Próxima ação
- Abrir PR draft da branch `feat/geyser-transaction-observation` para `feat/token2022-transfer-checked-with-fee`, validar CI e revisar o diff integrado. Não fazer merge sem autorização expressa.


### CI diagnóstico e correção do teste de dispatch — 19/11/2026
- Primeira execução da PR #37: workflow run `44617930665`, job `135891505019`, falhou em 1 de 615 testes; os demais 614 testes passaram até o erro.
- Erro: o teste de dispatch construiu o objeto externo como se fosse o wrapper interno `SubscribeUpdateTransaction`; o adaptador corretamente despacha o campo oneof para esse wrapper, que por sua vez contém TransactionInfo.
- Correção: teste agora modela os dois níveis protobuf (`SubscribeUpdate` externo e `SubscribeUpdateTransaction` interno). Não alterar a semântica do contrato para acomodar fixture incorreta.
- CI ainda pendente no novo HEAD; nenhum resultado SUCCESS declarado.


### Ajuste adicional do contrato e estado da branch — 19/11/2026
- O teste de dispatch foi corrigido para representar explicitamente os dois níveis protobuf: envelope `SubscribeUpdate` e wrapper interno `SubscribeUpdateTransaction`.
- O serializador agora preserva também metadados protobuf presentes cuja serialização válida seja vazia (`b""`); ausência de meta continua distinguida de meta presente e vazia.
- HEAD atual da branch de trabalho: `8780bab8319df3b36968042596566f4558f9e0d1`.
- PR #37 permanece OPEN/DRAFT, destino `feat/token2022-transfer-checked-with-fee`; o primeiro CI no HEAD anterior falhou no fixture de dispatch. Aguardando execução/resultado no HEAD corrigido; não declarar CI aprovado.


### Validação final da PR #39 — 19/11/2026
- PR #37 foi fechada sem merge por ter sido supersedida após correção do fixture de dispatch; PR #38 foi fechada sem merge para que a validação fosse executada no commit que também inclui o teste protobuf wire-compatible. Nenhuma dessas PRs alterou a branch-base.
- PR ativa: #39, https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/39, OPEN/DRAFT, base `feat/token2022-transfer-checked-with-fee`, head `feat/geyser-transaction-observation-final`.
- HEAD de código/testes validado: `0d507b60c034a15112aae48244300a4a595d8343`.
- CI run `44618347330`, job `135892970258`: SUCCESS.
- Logs: `Ran 617 tests in 4.763s`; etapa `python -m compileall -q src tests` concluída SUCCESS.
- O teste protobuf adicional percorre o envelope externo `SubscribeUpdate`, wrapper `SubscribeUpdateTransaction`, TransactionInfo, assinatura, slot, índice, Transaction, TransactionStatusMeta e bytes wire fornecidos.
- A comparação confirma que a branch de trabalho está 20 commits à frente e 0 atrás da branch-base no merge base `f688d290115ada8067ea0b1465076ff99f2e5f7c`.
- A comparação de `main` com o SHA previamente verificado `5060bc65ddf181a4736fdb662c44c3fec0dd7259` retornou identical: main permanece intacta.
- Esta atualização do Registro Mestre é documental e posterior ao HEAD de código/testes validado; não altera código nem testes. Não declarar CI executado no commit documental resultante sem nova execução.

### Estado e próxima etapa
- Contrato inicial de observação de transações Yellowstone implementado e validado em CI.
- Ainda falta: sequenciador compartilhado real para todas as mensagens SubscribeUpdate; integração de ordering_domain_id com account updates; captura de wire bytes na camada de transporte; persistência RAW; reconexão/gap/replay; decodificação integral de instruções/CPI; vínculo com transaction_order e snapshots históricos.
- PR #39 permanece Draft e sem merge. A integração na branch Token-2022 e qualquer merge para `main` dependem de autorização expressa do usuário.


### Confirmação adicional de CI no HEAD documental — 19/11/2026
- Após a atualização documental registrada acima, o HEAD `9252a0785d6415f5c1eed98d62da8bb53c3c63a2` também foi validado pelo workflow `44618376264`, job `135893072276`: SUCCESS.
- Logs: `Ran 617 tests in 4.149s`; `python -m compileall -q src tests` concluído SUCCESS.
- A alteração posterior a esse HEAD é somente este complemento documental; nenhum código ou teste foi alterado após a validação.
- PR #39 segue OPEN/DRAFT e não foi mergeada. Branch-base Token-2022 permanece idêntica ao SHA `f688d290115ada8067ea0b1465076ff99f2e5f7c`; `main` permanece idêntica ao SHA `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

# Histórico da branch de auditoria RAW (#26)

## 296. Política e auditoria de deliveries RAW sem sequência — 19/11/2026

### Decisão arquitetural
- Adotada separação em três camadas: RAW/deliveries como evidência autoritativa; auditoria derivada de deliveries; timeline derivada apenas de eventos com evidência sequenciada elegível.
- Uma delivery sem sequência nunca recebe sequência inferida. Timestamp, slot, write_version, delivery_id e ordem de chegada não substituem sequência de transporte.
- Reconciliação é somente uma relação de evidência: exige mesmo event_id, source_id e SHA-256 do payload RAW, além de testemunha sequenciada sem conflito RAW ou anomalia de transporte aberta.
- Stream diferente pode fornecer testemunha para o mesmo evento lógico, mas a sequência nunca é transferida para a delivery sem sequência.
- Conflitos de identidade e sequências afetadas por anomalias abertas não são testemunhas elegíveis.
- Ausência de sequência não cria gap numérico e não muda por si só a semântica COMPLETE/PARTIAL/UNKNOWN.

### Implementação nesta branch
- Criado `docs/GEYSER-UNSEQUENCED-DELIVERY-POLICY.md`, policy `geyser-unsequenced-delivery:v1`.
- Criado `src/smart_money_radar/storage/geyser_unsequenced_delivery_audit.py`.
- Criado `tests/test_geyser_unsequenced_delivery_audit.py`.
- A projeção classifica cada delivery individualmente: SEQUENCED, UNSEQUENCED_UNRESOLVED, UNSEQUENCED_RECONCILED, IDENTITY_CONFLICT ou SEQUENCE_ANOMALY.
- Auditoria guarda reason_code, referência ao event_id/source/stream/sequence/hash e IDs das deliveries sequenciadas testemunhas.
- Rebuild da auditoria e checkpoint próprio são gravados na mesma transação SQLite. Falha reverte a geração e mantém checkpoint anterior.
- Nenhuma tabela RAW, delivery, conflito ou checkpoint de transporte é atualizada pela projeção.
- Entregas sem sequência continuam fora da timeline. A nova auditoria é paralela e reconstruível.

### Testes e CI
- Oito testes específicos adicionados: não reconciliado; reconciliação posterior por identidade/hash; testemunha em outra stream; conflito RAW; sequência anômala aberta; rebuild repetido/versionado; rollback forçado; invariância de RAW e checkpoints de transporte.
- CI #1748 — run `44522143646`, commit `e2daae67601ce38882fa68a5604dd64d952ba3a3`: SUCCESS. Etapas de unit tests e compileall concluídas com sucesso.
- Não atribuir contagem de testes até consultar o log detalhado do job.

### Estado e limites
- PR #26: Draft, aberto e sem merge; branch `feat/geyser-unsequenced-raw-audit`.
- PR #26 tem como base a branch da PR #23 (`feat/damm-v2-economic-reconciliation`), HEAD base `4a517ca15499746ddd3f5522f112c80aaac1433b`.
- PR #23 continua aberta/Draft; nenhuma integração foi feita na branch base.
- `main` não foi alterada.
- Nenhum provedor foi conectado; desenvolvimento offline.
- Próxima ação: revisão técnica da implementação e da semântica dos estados, depois testes adicionais de borda e escala da auditoria/rebuild. Não fazer merge sem autorização.


## 297. Revisão de borda e versionamento da auditoria RAW sem sequência — 19/11/2026

### Revisão e decisões confirmadas
- Revisada a política oficial e a implementação da PR #26.
- Confirmado que a chave de reconciliação é `event_id + source_id + payload_sha256`; `stream_id` não participa da identidade. Isso é intencional: uma testemunha sequenciada em outra stream pode reconciliar a entrega, mas sua sequência não é transferida.
- Confirmado que a timeline permanece separada e só seleciona deliveries sequenciadas; auditoria reconciliada não injeta uma segunda ocorrência na timeline.
- Não foi identificado defeito na regra central de reconciliação durante esta revisão.

### Ajustes implementados na branch da PR #26
- Adicionada tabela `geyser_unsequenced_delivery_audit_schema_migrations`, com registro da versão inicial 1 e bloqueio de abertura por código com versão de schema superior à suportada.
- Ampliados os testes de auditoria para cobrir:
  - fontes diferentes sem reconciliação;
  - eventos distintos no mesmo slot e em chegadas adjacentes;
  - deliveries diferentes com timestamp de recebimento idêntico;
  - múltiplas deliveries sem sequência preservadas individualmente;
  - múltiplas testemunhas sequenciadas, com lista completa de IDs;
  - evento inicialmente não resolvido que se torna reconciliado após chegada posterior da testemunha e novo rebuild;
  - exclusão de evento sem sequência da timeline e contabilização no checkpoint de recovery;
  - registro da versão da migração.
- O teste de reconciliação tardia agora executa rebuild antes e depois da chegada da testemunha.
- Total atual do arquivo de testes: 14 métodos de teste específicos.

### Commits da revisão
- `33e8a5c7f0de5f91e26d716f6c25301e27b34ab6` — registro de migração versionada.
- `eec9e512f0cf256d2fa8dcfe790fef3fc64a92cd` — testes adicionais de borda e isolamento da timeline.
- `4d71af82f1b7823f5849d85b3fbc171b8ee19edd` — teste de timestamp de recebimento idêntico.
- `75548693dcdcf75be4484ebd09f62d731663a73b` — teste de testemunha tardia e lista completa de testemunhas.
- HEAD conhecido da branch: `75548693dcdcf75be4484ebd09f62d731663a73b`.

### Validação e limites
- Os arquivos foram gravados diretamente na branch `feat/geyser-unsequenced-raw-audit`; nenhuma alteração foi feita em `main).
- A consulta de execuções CI para o HEAD atual não retornou workflow run. Portanto, **os novos testes e compileall ainda não estão comprovados como executados/aprovados**. Não declarar CI verde nesta revisão.
- Não foi executado benchmark de escala; o rebuild continua materializando deliveries e estruturas auxiliares em memória.
- PR #26 continua Draft, aberta e sem merge; PR #23 continua como branch base não integrada.
- Nenhum provider, RPC, VPS, credencial ou execução on-chain foi conectado.

### Próxima ação
Obter execução verificável dos 14 testes novos, da suíte completa e de `python -m compileall -q src tests`; corrigir qualquer falha antes de considerar a PR pronta. Depois, revisar o versionamento e o desempenho com dados representativos. Não fazer merge sem autorização.

## 298. Correção da expectativa do teste de múltiplas deliveries — 19/11/2026

### Evidência de CI
- Workflow run #1758, run ID `44529355795`, executado no HEAD anterior `ebe84bba4e5e7ed1075e6ba59b4dcfbdef16aa41`, terminou em FAILURE.
- Setup, checkout, instalação do projeto passaram.
- A suíte executou 587 testes; houve uma única falha: `test_multiple_unsequenced_deliveries_are_preserved_individually`.
- Falha exata: `AssertionError: 4 != 3` na expectativa `len(rows) == 3`.
- O cenário cria quatro deliveries: duas sem sequência e duas testemunhas sequenciadas. A auditoria classifica e preserva todas as deliveries individualmente; portanto, quatro linhas são o resultado correto. Não foi identificada falha na regra de reconciliação.

### Correção aplicada
- No teste, expectativa alterada de 3 para 4 linhas.
- Acrescentada asserção explícita de que os quatro `delivery_id` (duas deliveries sem sequência e duas testemunhas) estão presentes na projeção.
- Nenhuma alteração na implementação da auditoria ou na política de reconciliação.
- Commit: `f5dc79b677a70b0a536b3644ba2fcbe5c02f9dc4`.
- PR #26 HEAD atualizado para esse commit; continua Draft, aberta e sem merge.
- `main` permanece intacta.

### Validação e próxima ação
- O run #1758 comprova a falha acima; compileall foi skipped porque a etapa de unit tests falhou.
- A correção foi gravada na branch, mas ainda **não há execução CI confirmada para o novo HEAD**. Não declarar testes ou compileall aprovados.
- Próxima ação: obter novo workflow run para o commit `f5dc79b677a70b0a536b3644ba2fcbe5c02f9dc4`; confirmar os 587 testes e compileall. Se houver nova falha, inspecionar logs antes de alterar código.
- Após CI verde, prosseguir para benchmark de escala/memória da auditoria.
- Não fazer merge sem autorização explícita.

## 299. CI verde após correção da expectativa do teste — 19/11/2026

### Validação comprovada
- Workflow `SMR tests`, run #1760, ID `44548456403`, associado ao commit de correção `f5dc79b677a70b0a536b3644ba2fcbe5c02f9dc4`: SUCCESS.
- Job `test`: SUCCESS.
- Log confirma `Ran 587 tests in 5.029s` e `OK`.
- Etapa `Compile source and tests` executada e concluída com SUCCESS (`python -m compileall -q src tests`).
- A correção de teste foi suficiente; nenhum código de produção foi alterado nesta correção.
- O commit de documentação `1740eaff3684bd1492c56695ef1b0039f8c27e19` foi validado no run #1761, ID `44548513163`: SUCCESS; 587 testes passaram em 4.237s e compileall também concluiu com SUCCESS.

### Estado atualizado
- O commit de código `f5dc79b...` tem suíte completa (587 testes) e compileall aprovados.
- PR #26 continua Draft, aberta e sem merge; `main` intacta.
- Próxima ação: confirmar o resultado do run #1761 para o HEAD com o Registro Mestre atualizado; em seguida iniciar a avaliação de desempenho/memória do rebuild da auditoria, sem alterar a política de evidência.
- Não fazer merge sem autorização explícita.

## 300. Benchmark sintético de escala da auditoria Geyser — 19/11/2026

### Isolamento e método
- Criada branch independente `perf/geyser-audit-benchmark`, partindo do HEAD validado da PR #26 (`f0d63038411cc4207fae910a3ef168e3af443784`). A PR #26 e `main` não foram alteradas.
- Adicionado `tools/benchmark_geyser_unsequenced_audit.py` e workflow `.github/workflows/geyser-audit-benchmark.yml`.
- Workflow #1, run ID `44559378178`, conclusão SUCCESS.
- Fixture sintética determinística gravada diretamente no schema SQLite em transação, para isolar o custo da projeção do overhead de ingestão. Cada evento lógico tem duas deliveries: uma sem sequência e uma testemunha sequenciada em outra stream.
- Métrica de memória: pico de alocações Python observado por `tracemalloc` durante `rebuild()`; não equivale ao RSS total do processo e não inclui o custo de preparação da fixture.
- Sem provider, RPC, dados reais, credenciais ou execução on-chain.

### Resultados observados
| Eventos lógicos | Deliveries | Rebuild | Deliveries/s | Pico Python |
|---:|---:|---:|---:|---:|
| 1.000 | 2.000 | 0,063 s | 31.582,91 | 1,38 MiB |
| 10.000 | 20.000 | 0,644 s | 31.036,27 | 14,35 MiB |
| 50.000 | 100.000 | 3,667 s | 27.273,51 | 75,15 MiB |
| 100.000 | 200.000 | 7,331 s | 27.279,93 | 150,48 MiB |

### Integridade e interpretação
- Todas as quatro escalas terminaram com workflow SUCCESS.
- Classificações esperadas em todas as escalas: uma delivery `SEQUENCED` e uma `UNSEQUENCED_RECONCILED` por evento lógico.
- Contagens RAW permaneceram iguais às da fixture; `PRAGMA integrity_check` retornou `ok` em todas as escalas.
- Throughput caiu de aproximadamente 31,6 mil para 27,3 mil deliveries/s e estabilizou entre 100 mil e 200 mil deliveries no ambiente GitHub Actions usado.
- Memória Python cresceu aproximadamente de forma linear: 75,15 MiB em 100 mil deliveries e 150,48 MiB em 200 mil. Extrapolação linear para milhões de deliveries é apenas indicativa, não uma medição.
- O perfil confirma o custo O(N) em memória já identificado no rebuild atual (lista completa de deliveries, conjuntos auxiliares, mapa de testemunhas e lista de linhas de auditoria). Para uma operação contínua de grande escala, o pico observado justifica otimização antes de conectar produção.
- O tempo medido inclui `tracemalloc` ativo; usar os valores para comparação relativa entre as escalas, não como latência de produção. O benchmark não mede RSS total, concorrência, latência de ingestão, disco sob pressão ou comportamento de provider.

### Próxima decisão técnica
- Não alterar a política nem os critérios de reconciliação.
- Próximo trabalho recomendado: projetar rebuild com memória limitada/streaming e staging SQLite temporário ou tabelas auxiliares transacionais, preservando atomicidade, determinismo e rollback. Evitar apenas reduzir estruturas em memória se isso enfraquecer a auditabilidade.
- Implementar otimização em branch separada, comparar com este baseline nas mesmas escalas e manter teste de equivalência das classificações/IDs de testemunha.
- PR #26 permanece Draft, aberta e sem merge. `main` intacta.
- Artefato JSON do benchmark: run #1, artifact `geyser-audit-benchmark-results`, ID `14546462526`.


## 301. Otimização de memória do rebuild da auditoria Geyser — 19/11/2026

### Decisão e isolamento
- Decisão técnica: avançar com a redução do pico de memória observado no benchmark da seção 300, antes de ampliar escala ou conectar provider.
- Criada branch independente `perf/geyser-audit-bounded-rebuild`, a partir do HEAD do benchmark `6561a66bf45e61ba0783fbe73ae8ee43d4628ba6`.
- PR #26, branch `feat/geyser-unsequenced-raw-audit`, e `main` não foram alteradas. Nenhum merge realizado.

### Implementação inicial
- Modificado `src/smart_money_radar/storage/geyser_unsequenced_delivery_audit.py`.
- O rebuild deixou de carregar todas as deliveries, todos os conflitos/anomalias, o mapa Python de testemunhas e a lista completa de linhas de auditoria em memória.
- Elegibilidade das testemunhas passou a ser materializada em tabela TEMP SQLite indexada pela chave `event_id + source_id + payload_sha256 + delivery_id`, com exclusão SQL de conflitos RAW e anomalias abertas.
- Deliveries são lidas em lotes de 500 via `fetchmany(500)`; cada lote é inserido na tabela de auditoria dentro da mesma transação `BEGIN IMMEDIATE`.
- IDs de testemunhas são consultados por chave e serializados em ordem crescente de `delivery_id`; a sequência continua apenas como referência e nunca é transferida.
- Mantidos o mesmo esquema persistente, política v1, códigos de classificação, checkpoint e commit atômico. Exceções antes do commit devem reverter exclusão, inserções e checkpoint como antes.
- Tabela TEMP e índice são locais à conexão e desaparecem ao fechar; nenhuma tabela RAW, delivery, conflito ou checkpoint de transporte é modificada.

### Testes adicionados
- Adicionado `test_rebuild_streams_across_multiple_delivery_batches`: 501 eventos lógicos, 1.002 deliveries (acima do limite de lote), 501 reconciliações, uma testemunha por delivery reconciliada e `integrity_check == ok`.
- Os 14 testes anteriores da auditoria foram preservados.
- Commit de implementação: `ea4f84965b7b7c41e3b17e461e8bfaca84600cdf`.
- Commit do teste multi-lote: `970ed5efce7a7fb96aed6e993551a3aab90ab8a3`.

### Validação comprovada
- CI `SMR tests` run #1770, ID `44560521402`, no HEAD `4ef7ad0393c2d8796f897274c3b7aaefb7cee6ef`: SUCCESS.
- Log confirma o teste multi-lote e `Ran 588 tests in 6.612s`, `OK`; etapa `python -m compileall -q src tests` concluída com SUCCESS.
- Job `geyser-audit-benchmark` do run #1770: SUCCESS; artefato `geyser-audit-bounded-rebuild-results`, ID `14549585032`.
- Workflow dedicado de benchmark #5, run ID `44560521447`: SUCCESS, mesma fixture e mesmas quatro escalas.

### Comparação com o baseline da seção 300
| Eventos lógicos | Deliveries | Baseline: rebuild | Novo: rebuild | Baseline: pico Python | Novo: pico Python |
|---:|---:|---:|---:|---:|---:|
| 1.000 | 2.000 | 0,063325 s | 0,028314 s | 1,38 MiB | 0,59 MiB |
| 10.000 | 20.000 | 0,644407 s | 0,305129 s | 14,35 MiB | 0,42 MiB |
| 50.000 | 100.000 | 3,666561 s | 1,694234 s | 75,15 MiB | 0,60 MiB |
| 100.000 | 200.000 | 7,331397 s | 3,194474 s | 150,48 MiB | 0,42 MiB |

- Tempo de rebuild melhorou entre 52,6% e 56,4% (aproximadamente 2,1–2,3x mais rápido) nas quatro escalas.
- Pico de alocações Python caiu 57,2% na escala de 2 mil deliveries e entre 97,1% e 99,7% nas três escalas maiores. Na escala de 200 mil deliveries, caiu de 150,48 MiB para 0,42 MiB.
- Em todas as escalas, as classificações permaneceram exatamente as esperadas: uma `SEQUENCED` e uma `UNSEQUENCED_RECONCILED` por evento lógico.
- Contagens RAW de eventos/deliveries permaneceram intactas e `PRAGMA integrity_check` retornou `ok` em todas as escalas.
- O teste adicional atravessou mais de um lote de leitura e verificou 501 reconciliações, testemunhas individuais e integridade SQLite.

### Limites e interpretação
- `tracemalloc` mede alocações Python, não RSS total nem todas as alocações internas do SQLite/C; portanto, 0,42 MiB não representa o consumo total do processo.
- A nova estratégia transfere estruturas de trabalho para tabela TEMP e índice SQLite; o benchmark sintético não mediu espaço temporário em disco, pressão de cache, concorrência, latência de ingestão nem workload real de provider.
- O tempo medido inclui `tracemalloc` ativo e deve ser comparado apenas com o baseline executado sob o mesmo método/runner.
- A lista de IDs testemunhas de um único evento ainda é materializada como JSON em uma string pelo SQLite; cardinalidade extrema por evento permanece uma limitação a testar.
- Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain foi conectado.
- PR #27 continua Draft, aberta e sem merge; PR #26 permanece inalterada e Draft; `main` intacta.
- HEAD de código/testes validado pelo CI #1770: `4ef7ad0393c2d8796f897274c3b7aaefb7cee6ef`; commits posteriores alteraram somente o Registro Mestre.
- Verificação GitHub: PR #27 OPEN/DRAFT, `merged=false`, base `feat/geyser-unsequenced-raw-audit`; PR #26 OPEN/DRAFT, `merged=false`, HEAD preservado em `f0d63038411cc4207fae910a3ef168e3af443784`; `main` preservada em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

### Próxima ação
- Obter CI verde no HEAD atual (suíte completa e compileall); corrigir falhas com evidência antes de benchmark.
- Depois executar o mesmo benchmark da seção 300, nas mesmas quatro escalas, comparar tempo e pico Python e validar classificações, IDs de testemunhas, contagens RAW e integridade SQLite.
- Manter esta branch isolada; não fazer merge nem alterar PR #26 ou `main` sem nova decisão explícita.


## 302. Cardinalidade de testemunhas, RSS e alocação TEMP SQLite — 19/11/2026
> **Nota de correção (seção 303):** os valores `process_rss_peak_mib` desta seção, calculados com `resource.getrusage().ru_maxrss`, foram contaminados pelo high-water mark do processo pai que preparou a fixture antes de iniciar o subprocesso. Portanto, os números de 87,12 MiB não representam o pico exclusivo do worker de rebuild e estão supersedidos pela medição `/proc/self/status` da seção 303. Os valores `tracemalloc` e TEMP SQLite continuam sendo medições independentes.


### Objetivo e alterações
- Continuação autorizada da revisão da otimização da auditoria Geyser na branch isolada `perf/geyser-audit-bounded-rebuild`.
- Adicionada métrica `last_rebuild_metrics` no auditor para observar páginas e bytes alocados no banco TEMP SQLite após materialização da tabela/índice de testemunhas. Métrica é diagnóstica e não altera schema persistente nem retorno de `rebuild()`.
- Benchmark passou a executar o rebuild em processo filho isolado após a preparação da fixture, medindo `ru_maxrss` (RSS high-water mark) sem incluir a memória usada pelo processo pai para semear o banco.
- Benchmark também mede páginas TEMP SQLite (`PRAGMA temp.page_count * temp.page_size`) e adiciona cenário de fanout com um evento lógico, uma delivery sem sequência e 10.000 testemunhas sequenciadas.
- Adicionado teste `test_high_cardinality_witnesses_are_complete_and_sorted`: uma delivery sem sequência e 4.096 testemunhas; confirma todos os IDs, ordenação crescente, nenhuma transferência de sequência e integridade RAW/SQLite.
- Teste de rollback fortalecido: após falha forçada na inserção da nova geração, compara todas as linhas projetadas anteriores, checkpoint, contagens RAW e `integrity_check`.
- Removido job de benchmark duplicado do workflow de testes; benchmark permanece no workflow dedicado `.github/workflows/geyser-audit-benchmark.yml`.

### CI e artefato
- PR CI #1786, run ID `44561492702`, HEAD `e3763dd47f6ede8b5dfc3fc16b8ec11fc6f835e7`: SUCCESS.
- Log confirma `test_high_cardinality_witnesses_are_complete_and_sorted ... ok`, `Ran 589 tests in 6.388s`, `OK`; `python -m compileall -q src tests` executado com sucesso.
- Workflow dedicado Geyser audit benchmark #19, run ID `44561492784`: SUCCESS.
- Artefato `geyser-audit-benchmark-results`, ID `14550045706`, disponível até 2027-02-17.

### Medições no processo isolado
| Eventos lógicos | Deliveries | RSS pico do processo | TEMP SQLite alocado | Pico tracemalloc | Rebuild |
|---:|---:|---:|---:|---:|---:|
| 1.000 | 2.000 | 25,77 MiB | 253.952 B | 0,59 MiB | 0,048756 s |
| 10.000 | 20.000 | 31,42 MiB | 2.428.928 B | 0,59 MiB | 0,514730 s |
| 50.000 | 100.000 | 55,80 MiB | 12.156.928 B | 0,60 MiB | 2,641332 s |
| 100.000 | 200.000 | 87,12 MiB | 24.399.872 B | 0,60 MiB | 5,300452 s |

### Fanout de alta cardinalidade
- Cenário sintético: 1 evento lógico, 1 delivery sem sequência e 10.000 deliveries sequenciadas elegíveis.
- Resultado: 10.000 IDs de testemunha completos e ordenados; 10.001 deliveries RAW preservadas; `integrity_check == ok`.
- Rebuild: 0,305554 s; pico `tracemalloc`: 0,61 MiB; RSS high-water mark: 87,12 MiB; alocação TEMP SQLite: 510 páginas × 4.096 bytes = 2.088.960 bytes (~1,99 MiB).
- O teste unitário independente com 4.096 testemunhas também passou.

### Interpretação e limites
- `ru_maxrss` é o pico residente do processo filho que executou o rebuild; a preparação da fixture foi feita no processo pai e não compõe esse pico. É uma medida de processo no runner Linux, não uma medição em Android/Termux nem em produção.
- `temp_db_allocated_bytes` mede páginas do banco TEMP SQLite no ponto instrumentado; não deve ser interpretado automaticamente como bytes físicos gravados em disco. O modo efetivo de armazenamento temporário, I/O físico e comportamento sob pressão de disco/cache ainda precisam de medição específica.
- A memória Python permaneceu próxima de 0,6 MiB, mas RSS chegou a 87,12 MiB nas escalas maiores e no fanout de 10 mil. Isso demonstra que `tracemalloc` sozinho não representa o custo total; a atribuição detalhada do RSS entre SQLite, alocadores nativos e cache ainda não foi estabelecida.
- O fanout de 10 mil não perdeu nem reordenou testemunhas, mas continua exigindo materialização de um JSON completo por delivery sem sequência. Não aumentar esse limite sem testar limites de tamanho, cardinalidade extrema e custos nativos.
- Tempos variaram em relação ao benchmark anterior; runner compartilhado/contenda e método isolado mudaram. Não usar estes tempos como comparação direta com a tabela da seção 301.
- Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain foi conectado.

### Estado e próxima ação
- PR #27 permanece OPEN/DRAFT, `merged=false`; PR #26 permanece OPEN/DRAFT e sem alteração; `main` permanece intacta.
- HEAD atual da PR #27: `03c2c425b451c35427b656e0e6f2626bcf9a9023`; CI #1786 e benchmark #19 validaram o commit de código/workflows `e3763dd47f6ede8b5dfc3fc16b8ec11fc6f835e7`; o commit posterior `03c2c42...` atualizou somente o Registro Mestre.
- HEAD de código/testes e workflows validado pelo CI: `e3763dd47f6ede8b5dfc3fc16b8ec11fc6f835e7`.
- Próxima revisão técnica: investigar a diferença entre o pico RSS (~87 MiB) e `tracemalloc` (~0,6 MiB), além de medir se TEMP SQLite está em memória ou em arquivo no runner e como o comportamento varia com cache/disco. Preservar a serialização completa, ordenação, atomicidade e rollback.
- Não fazer merge sem revisão e aprovação explícitas.


## 303. Correção de RSS e diagnóstico do armazenamento TEMP SQLite — 19/11/2026

### Correção metodológica
- Investigação identificou que `resource.getrusage(RUSAGE_SELF).ru_maxrss` no subprocesso não era uma medida confiável para este benchmark: o valor reportado estava contaminado pelo high-water mark do processo pai que semeava a fixture antes de chamar `subprocess.run`.
- Os valores anteriores de 87–95 MiB não devem ser atribuídos ao rebuild nem ao SQLite. A seção 302 foi anotada para marcar essa medição como supersedida.
- Benchmark corrigido para usar `VmHWM` de `/proc/self/status` e snapshots de `VmRSS`, `smaps_rollup:Rss`, `Pss` e `Private_Dirty` dentro do próprio worker. Assim, o high-water mark é lido no espaço de processo do worker, sem a métrica herdada do pai.
- Adicionado parâmetro opcional `temp_store=None|"FILE"|"MEMORY"` ao auditor. O padrão continua sem override; opções explícitas são aplicadas por conexão antes da criação de objetos TEMP. Valores não suportados são rejeitados.
- Benchmark compara DEFAULT, FILE e MEMORY em 100.000 eventos lógicos / 200.000 deliveries; as classificações, contagens RAW e integridade são verificadas em todos os modos.
- Testes cobrem FILE, MEMORY e rejeição de modo inválido.

### Evidência de modo TEMP
- Opções de compilação SQLite do runner: `TEMP_STORE=1` e `DEFAULT_CACHE_SIZE=-2000`.
- Com `PRAGMA temp_store=0` (DEFAULT), o SQLite usa o default compilado `TEMP_STORE=1`, isto é, armazenamento TEMP baseado em arquivo.
- Override FILE resulta em `PRAGMA temp_store=1`; override MEMORY resulta em `PRAGMA temp_store=2`.
- O tamanho de TEMP no cenário de 200.000 deliveries foi 5.957 páginas × 4.096 bytes = 24.399.872 bytes (~23,27 MiB). Isso mede páginas alocadas pela base TEMP; não é medição direta de bytes físicos gravados no dispositivo nem prova de que o filesystem subjacente não seja tmpfs.

### RSS corrigido e comparação de modos
| Modo TEMP | RSS pico real do worker (VmHWM) | RSS antes | RSS depois | Rebuild | Throughput |
|---|---:|---:|---:|---:|---:|
| DEFAULT (TEMP_STORE=1) | 28,91 MiB | 23,00 MiB | 28,79 MiB | 5,565 s | 35.937,55 deliveries/s |
| FILE | 29,06 MiB | 23,03 MiB | 28,83 MiB | 5,622 s | 35.573,77 deliveries/s |
| MEMORY | 53,24 MiB | 22,98 MiB | 53,24 MiB | 5,543 s | 36.080,69 deliveries/s |

- Os tempos acima são uma execução no runner compartilhado e não sustentam diferença de performance significativa entre os modos.
- MEMORY elevou o RSS em aproximadamente 24 MiB adicionais em relação ao modo FILE/DEFAULT, sem ganho de velocidade mensurável. Não adotar MEMORY como padrão.
- Para 200.000 deliveries no cenário principal, DEFAULT apresentou `VmHWM=29,0 MiB`, `VmRSS` pós-rebuild ~28,8 MiB, TEMP de 24.399.872 bytes e `tracemalloc=0,60 MiB`.
- Fanout de 10.000 testemunhas: 10.001 deliveries; `VmHWM=28,70 MiB`, `VmRSS` pós-rebuild ~28,8 MiB, TEMP 2.088.960 bytes (~1,99 MiB), `tracemalloc=0,60 MiB`, 10.000 IDs completos/ordenados e `integrity_check=ok`.
- O incremento de RSS no modo DEFAULT/FILE foi de cerca de 5,8 MiB sobre o processo inicial (~23 MiB), enquanto MEMORY reteve cerca de 30 MiB adicionais. Isso é compatível com TEMP em arquivo no runner e TEMP em memória no modo explícito.

### Validação
- CI SMR tests #1800, run ID `44562544337`, HEAD `d78b7dceafedad8a596156dfb42dbf80330d83c7`: SUCCESS.
- Log: `Ran 591 tests in 6.343s`, `OK`; `python -m compileall -q src tests` SUCCESS.
- Geyser audit benchmark #29, run ID `44562529547`, mesmo HEAD: SUCCESS.
- Artefato `geyser-audit-benchmark-results`, ID `14550116560`, disponível até 2027-02-17.
- Nenhuma alteração na política de reconciliação; RAW e resultados de classificação permaneceram íntegros nos três modos.

### Conclusão e estado
- O pico anterior de 87–95 MiB era artefato de medição, não evidência de consumo real do rebuild.
- No runner Linux, o modo TEMP padrão efetivo é FILE e o rebuild manteve RSS de pico próximo a 29 MiB em 200.000 deliveries. O modo MEMORY aumenta RSS para ~53 MiB sem ganho de throughput relevante.
- Manter DEFAULT (SQLite file-backed TEMP) como comportamento padrão; não mudar para MEMORY.
- A evidência não mede RSS em Android/Termux, VPS ou produção, nem confirma se o diretório temporário do runner está num filesystem físico ou tmpfs.
- PR #27 permanece OPEN/DRAFT, sem merge; PR #26 e `main` não foram alteradas.
- HEAD de código/testes/benchmark validado: `d78b7dceafedad8a596156dfb42dbf80330d83c7`; commits de registro posteriores, se houver, devem ser identificados separadamente.
- Próxima ação: revisão final de implementação e documentação, especialmente validar o parâmetro opcional TEMP_STORE e decidir se ele permanece como opção diagnóstica ou é removido após o experimento. Nenhum merge sem aprovação explícita.


## 304. Revisão de integração da auditoria Geyser — 19/11/2026

### Ajustes autorizados e implementados na branch isolada
- Removido o parâmetro `temp_store` do construtor operacional de `SQLiteGeyserUnsequencedDeliveryAudit`; a auditoria usa o default SQLite sem override operacional.
- A comparação DEFAULT/FILE/MEMORY permanece exclusivamente no benchmark, por meio de uma subclasse privada `_BenchmarkAudit`; nenhum modo de armazenamento temporário é exposto pela API do produto.
- Removidos os testes de configuração TEMP operacional e substituídos por teste que confirma que o construtor rejeita esse argumento.
- Adicionado teste concorrente com duas instâncias e barreira sincronizada; ambas executam rebuild no mesmo banco, devem serializar via `BEGIN IMMEDIATE`, produzir gerações 1 e 2 e preservar contagens/integridade RAW.
- Removida a chave duplicada `temp_store_requested` no resultado do worker.
- Documentado que `VmHWM` mede o high-water mark durante toda a vida do worker isolado (incluindo imports e construção do auditor), não o pico exclusivo de `rebuild()`. O isolamento elimina a contaminação do processo pai, mas não isola o rebuild de toda a memória anterior do próprio worker.

### Validação desta revisão
- Commit de código/testes/benchmark validado: `7ff820e966b67b8f65a05bf07a992f44a4c5d8b6`.
- CI SMR tests #? — run ID `44564297986`: SUCCESS; inclui o teste concorrente de duas reconstruções e a suíte completa.
- Geyser audit benchmark #? — run ID `44564298047`: SUCCESS; artefato `geyser-audit-benchmark-results`, ID `14551905844`, disponível até 2027-02-17.
- Execuções anteriores de CI falharam durante a própria revisão por dois erros introduzidos nas edições (import `threading` ausente e quebra de linha literal no benchmark); ambos foram corrigidos. A validação final acima é a execução posterior às correções.
- `VmHWM` é descrito como high-water mark do worker inteiro, não como pico exclusivo de `rebuild()`.
- Nenhuma alteração à política de reconciliação, tabelas RAW ou Timeline.
- PR #27 permanece OPEN/DRAFT e sem merge. PR #26 e `main` não foram modificadas.
- Próxima ação: revisão final do diff atualizado e conferência do resultado agregado da PR antes de qualquer proposta de integração. Nenhum merge sem aprovação explícita.


## 305. Revisão de integração PR #26 + PR #27 — 19/11/2026

### Estado da cadeia de branches confirmado
- PR #23 permanece OPEN/DRAFT, sem merge; base `feat/damm-v2-referral-transfer-attribution`, HEAD `4a517ca15499746ddd3f5522f112c80aaac1433b`.
- PR #26 permanece OPEN/DRAFT, `merged=false`; base `feat/damm-v2-economic-reconciliation` (HEAD base `4a517ca15499746ddd3f5522f112c80aaac1433b`), HEAD `f0d63038411cc4207fae910a3ef168e3af443784`.
- PR #27 permanece OPEN/DRAFT, `merged=false`; base `feat/geyser-unsequenced-raw-audit`, e seu `base_sha` coincide exatamente com o HEAD da PR #26 (`f0d63038411cc4207fae910a3ef168e3af443784`); HEAD documental consultado `56190344951bf65112c8190178b56ca6a855f7d4`.
- A cadeia de PRs está corretamente empilhada: PR #27 adiciona a otimização sobre a implementação da PR #26, que por sua vez depende da PR #23. Nenhuma alteração em `main`; nenhum merge executado.

### Revisão da compatibilidade entre auditoria e otimização
- PR #27 altera o rebuild da projeção, mas preserva o contrato persistente, a policy ID `geyser-unsequenced-delivery:v1`, os códigos de classificação e a regra de reconciliação da PR #26.
- A tabela TEMP indexada materializa somente testemunhas sequenciadas sem conflito de identidade e sem anomalia de transporte aberta; a chave continua `event_id + source_id + payload_sha256`, sem incluir `stream_id`.
- Entregas são lidas em lotes de 500; testemunhas são consultadas por chave e ordenadas por `delivery_id`; IDs completos são serializados sem transferir sequência à delivery não sequenciada.
- `BEGIN IMMEDIATE`, substituição da projeção e atualização do checkpoint permanecem na mesma transação. O teste concorrente verifica duas instâncias serializadas e gerações sucessivas; o teste de rollback compara linhas projetadas, checkpoint, contagens RAW e integridade.
- O benchmark permanece fora da API operacional. Não foi identificada alteração de RAW, deliveries, conflitos, checkpoints de transporte ou contrato de Timeline pelo código da PR #27.
- Validações finais de código/testes/benchmark já registradas na seção 304 continuam válidas para o commit de código validado; esta revisão não repetiu CI nem benchmark.

### Achado de integração — Timeline não filtra todas as deliveries inelegíveis
- Arquivo: `src/smart_money_radar/storage/geyser_account_timeline_projection.py`, método `SQLiteGeyserAccountTimelineProjection.rebuild()`.
- A consulta atual seleciona a delivery por `MIN(delivery_id)` com a única condição `d2.stream_sequence IS NOT NULL`. Ela não filtra `conflict_id`, conflitos em `geyser_raw_conflicts` nem anomalias abertas em `geyser_transport_anomalies`.
- Em contraste, a auditoria da PR #26 classifica deliveries com conflito de identidade como `IDENTITY_CONFLICT` e deliveries sequenciadas afetadas por anomalia aberta como `SEQUENCE_ANOMALY`; nenhuma delas é testemunha elegível para reconciliar uma delivery sem sequência.
- Consequência: uma delivery sequenciada que a auditoria considera inelegível ainda pode ser escolhida pela Timeline. Se houver uma delivery inelegível com menor `delivery_id`, a seleção também pode preferi-la a uma delivery sequenciada elegível posterior.
- O teste adicionado na PR #26 comprova que uma delivery sem sequência não entra na Timeline, mas não cobre a exclusão de deliveries sequenciadas com conflito RAW ou anomalia aberta.
- O achado é uma lacuna de integração entre a política aprovada e a projeção Timeline preexistente; não é defeito introduzido pela otimização da PR #27. A consulta e os testes de Timeline precisam ser ajustados para consumir a mesma regra de elegibilidade (ou predicado compartilhado equivalente), preservando o isolamento da auditoria e sem transferir sequência.

### Conclusão e próxima ação
- A otimização da PR #27 é compatível com o contrato de auditoria da PR #26 na revisão estática realizada; a cadeia de branches está corretamente empilhada.
- **Integração ainda não pode ser considerada totalmente aprovada** enquanto a Timeline puder selecionar deliveries sequenciadas com conflito RAW ou anomalia aberta.
- Próxima ação recomendada: preparar uma correção isolada para a elegibilidade da Timeline, com testes que demonstrem exclusão de conflito RAW e anomalia aberta, e teste que escolha uma delivery elegível posterior quando a primeira sequenciada for inelegível. Reexecutar CI somente na branch que receber essa correção.
- PR #23, #26 e #27 permanecem OPEN/DRAFT e sem merge. `main` permanece intacta. Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain foi conectado.


## 306. Correção de elegibilidade da Timeline Geyser — PR #28 — 19/11/2026

### Branch e PR
- Branch isolada: `fix/geyser-timeline-delivery-eligibility`.
- Base exata: HEAD da PR #26, `f0d63038411cc4207fae910a3ef168e3af443784`.
- PR #28: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/28
- Título: `fix(geyser): enforce delivery eligibility in account timeline`.
- PR aberta como Draft; sem merge. A PR #27 permanece paralela, também baseada na PR #26.
- A correção não altera `main`, RAW, deliveries, checkpoints de transporte nem a projeção separada de auditoria.

### Implementação
Arquivo `src/smart_money_radar/storage/geyser_account_timeline_projection.py`:
- A subconsulta de seleção da delivery agora exige `d2.source_id=e.source_id`.
- Exige `stream_sequence IS NOT NULL`.
- Exclui delivery com `conflict_id IS NOT NULL`.
- Exclui todos os eventos com qualquer registro em `geyser_raw_conflicts`.
- Exclui delivery cuja chave exata `source_id + stream_id + stream_sequence` tenha anomalia de transporte em estado `OPEN`.
- A seleção continua usando o menor `delivery_id` **entre as deliveries elegíveis**. Se a primeira delivery sequenciada for inelegível, uma reentrega posterior elegível do mesmo evento pode ser escolhida.
- Nenhuma sequência é transferida; a Timeline decodifica a delivery que efetivamente passou pelo predicado de elegibilidade.

### Testes de regressão adicionados
Arquivo `tests/test_geyser_account_timeline_projection.py`:
1. `test_raw_identity_conflict_excludes_event_from_timeline`: evento com conflito RAW não gera account write na Timeline.
2. `test_open_transport_anomaly_skips_first_delivery_for_later_eligible_replay`: delivery inicial com anomalia aberta é ignorada; reentrega idêntica em outra stream, sequenciada e elegível, é selecionada. A continuidade com o evento anterior da stream elegível é preservada, sem criar baseline artificial.
- Os testes anteriores de continuidade, gaps, bank lineage, recuperação e rollback permanecem no conjunto.

### CI comprovada
- Workflow `SMR tests`, run #1815, ID `44577404211`, commit de código/testes `cd070c47661582f0ea2c7566c4b7ac17585268fc`: SUCCESS.
- Job `test`: instalação concluída, suíte completa `Ran 589 tests in 4.952s — OK`; `compileall -q src tests` também concluído com sucesso.
- Run #1814, ID `44577367109`, commit anterior de implementação `81f61281f864151a30f56aa0fa75a7cbcc566ab8`: SUCCESS.
- A atualização documental posterior não altera código nem testes; não exige nova execução de CI.

### Estado e pendências
- PR #28 é uma correção isolada e validada por CI para o achado da seção 305.
- Revisão final concluída: PR #28 permanece OPEN/DRAFT, `merged=false`, `mergeable=true`; base SHA coincide com o HEAD da PR #26. O workflow PR #28 run ID `44577550530` também concluiu SUCCESS no HEAD documental `abc8a1a591f65d0dc525c2cf633fa6b6524fce50`.
- PR #23, #26, #27 e #28 permanecem sem merge. `main` intacta.
- Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain conectado.



## 307. Revisão conjunta de arquitetura e integração das PRs Geyser #26, #27 e #28 — 19/11/2026

### Escopo e resultado
- Revisadas em conjunto a política/auditoria RAW sem sequência (PR #26), a otimização de rebuild em lotes e TEMP SQLite (PR #27) e a elegibilidade da Account Timeline (PR #28).
- Resultado: **nenhuma divergência semântica bloqueadora identificada** entre a política de reconciliação, o conjunto de testemunhas elegíveis e o predicado de seleção da Timeline.
- A otimização da PR #27 preserva o contrato da PR #26. A PR #28 corrige a seleção da Timeline sem alterar RAW nem a auditoria.
- Revisão não autoriza merge. Todas as PRs permanecem Draft/abertas; main permanece intacta.

### Equivalência semântica auditada
A PR #26 e a versão otimizada da PR #27 selecionam testemunhas sequenciadas com os mesmos requisitos:
- `stream_sequence IS NOT NULL`;
- `event_id` não nulo e evento RAW existente;
- `delivery.conflict_id IS NULL`;
- `event.source_id = delivery.source_id`;
- hash RAW não nulo;
- nenhum conflito RAW associado ao `event_id`;
- nenhuma anomalia de transporte OPEN para a chave exata `source_id + stream_id + stream_sequence`.

A Timeline da PR #28 aplica o mesmo núcleo de elegibilidade para a delivery efetivamente projetada: sequência presente, fonte igual à do evento, sem `conflict_id`, sem conflito RAW do evento e sem anomalia OPEN na chave exata da delivery. O schema RAW declara `payload_sha256 NOT NULL`, portanto a ausência de filtro explícito de hash na Timeline não cria uma classe divergente no schema atual.

Precedência e efeito:
- Conflito de identidade impede projeção/reconciliação; a Timeline exclui o evento e a auditoria classifica `IDENTITY_CONFLICT`.
- Anomalia OPEN impede que a delivery seja testemunha/projetada; a auditoria classifica delivery sequenciada afetada como `SEQUENCE_ANOMALY`.
- Delivery sem sequência continua sem sequência; pode ser `UNSEQUENCED_RECONCILED` apenas por referência a testemunhas elegíveis, nunca pela transferência de sequência.
- A Timeline seleciona o menor `delivery_id` entre deliveries elegíveis, permitindo replay elegível posterior quando uma delivery anterior é inelegível.
- `COMPLETE/PARTIAL/UNKNOWN` e checkpoints de transporte não são reescritos pela auditoria.

### Revisão da otimização PR #27
- TEMP table é conexão-local e materializa somente testemunhas elegíveis; índice usa `event_id + source_id + payload_sha256 + delivery_id`.
- Leitura da auditoria é feita com `fetchmany(500)`; gravação em lotes mantém o working set de Python limitado.
- Consulta das testemunhas preserva todos os IDs em ordem determinística; nenhuma sequência é transferida.
- `BEGIN IMMEDIATE` envolve rebuild, projeção e checkpoint; a falha reverte a geração/checkpoint. Testes cobrem rollback e concorrência entre instâncias.
- A otimização não muda `POLICY_ID`, classificações, códigos de motivo ou schema persistente.
- Benchmarks e limites de interpretação permanecem os da seção 304: fixture sintética, runner compartilhado, VmHWM do worker inteiro, não métrica exclusiva do rebuild nem previsão de produção.

### Integração entre branches
- PR #26: base `feat/damm-v2-economic-reconciliation` em `4a517ca15499746ddd3f5522f112c80aaac1433b`; HEAD `f0d63038411cc4207fae910a3ef168e3af443784`.
- PR #27: base PR #26 em `f0d63038411cc4207fae910a3ef168e3af443784`; HEAD `d281daea02dc8d93c7159c5095d8a47579becf7c`.
- PR #28: base PR #26 em `f0d63038411cc4207fae910a3ef168e3af443784`; HEAD documental antes deste registro `b6cd259f6cc2e08dd9238ef72b27a4633cb85c92`.
- Os arquivos de código e testes de PR #27 e #28 não se sobrepõem. Ambas alteram `REGISTRO-MESTRE-SMR.md`; portanto, apesar de cada PR estar individualmente mergeable contra a base atual, a integração conjunta exige rebase/atualização e resolução do histórico documental. Não tratar o estado `mergeable=true` individual como prova de que as duas podem ser integradas em sequência sem ajuste.
- Sequência recomendada para futura integração: manter PR #26 como base; integrar uma PR filha por vez, atualizar/rebasear a outra sobre a base avançada, resolver o Registro Mestre e validar o diff combinado antes de seguir. A ordem entre #27 e #28 pode ser escolhida na etapa de integração; não há dependência de código entre elas.
- PR #23 permanece ancestral/base acima da PR #26; sua integração continua separada.

### Evidências atuais de CI e estado remoto
- PR #26 HEAD `f0d63038411cc4207fae910a3ef168e3af443784`: check-run `test` SUCCESS, run ID `44548677924`.
- PR #27 HEAD `d281daea02dc8d93c7159c5095d8a47579becf7c`: check-runs `test` e `benchmark` SUCCESS, IDs `44574595397` e `44574595312`.
- PR #28 HEAD anterior a este commit documental `b6cd259f6cc2e08dd9238ef72b27a4633cb85c92`: check-run `test` SUCCESS, run ID `44577659605`.
- PR #26, #27 e #28 estavam OPEN/DRAFT, `merged=false`, `mergeable=true` em consulta individual. PR #27 e #28 baseadas no mesmo HEAD da PR #26.
- `main` confirmada em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; sem alteração.
- Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain conectado.

### Pendências reais e próxima ação
1. Não há correção de código adicional exigida pela revisão conjunta atual.
2. Antes de qualquer merge, executar integração controlada das PRs filhas na branch-base da PR #26, resolvendo o conflito potencial do Registro Mestre e revisando o diff combinado.
3. Depois, validar a PR #26 resultante contra sua base PR #23; só então decidir a integração posterior com PR #23.
4. Não fazer merge de nenhuma PR sem ordem explícita do usuário.

## 308. Atualização 2026-11-19 — integração controlada PR #27 + PR #28 validada

### Branch temporária e escopo
- Branch: `integration/geyser-pr27-pr28`.
- PR temporária #29: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/29.
- Base exata: PR #26 / branch `feat/geyser-unsequenced-raw-audit`, SHA `f0d63038411cc4207fae910a3ef168e3af443784`.
- HEAD validado: `1512c47113f34fcd184cd6813d3da5158d094820`.
- PR #29 permanece OPEN/DRAFT, `merged=false), `mergeable=true). A descrição identifica a PR como validação temporária e instrui não fazer merge.
- Diff combinado: 8 arquivos, 1.027 adições e 74 remoções.
- Arquivos combinados: workflow de benchmark, workflow SMR tests, auditoria de deliveries Geyser sem sequência, testes da auditoria, ferramenta de benchmark, projeção Timeline de conta, testes da Timeline e Registro Mestre com seções 300–307.
- PRs #26, #27 e #28 originais não foram modificadas por esta integração controlada.

### Validação CI no mesmo HEAD
- Workflow SMR tests: run `44580544704`, SUCCESS. Log confirma `Ran 593 tests`, resultado OK, e `python -m compileall -q src tests` aprovado.
- Workflow Geyser audit benchmark: run `44580544811`, SUCCESS. Job `benchmark`, execução do benchmark sintético e upload do artefato concluídos com sucesso.
- Ambos os workflows foram disparados para o mesmo HEAD `1512c47113f34fcd184cd6813d3da5158d094820`; nenhuma nova execução manual foi necessária.
- Artefato: `geyser-audit-benchmark-results`, ID `14559085293`, SHA-256 `c3ced6ec55bf5c394cfc5ac3bd2b7e35319b1001cf51bce64682b2c0faa0e391`, expiração indicada 2027-02-17. ZIP baixado e conteúdo JSON inspecionado.

### Resultado técnico do benchmark integrado
- Fixture sintética principal: 100.000 eventos lógicos / 200.000 deliveries; classificação: 100.000 `SEQUENCED` e 100.000 `UNSEQUENCED_RECONCILED`; SQLite `integrity_check=ok).
- Modo DEFAULT na comparação: 5,978 s, 33.456,54 deliveries/s, pico RSS 28,97 MiB.
- Modo FILE: 5,827 s, 34.323,01 deliveries/s, pico RSS 28,88 MiB.
- Modo MEMORY: 5,801 s, 34.478,41 deliveries/s, pico RSS 53,37 MiB.
- O modo MEMORY elevou o pico RSS em aproximadamente 24,4 MiB frente ao DEFAULT, para ganho de throughput inferior a 4%; não há justificativa demonstrada para adotá-lo como padrão.
- Fanout alto: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,220 s, pico RSS 28,8 MiB, `integrity_check=ok`.
- Em outro cenário de escala, 200.000 deliveries foram reconstruídas em 5,850 s (~34.189,51 deliveries/s), pico RSS 28,91 MiB e `integrity_check=ok`.
- Interpretação: evidência sintética em runner Linux/GitHub Actions; não é benchmark de Termux, VPS ou produção, não comprova bytes físicos escritos nem filesystem efetivo em produção. VmHWM/RSS representa o worker, não exclusivamente o rebuild.
- Recomendação mantida: DEFAULT/file-backed; não alterar sem medição representativa no ambiente-alvo.

### Estado remoto após validação
- PR #26: OPEN/DRAFT, não mergeada, base PR #23 em `4a517ca15499746ddd3f5522f112c80aaac1433b`, HEAD `f0d63038411cc4207fae910a3ef168e3af443784`, mergeable.
- PR #27: OPEN/DRAFT, não mergeada, base PR #26, HEAD `d281daea02dc8d93c7159c5095d8a47579becf7c`, mergeable.
- PR #28: OPEN/DRAFT, não mergeada, base PR #26, HEAD `61ecdde08e66a6707e13ceb09fd54372e672c859`, mergeable.
- PR #29: OPEN/DRAFT, não mergeada, base PR #26, HEAD `1512c47113f34fcd184cd6813d3da5158d094820`, mergeable; exclusivamente temporária.
- `main` confirmada intacta em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Nenhum merge foi executado. Nenhum RPC/provider, credencial, VPS, dado real ou execução on-chain foi conectado.

### Conclusão e próxima ação
- A integração conjunta de código/testes das PRs #27 e #28 sobre a base #26 passou em CI e benchmark; não foi encontrada falha de integração nesta validação.
- Isso valida o conjunto combinado no HEAD da PR #29, mas não autoriza merge automático das PRs originais nem transforma a PR temporária #29 em PR final.
- Próxima etapa: revisão final do diff combinado e escolha explícita da estratégia de integração permanente. Preservar a base ancestral PR #23/#26 e resolver a documentação sem duplicar seções. Depois da decisão, validar o HEAD final da branch de integração permanente e só então solicitar autorização específica para merge.
- Não fechar nem mergear a PR #29 nesta etapa; mantê-la como evidência reproduzível até a decisão sobre integração permanente.

## 309. Validação final do HEAD documental da integração Geyser — 19/11/2026

### CI no HEAD atualizado
- Após registrar a seção 308, o commit 267f7512871d8bbab1414822413c2c11da18264c disparou automaticamente nova execução de ambos os workflows.
- SMR tests: run 44581283469, job test SUCCESS. Log confirma Ran 593 tests in 5.319s; python -m compileall -q src tests concluiu com sucesso. Nenhuma falha.
- Geyser audit benchmark: run 44581283368, job benchmark SUCCESS. Benchmark sintético e upload do artefato concluídos com sucesso.
- Ambos os workflows apontam para o mesmo HEAD 267f7512871d8bbab1414822413c2c11da18264c.

### Benchmark e artefato da execução final
- Artefato geyser-audit-benchmark-results, ID 14559665298, SHA-256 457084e0646e213ae0e0a6f90241af59321c70fb02e9a2e0725d2035517b45a0, expiração indicada 2027-02-17. ZIP baixado e JSON interno inspecionado.
- Escala principal de 100.000 eventos lógicos / 200.000 deliveries: rebuild 4,997681 s, throughput 40.018,56 deliveries/s, pico RSS do worker 28,99 MiB, TEMP SQLite 24.399.872 bytes, tracemalloc 0,60 MiB; 100.000 classificações SEQUENCED e 100.000 UNSEQUENCED_RECONCILED; contagens RAW preservadas e integrity_check=["ok"].
- Fanout: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,199967 s, pico RSS 28,90 MiB, TEMP SQLite 2.088.960 bytes, 10.000 IDs completos e ordenados, integrity_check=["ok"].
- Comparação de TEMP em 100.000 eventos: DEFAULT 5,014738 s / 28,98 MiB RSS; FILE 4,986653 s / 28,95 MiB; MEMORY 5,005368 s / 53,37 MiB. Não há ganho de velocidade material do modo MEMORY; mantém-se DEFAULT/file-backed.
- Em todas as quatro escalas (2 mil, 20 mil, 100 mil e 200 mil deliveries), classificações esperadas, contagens RAW e integridade SQLite passaram.
- Limite: fixture sintética em runner Linux/GitHub Actions. RSS inclui vida útil do worker (imports/construção), não apenas rebuild; TEMP pages são alocação lógica SQLite, não medição de bytes físicos escritos. Não extrapolar diretamente para Termux/VPS/produção.

### Revisão do diff e estado remoto
- Revisão do diff combinado confirmou que o rebuild da auditoria usa TEMP table/index local à conexão, leitura em lotes de 500, transação BEGIN IMMEDIATE, inserção em lotes, IDs de testemunhas ordenados e nenhuma transferência de sequência. A Timeline escolhe a menor delivery_id entre deliveries sequenciadas elegíveis, exigindo mesma fonte, ausência de conflito RAW e ausência de anomalia OPEN na chave exata da delivery.
- Os testes integrados cobrem lote acima de 500, fanout de 4.096 testemunhas, rollback, concorrência de rebuilds, conflito RAW e replay elegível posterior quando a primeira delivery é inelegível.
- PR #29 permanece OPEN/DRAFT, merged=false, mergeable=true, base feat/geyser-unsequenced-raw-audit em f0d63038411cc4207fae910a3ef168e3af443784, HEAD 267f7512871d8bbab1414822413c2c11da18264c, diff 8 arquivos (+1.070/-74).
- PRs #26, #27 e #28 permanecem OPEN/DRAFT e não mergeadas; seus HEADs não foram alterados por esta revisão.
- Branch integration/geyser-pr27-pr28 aponta para 267f7512871d8bbab1414822413c2c11da18264c; main continua intacta em 5060bc65ddf181a4736fdb662c44c3fec0dd7259.
- Nenhum merge foi executado. Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain foi conectado.

### Conclusão e próximo passo
- A combinação PR #27 + PR #28 sobre a base PR #26 passou na suíte completa, compilação, benchmark e revisão do diff no HEAD 267f751...
- A integração está tecnicamente validada no ambiente CI, mas ainda não foi integrada permanentemente à cadeia de PRs nem à main.
- Próxima etapa: preparar a estratégia de incorporação permanente sem duplicar commits/documentação entre PRs #27, #28 e #29; manter a PR #29 como candidata Draft e preservar todas as branches até a decisão de merge.
- Esta validação não autoriza merge. Não fazer merge sem aprovação explícita e específica do usuário.


## 310. Terceira validação da integração Geyser no HEAD documental final — 19/11/2026

### CI confirmada no commit f6664760b23d0b65be7fc8e301d8cce6627773cf
- Workflow **SMR tests**, run ID `44582227274`, run #1828: SUCCESS.
- Job `test`: instalação, suíte unitária e compilação concluídos com sucesso.
- Log completo confirma `Ran 593 tests in 6.745s` e resultado `OK`; `python -m compileall -q src tests` também passou.
- Workflow **Geyser audit benchmark**, run ID `44582227405`, run #45: SUCCESS.
- Job `benchmark`: benchmark sintético e upload do artefato concluídos com sucesso.
- Ambos os workflows foram executados para o mesmo HEAD documental `f6664760b23d0b65be7fc8e301d8cce6627773cf`; nenhuma execução manual foi iniciada.

### Artefato e resultados inspecionados
- Artefato `geyser-audit-benchmark-results`, ID `14560500979`, SHA-256 `023531df5bcccf63c24606ad9c9acd63c66d3ae4f7d231f44fbe0b12a2436d6d`; criado em 2026-11-19 17:55:51Z, expiração 2027-02-17 17:54:53Z.
- ZIP baixado e JSON interno `benchmark-results.json` inspecionado.
- Escala principal: 100.000 eventos lógicos / 200.000 deliveries; rebuild 6,592466 s; throughput 30.337,66 deliveries/s; pico RSS do worker 28,98 MiB; TEMP SQLite 24.399.872 bytes; tracemalloc 0,60 MiB.
- Classificações: 100.000 `SEQUENCED` e 100.000 `UNSEQUENCED_RECONCILED`; contagens RAW preservadas e `integrity_check=["ok"]`.
- Fanout alto: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,236675 s; pico RSS 28,90 MiB; TEMP SQLite 2.088.960 bytes; todas as 10.000 testemunhas preservadas; `integrity_check=["ok"]`.
- Quatro escalas (2.000, 20.000, 100.000 e 200.000 deliveries) mantiveram as classificações esperadas, contagens RAW e integridade SQLite.
- Comparação TEMP em 100.000 eventos: DEFAULT 6,646549 s / 28,97 MiB RSS; FILE 6,612447 s / 29,06 MiB; MEMORY 6,535911 s / 53,39 MiB. MEMORY teve pequena diferença de tempo nesta execução, mas elevou o pico RSS em aproximadamente 24,4 MiB; a evidência continua insuficiente para justificar MEMORY como padrão. Manter DEFAULT/file-backed.
- Limites: fixture sintética em runner Linux/GitHub Actions. RSS/VmHWM mede a vida útil do worker, não somente o rebuild; TEMP pages × page size representa alocação lógica SQLite, não bytes físicos escritos. Não extrapolar diretamente para Termux, VPS ou produção.

### Estado remoto conferido após a CI
- Branch `integration/geyser-pr27-pr28` / PR temporária #29 aponta para HEAD `f6664760b23d0b65be7fc8e301d8cce6627773cf`.
- PR #29: OPEN/DRAFT, `merged=false`, `mergeable=true`, base `feat/geyser-unsequenced-raw-audit` em `f0d63038411cc4207fae910a3ef168e3af443784`; continua identificada como validação temporária, com instrução explícita para não fazer merge.
- PRs originais #26, #27 e #28 permanecem abertas/Draft e sem merge; não foram modificadas por esta rodada.
- `main` foi consultada novamente e permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Nenhum merge foi executado. Nenhum provider, RPC, credencial, VPS, dado real ou execução on-chain foi conectado.

### Conclusão e próxima ação
- A integração conjunta de PR #27 + PR #28 sobre a base PR #26 passou novamente na suíte completa de 593 testes, compilação, benchmark e inspeção do artefato no HEAD documental final.
- Não há falha nova indicada por esta rodada. A evidência é de CI/benchmark sintético, não de execução operacional em ambiente real.
- Próxima etapa: preparar a incorporação permanente de forma controlada, definindo a cadeia de branches/PRs e evitando duplicação de commits e seções do Registro Mestre. Manter PR #29 como candidata temporária até essa decisão.
- Não fazer merge de #26, #27, #28 ou #29 sem autorização explícita e específica do usuário.


## 311. CI e benchmark confirmados após atualização documental da seção 310 — 19/11/2026

### CI do commit documental 6a40966c64d5c2c52a8e82fb1f77a7e3af4a681e
- Workflow **SMR tests**, run ID `44582752853`, run #1829: SUCCESS.
- Job `test`: SUCCESS; log confirma `Ran 593 tests in 5.298s`, resultado `OK`; etapa `python -m compileall -q src tests` também SUCCESS.
- Workflow **Geyser audit benchmark**, run ID `44582752878`, run #46: SUCCESS.
- Job `benchmark`: SUCCESS; execução sintética e upload do artefato concluídos.
- Os dois workflows foram disparados para o commit `6a40966c64d5c2c52a8e82fb1f77a7e3af4a681e`. Como PR #29 é uma PR aberta, o runner fez checkout do merge ref temporário `7fb9353b70bdde58fcaaa4570cf9d7ed1ae40552`, que combina esse HEAD com a base PR #26; a execução corresponde à validação da PR, não a um merge na branch base.

### Artefato da execução
- Artefato `geyser-audit-benchmark-results`, ID `14560140889`, SHA-256 `f9d2d172325b98a96e874113a813210838cdc3f98dd68ac16995ffda3dac83a0`; ZIP baixado e JSON interno inspecionado.
- Escala principal: 100.000 eventos lógicos / 200.000 deliveries; rebuild 5,757790 s; throughput 34.735,55 deliveries/s; pico RSS do worker 28,93 MiB; TEMP SQLite 24.399.872 bytes; tracemalloc 0,60 MiB.
- Classificações: 100.000 `SEQUENCED` e 100.000 `UNSEQUENCED_RECONCILED`; contagens RAW preservadas; `integrity_check=["ok"]`.
- Fanout alto: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,212787 s; pico RSS 28,93 MiB; TEMP SQLite 2.088.960 bytes; todas as 10.000 testemunhas preservadas; `integrity_check=["ok"]`.
- Escalas 2.000, 20.000, 100.000 e 200.000 deliveries passaram com classificações esperadas, contagens RAW preservadas e integridade SQLite OK.
- Comparação TEMP em 100.000 eventos: DEFAULT 5,800909 s / 28,98 MiB RSS; FILE 5,803232 s / 28,95 MiB; MEMORY 5,751945 s / 53,28 MiB. A diferença temporal de MEMORY é pequena e não compensa o aumento de aproximadamente 24,3 MiB de RSS; manter DEFAULT/file-backed.
- Limites: benchmark sintético em runner Linux/GitHub Actions. RSS/VmHWM mede a vida útil do worker; TEMP pages × page size mede alocação lógica SQLite, não bytes físicos escritos. Não extrapolar diretamente para Termux, VPS ou produção.

### Estado e próxima ação
- A atualização documental da seção 310 foi validada por 593 testes, compileall e benchmark no fluxo da PR #29.
- PR #29 continua OPEN/DRAFT, `merged=false`, `mergeable=true`; branch `integration/geyser-pr27-pr28`. PRs originais #26, #27 e #28 continuam sem merge.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Nenhum merge foi executado; nenhum provider/RPC/credencial/VPS/dado real/execução on-chain foi conectado.
- Próxima etapa: decidir e preparar a estratégia de incorporação permanente das PRs #27 e #28 na cadeia baseada em #26, sem duplicar commits ou documentação. A PR #29 permanece apenas como validação temporária; não mergear sem autorização explícita.


## 312. Integração com histórico preservado das PRs #27 e #28 — PR #30 — 19/11/2026

### Construção da integração
- Criada branch `integration/geyser-pr27-pr28-preserve-history`, inicialmente a partir do HEAD original da PR #27.
- Criado commit de integração `a749fe84f96558b64a6eecc2642208204784511e` com dois pais ordenados:
  1. PR #27: `d281daea02dc8d93c7159c5095d8a47579becf7c`.
  2. PR #28: `61ecdde08e66a6707e13ceb09fd54372e672c859`.
- A árvore do commit é exatamente `b77f63a0a940cf0485a7627cffdece8da9d4901c`, a mesma árvore combinada previamente validada na PR #29.
- A PR #30 foi criada em Draft e inicialmente apontada para a base ancestral da PR #26. Em seguida, a base foi corrigida explicitamente para `feat/geyser-unsequenced-raw-audit`, HEAD `f0d63038411cc4207fae910a3ef168e3af443784`.
- Comparação GitHub após correção da base: `ahead`, 43 commits, 0 atrás; 8 arquivos alterados (+1.159/-74), correspondendo à integração combinada sobre a base #26.
- A PR #30 preserva a ancestralidade de ambas as PRs originais; a PR #29 continua sendo referência temporária de validação, não uma PR final.
- Estado consultado: PR #30 OPEN/DRAFT, `merged=false`, `mergeable=true`. Não houve merge.

### CI e benchmark do commit de integração
- Workflow **SMR tests**, run ID `44586860900`, run #1832: SUCCESS. Log confirma `Ran 593 tests in 6.795s`, resultado `OK`; `python -m compileall -q src tests` também passou.
- Workflow **Geyser audit benchmark**, run ID `44586860592`, run #48: SUCCESS; job `benchmark` e upload do artefato concluídos.
- Artefato `geyser-audit-benchmark-results`, ID `14561438046`, SHA-256 `4c631209519086d6c1a6f8e46a169315bfc244283cd2df6b03a4fc8e1a4d271d`.
- Escalas sintéticas: 1.000, 10.000, 50.000 e 100.000 eventos lógicos (2.000, 20.000, 100.000 e 200.000 deliveries). Na escala máxima, rebuild 4,670176 s, 42.824,94 deliveries/s, pico RSS do worker 28,78 MiB, TEMP SQLite 24.399.872 bytes; 100.000 `SEQUENCED` e 100.000 `UNSEQUENCED_RECONCILED`; 200.000 deliveries e 100.000 eventos RAW preservados; `integrity_check=["ok"]`.
- Fanout alto: 1 evento lógico e 10.000 testemunhas; rebuild 0,173194 s, pico RSS 28,76 MiB, TEMP SQLite 2.088.960 bytes e `integrity_check=["ok"]`.
- Comparação TEMP no cenário de 100.000 eventos: DEFAULT 3,962442 s / 28,94 MiB RSS; FILE 3,831503 s / 29,05 MiB; MEMORY 3,752154 s / 53,26 MiB. O ganho temporal de MEMORY é pequeno diante do aumento de aproximadamente 24,3 MiB de RSS; manter DEFAULT/file-backed.
- Limites: benchmark sintético em runner Linux/GitHub Actions. RSS/VmHWM mede a vida útil do worker, não somente rebuild; TEMP pages × page size mede alocação lógica SQLite, não bytes físicos escritos. Não extrapolar diretamente para Termux, VPS ou produção.

### Observação sobre o escopo da validação e base da PR
- Os runs #1832 e #48 foram concluídos antes da correção final da base da PR #30. O log do benchmark mostra checkout do merge ref temporário `55719e912215da9d226bfa52369264e3e8fcc244`, que combinava o commit de integração com a antiga base `4a517ca15499746ddd3f5522f112c80aaac1433b`.
- Portanto, esses resultados comprovam a execução bem-sucedida sobre a árvore de implementação da PR #30, mas não substituem a CI do novo merge ref após a base ser alterada para o HEAD da PR #26.
- Após esta atualização do Registro Mestre, confirmar que os workflows executam no novo HEAD/merge ref com base #26. Registrar os novos resultados antes de considerar a validação final da PR #30.

### Estado de segurança e próxima ação
- PR #30 permanece Draft e não mergeada; PRs #26, #27, #28 e #29 permanecem abertas/Draft e sem merge.
- A branch `main` não foi modificada por esta operação. Nenhum provider/RPC, credencial, VPS, dado real ou execução on-chain foi conectado.
- Próxima ação: aguardar e inspecionar a CI disparada por esta atualização documental, confirmando que o runner usa a base #26. Em seguida, revisar o diff e o estado das PRs sem repetir os testes já aprovados.
- Não fazer merge sem autorização explícita e específica do usuário.


## 313. CI e benchmark confirmados após correção da base da PR #30 — 19/11/2026

### Execuções no HEAD atual da branch
- HEAD da branch: `b58c8a19d3cd22f91c19ad508f5ccbdf4f0afa45`.
- A PR #30 usa base `feat/geyser-unsequenced-raw-audit`, HEAD `f0d63038411cc4207fae910a3ef168e3af443784`.
- Workflow **SMR tests**, run ID `44587193741`, run #1833: SUCCESS.
- Job `test`: SUCCESS; log confirma `Ran 593 tests in 6.723s`; etapa `python -m compileall -q src tests` SUCCESS.
- Workflow **Geyser audit benchmark**, run ID `44587193771`, run #49: SUCCESS.
- Os logs confirmam checkout do merge ref `33604cae9e8a0c333079a592a9bc447d6496c440`, criado por GitHub para integrar o HEAD `b58c8a19d3cd22f91c19ad508f5ccbdf4f0afa45` à base #26 `f0d63038411cc4207fae910a3ef168e3af443784`. Assim, esta rodada valida a PR #30 já com a base corrigida.

### Resultados do benchmark desta rodada
- Artefato `geyser-audit-benchmark-results`, ID `14562735206`, SHA-256 do ZIP `0eadcc6e601df32f7e3d0fbaf17d94f108492f8882de8157adbc3cef842d4670`.
- Escalas sintéticas: 1.000, 10.000, 50.000 e 100.000 eventos lógicos (2.000, 20.000, 100.000 e 200.000 deliveries). Todas as escalas apresentaram classificações esperadas, contagens RAW preservadas e `integrity_check=["ok"]`.
- Escala máxima: 100.000 eventos lógicos / 200.000 deliveries; rebuild 6,510442 s; throughput 30.719,88 deliveries/s; pico RSS do worker 29,06 MiB; TEMP SQLite 24.399.872 bytes; tracemalloc 0,60 MiB; 100.000 `SEQUENCED` e 100.000 `UNSEQUENCED_RECONCILED`.
- Fanout alto: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,230718 s; pico RSS 28,93 MiB; TEMP SQLite 2.088.960 bytes; todas as testemunhas preservadas; `integrity_check=["ok"]`.
- Comparação TEMP no cenário de 100.000 eventos: DEFAULT 6,498656 s / 28,96 MiB RSS; FILE 6,494436 s / 28,94 MiB; MEMORY 6,471898 s / 53,29 MiB. A diferença temporal de MEMORY é irrelevante frente ao aumento de aproximadamente 24,3 MiB de RSS; manter DEFAULT/file-backed.
- Limites: benchmark sintético em runner Linux/GitHub Actions. RSS/VmHWM mede a vida útil do worker, não somente rebuild; TEMP pages × page size mede alocação lógica SQLite, não bytes físicos escritos. Não extrapolar diretamente para Termux, VPS ou produção.

### Estado atualizado e próxima ação
- A lacuna de CI identificada na seção 312 foi resolvida: os dois workflows passaram no merge ref atual da PR #30 com a base #26.
- PR #30 permanece OPEN/DRAFT, `merged=false`, `mergeable=true`; HEAD `b58c8a19d3cd22f91c19ad508f5ccbdf4f0afa45`; 44 commits e 8 arquivos alterados conforme snapshot consultado.
- PRs #26, #27, #28 e #29 continuam abertas/Draft e sem merge. `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Nenhum provider/RPC, credencial, VPS, dado real ou execução on-chain foi conectado.
- Próxima ação: revisão final somente leitura do diff e das relações entre PRs #26–#30, sem repetir testes e sem fazer merge. Não fazer merge sem autorização explícita e específica do usuário.


## 314. Merge da PR #30 na PR #26 e validação pós-merge — 19/11/2026

### Integração concluída
- O usuário autorizou explicitamente o merge da PR #30 na PR #26.
- PR #30 (integration/geyser-pr27-pr28-preserve-history) foi integrada à branch feat/geyser-unsequenced-raw-audit por merge commit:
  - SHA: 061579b52f6c94e348fe2df63f2c6a6fafc9e0f9.
  - A PR #30 foi fechada como merged em 19/11/2026 às 18:42:02Z.
  - O merge preservou a ancestralidade original das PRs #27 e #28.
- A PR #26 permaneceu aberta, Draft, não mergeada, com HEAD atualizado para 061579b52f6c94e348fe2df63f2c6a6fafc9e0f9.
- A PR #26 continua baseada em feat/damm-v2-economic-reconciliation, SHA 4a517ca15499746ddd3f5522f112c80aaac1433b.
- Snapshot GitHub após o merge: PR #26 com 60 commits, 9 arquivos alterados (+1.870/-1), estado OPEN, merged=false, mergeable=true, mergeable_state=clean.
- A branch main foi consultada após o merge e permaneceu no SHA 5060bc65ddf181a4736fdb662c44c3fec0dd7259; não foi modificada.
- PR #30 está encerrada por merge. PRs #26, #27, #28 e #29 não foram fechadas por esta ação.

### CI pós-merge no HEAD da PR #26
- Os workflows executaram sobre o HEAD 061579b52f6c94e348fe2df63f2c6a6fafc9e0f9; o benchmark fez checkout do merge ref temporário 8dae0f780475fdd550a16f3887c74ef601910967, que combina o HEAD da PR #26 com sua base 4a517ca15499746ddd3f5522f112c80aaac1433b.
- Workflow SMR tests, run ID 44590591705: SUCCESS. Job test: Ran 593 tests in 6.678s, resultado OK; python -m compileall -q src tests também passou.
- Uma segunda execução do workflow SMR tests, run ID 44590577810, também terminou SUCCESS no mesmo HEAD.
- Workflow Geyser audit benchmark, run ID 44590591819: SUCCESS; benchmark sintético e upload do artefato concluídos.
- Todos os três check runs associados ao HEAD 061579b... foram consultados como completed/success.

### Resultados do benchmark pós-merge
- Artefato geyser-audit-benchmark-results, ID 14563462630, SHA-256 do ZIP a8e85005acace0d59b260cf0571fefdb8f7af946f690c06acc99214b4c9def91; log do job e JSON do benchmark foram inspecionados.
- Escalas sintéticas: 1.000, 10.000, 50.000 e 100.000 eventos lógicos, correspondendo a 2.000, 20.000, 100.000 e 200.000 deliveries. Todas as escalas mantiveram classificações esperadas, contagens RAW preservadas e integrity_check=[ok].
- Escala máxima: 100.000 eventos lógicos / 200.000 deliveries; rebuild 3,983794 s; throughput 50.203,40 deliveries/s; pico RSS do worker 29,02 MiB; TEMP SQLite 24.399.872 bytes; tracemalloc 0,60 MiB; 100.000 SEQUENCED e 100.000 UNSEQUENCED_RECONCILED.
- Fanout alto: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,145391 s; pico RSS 29,00 MiB; TEMP SQLite 2.088.960 bytes; todas as 10.000 testemunhas preservadas; integrity_check=[ok].
- Comparação TEMP no cenário de 100.000 eventos: DEFAULT 3,998376 s / 29,10 MiB RSS; FILE 4,007098 s / 29,11 MiB; MEMORY 3,975822 s / 53,37 MiB. O ganho de tempo do MEMORY foi desprezível, com aumento de aproximadamente 24,3 MiB de RSS; manter DEFAULT/file-backed.
- Limites: benchmark sintético em runner Linux/GitHub Actions. RSS/VmHWM mede a vida útil do worker; TEMP pages × page size mede alocação lógica SQLite, não bytes físicos escritos. Não extrapolar diretamente para Termux, VPS ou produção.

### Estado de segurança e próxima ação
- A integração #27 + #28 está incorporada à PR #26 e passou na suíte de testes, compilação e benchmark pós-merge.
- A PR #26 ainda não foi integrada à sua base #23. A PR #26 permanece Draft; não há autorização implícita para merge subsequente.
- PR #30 está merged; PR #29 permanece apenas como integração temporária de validação. PRs #27 e #28 continuam abertas e não foram fechadas nesta operação.
- main permanece em 5060bc65ddf181a4736fdb662c44c3fec0dd7259.
- Nenhum provider/RPC, credencial, VPS, dado real ou execução on-chain foi conectado.
- Próxima etapa recomendada: revisão técnica da PR #26 contra a base #23, incluindo o conjunto completo de alterações herdadas e a cadeia de PRs, sem repetir os testes já aprovados. Só depois decidir a promoção da PR #26 para revisão final; não fazer merge na #23 ou na main sem autorização explícita.

### Validação da atualização do próprio Registro Mestre
- A seção 314 foi registrada na branch feat/geyser-unsequenced-raw-audit pelo commit 0a174fab6f7fdfcc3196ef98d15617b24b7747a7.
- No HEAD 0a174fab..., workflow SMR tests run ID 44591253468: SUCCESS; 593 testes em 7,802 s e compileall aprovado.
- No mesmo HEAD, workflow Geyser audit benchmark run ID 44591253458: SUCCESS; checkout do merge ref temporário da PR #26 e upload do artefato concluídos.
- Artefato geyser-audit-benchmark-results, ID 14562134508, SHA-256 do ZIP 8430578bf974729b9253cd30da5dbbd7d1cf10d89cdb87beeee3bcecd4d18573.
- Escala máxima nesta rodada documental: 100.000 eventos lógicos / 200.000 deliveries; rebuild 5,578896 s; throughput 35.849,39 deliveries/s; pico RSS 29,01 MiB; TEMP SQLite 24.399.872 bytes; tracemalloc 0,60 MiB; 100.000 SEQUENCED e 100.000 UNSEQUENCED_RECONCILED; RAW preservado e integrity_check=[ok].
- Fanout alto: 1 evento lógico, 10.000 testemunhas e 10.001 deliveries; rebuild 0,207009 s; pico RSS 28,86 MiB; TEMP SQLite 2.088.960 bytes; todas as testemunhas preservadas e integrity_check=[ok].
- Comparação TEMP: DEFAULT 5,571093 s / aproximadamente 29,01 MiB RSS; FILE 5,549700 s / aproximadamente 29 MiB; MEMORY 5,578654 s / 53,30 MiB. MEMORY não apresentou ganho de tempo e elevou RSS em cerca de 24 MiB; manter DEFAULT/file-backed.
- A nova rodada foi disparada pela atualização documental, não por alteração de código. Os resultados são sintéticos e não substituem validação em Termux/VPS ou ambiente real.

# Histórico da branch de anomalias de transporte (#31)

## 296. Taint histórico de anomalias de sequência Geyser — 19/11/2026

### Achado da auditoria
- Na revisão da persistência RAW da PR #23 foi identificado que `resolve_transport_anomaly(anomaly_id, resolution_note)` aceitava justificativa textual livre e, ao mudar o status para `RESOLVED`, podia liberar o checkpoint quando não restassem anomalias/gaps OPEN.
- A Timeline da PR #23 e a auditoria de deliveries sem sequência da PR #26 filtravam apenas anomalias OPEN.
- Isso permitia que uma colisão de sequência voltasse a ser tratada como evidência elegível após encerramento administrativo, sem prova de que a sequência foi reparada.
- Conclusão: `RESOLVED` deve significar apenas encerramento administrativo. Não é evidência de integridade nem reabilita a sequência histórica.

### Correção preparada — PR #31, baseada na PR #23
- Branch: `fix/geyser-sequence-anomaly-taint`.
- PR #31: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/31 — OPEN/DRAFT, mergeable, sem merge.
- HEAD validado: `093742b1409d16aeadb94268243ad8dd85cfd9f7`.
- `SQLiteGeyserRawStore` mantém o checkpoint interrompido enquanto existir qualquer anomalia histórica na combinação source/stream, mesmo após status RESOLVED.
- A Timeline exclui deliveries cuja combinação `(source_id, stream_id, stream_sequence)` tenha qualquer anomalia registrada, independentemente do status.
- A cobertura por fonte considera anomalias históricas; uma sequência contaminada não pode ser promovida a COMPLETE por encerramento administrativo.
- `PROJECTION_VERSION` da Timeline foi incrementada de 1 para 2 para identificar a mudança semântica da projeção.
- Documentação de persistência/backfill atualizada: gaps podem ser resolvidos por recuperação de sequência; anomalias históricas permanecem tainted até um procedimento futuro separado, com evidência verificável.
- Teste integrado reproduz duas identidades lógicas diferentes na mesma sequência, encerra administrativamente a anomalia e comprova que a Timeline não reproduz os eventos ambíguos e mantém cobertura PARTIAL com baseline declarado.

### Correção complementar — PR #32, baseada na PR #26
- Branch: `fix/geyser-audit-historical-anomaly-taint`.
- PR #32: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/32 — OPEN/DRAFT, mergeable, sem merge.
- HEAD validado: `cfd894718bfae760fee2ffba8be47af125db3e73`.
- A tabela temporária de testemunhas exclui qualquer delivery cuja sequência tenha anomalia histórica, inclusive RESOLVED.
- A classificação da delivery sequenciada continua `SEQUENCE_ANOMALY` após resolução administrativa.
- A delivery sem sequência não pode ser reconciliada usando uma testemunha contaminada.
- `POLICY_ID` foi incrementado para `geyser-unsequenced-delivery:v2`, preservando rastreabilidade da mudança de regra.
- Política `docs/GEYSER-UNSEQUENCED-DELIVERY-POLICY.md` atualizada para refletir a inelegibilidade histórica.

### Validação CI — HEADs atuais
- PR #31 — workflow SMR tests, run `44594389528`, HEAD `093742b1409d16aeadb94268243ad8dd85cfd9f7`: SUCCESS; **574 testes OK** em 4,650 s; compileall aprovado.
- PR #32 — workflow SMR tests, run `44594439303`, HEAD `cfd894718bfae760fee2ffba8be47af125db3e73`: SUCCESS; **593 testes OK** em 7,125 s; compileall aprovado.
- PR #32 — Geyser audit benchmark, run `44594439374`, mesmo HEAD: SUCCESS; artefato `geyser-audit-benchmark-results`, ID `14566160222`, SHA-256 `1b19051894b71b5a042e69544fc793b077d0b9088b5a3b7ad1ae43b42b6f66ff`.
- Benchmark é sintético em runner GitHub Actions; não representa tráfego Geyser real nem desempenho em Termux/VPS.
- Rodadas preliminares expuseram falhas nos testes recém-criados (identidade de fixture e baseline não declarado). Os cenários foram corrigidos; os HEADs finais acima passaram.

### Estado e limites
- PR #23 permanece OPEN/DRAFT no HEAD `4a517ca15499746ddd3f5522f112c80aaac1433b`.
- PR #26 permanece OPEN/DRAFT no HEAD `675b03bb00cfa869e5102241bbc5eec72bb20cab`.
- PR #31 e PR #32 permanecem OPEN/DRAFT e mergeable; nenhuma delas foi mergeada.
- `main` foi consultada novamente e permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- RAW, deliveries e anomalias originais não são apagados nem reescritos.
- Nenhum procedimento de reparo/reabilitação de sequência foi criado. A política atual é deliberadamente fail-closed.
- Nenhum provider Geyser/RPC, credencial, VPS, tráfego contínuo ou execução on-chain foi conectado.

### Próxima etapa
Continuar a auditoria técnica da PR #23 nos módulos de recuperação/backfill, linhagem de bancos e reconciliação econômica DAMM v2. Manter PR #31/#32 Draft até revisão conjunta das dependências. Não fazer merge #31 → #23, #32 → #26, #26 → #23 ou qualquer merge para `main` sem autorização explícita.


## 297. Invalidação fail-closed de identidade de banco após metadados contraditórios — 19/11/2026

### Achado da auditoria
- Na revisão de `BankLineageTracker`, foi observado que `_conflict()` registrava divergências de blockhash/parent metadata, mas mantinha o nó previamente aceito com `usable_for_observation=True`.
- `AccountUpdateTimeline.transition_for()` usa `is_bank_usable()` e `is_ancestor()`; portanto, uma cadeia antes válida poderia continuar autorizando pareamento pre/post mesmo depois de uma observação contraditória para a mesma identidade `(source_id, slot, bank_id)`.
- Isso não selecionava um fork errado por si só, mas preservava indevidamente uma prova de ancestralidade após evidência conflitante.

### Correção preparada — PR #33
- Branch: `fix/geyser-bank-lineage-conflict-taint`.
- PR #33: https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/33 — OPEN/DRAFT, mergeable, sem merge.
- HEAD validado: `90ebeca948829325f3f6a5c25e0e7a6887cae27a`.
- `_conflict()` agora registra a chave em `_conflicted_keys` e invalida um nó já existente.
- Um conflito sobre identidade ainda não materializada não cria artificialmente um nó; se metadados posteriores materializarem essa chave, `_node()` aplica o taint histórico e cria o nó já invalidado.
- `is_bank_usable()` passa a falhar fechado para a identidade conflitante e para descendentes cuja cadeia conhecida passe por ela.
- Nenhuma reparação automática ou seleção de fork canônico foi introduzida.
- Documentação `docs/GEYSER-ACCOUNT-TIMELINE.md` atualizada.
- Teste novo reproduz uma cadeia pai/filho inicialmente válida, introduz blockhash contraditório e comprova que a ancestralidade deixa de ser utilizável. O teste de múltiplos bancos limpos também confirma que uma chave conflitante não é materializada, mas permanece tainted caso apareça depois.

### Validação CI
- PR #33 — workflow SMR tests, run `44595295948`, HEAD `90ebeca948829325f3f6a5c25e0e7a6887cae27a`: SUCCESS; **574 testes OK** em 4,536 s; compileall aprovado.
- Rodadas preliminares falharam porque a primeira implementação materializava um nó para um replacement ambíguo, contrariando o contrato/teste existente. A correção passou a guardar a chave conflitante separadamente, sem materializar o nó, e o HEAD final passou.
- PR #31 recebeu atualização documental no Registro Mestre: HEAD `20fc3ba49eae1972887dd421ed12f2aa14839dfb`; CI run `44594779664`: SUCCESS; **574 testes OK** em 4,697 s; compileall aprovado.

### Estado e limites
- PR #33 é uma correção independente baseada na PR #23; permanece Draft e sem merge.
- PR #31 e #32 permanecem Draft; seus estados e validações estão registrados na seção 296.
- PR #23 permanece no HEAD `4a517ca15499746ddd3f5522f112c80aaac1433b`; PR #26 permanece no HEAD `675b03bb00cfa869e5102241bbc5eec72bb20cab`.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Não houve alteração de RAW, seleção de fork canônico, conexão de provider/RPC ou execução on-chain.

### Próxima etapa
Concluir a revisão da reconciliação econômica DAMM v2 e de suas dependências de transferência/balance snapshots. Até agora, a leitura não encontrou outro bloqueio semântico confirmado nesses módulos; a revisão permanece parcial, não uma aprovação integral da PR #23. Não fazer merge de PR #31, #32 ou #33 sem autorização explícita.


## 298. Revisão inicial da reconciliação econômica DAMM v2 e recovery — 19/11/2026

### Escopo lido
- `src/smart_money_radar/storage/geyser_recovery_store.py` e `tests/test_geyser_recovery_store.py`.
- `src/smart_money_radar/data_sources/damm_v2_economic_reconciliation.py` e `tests/test_damm_v2_economic_reconciliation.py`.
- Dependências de linhagem bancária, transfer analyzer, decoder de transferências SPL/Token-2022 e decoder de balance deltas.

### Avaliação preliminar
- Recovery/backfill exige evidência explícita para finalizar job como COMPLETED: contrato do provider confirmado, intervalo coberto, paginação esgotada, retenção verificada e semântica de consulta idêntica à registrada.
- A documentação corretamente declara que essa evidência é fornecida pelo futuro adapter e registrada pelo store; não é prova independente das garantias do provider.
- Contadores de progresso não podem regredir; retomada preserva cursor durável e cria nova tentativa; recuperação de job interrompido não inventa cobertura COMPLETE.
- A reconciliação econômica DAMM v2 agrega todas as operações por token account, falha fechada em snapshots incompletos, transferências não atribuídas/reutilizadas, CPI não confiável, divergência de gross/net, mint/decimals/owner e fee incompatível.
- Withheld fee esperado permanece `EXPECTED_NOT_VERIFIED` até snapshots TLV pre/post vinculados à transação. Configuração de TransferFeeConfig Token-2022 é verificada separadamente com prestate do mint, epoch, slot, ordem, assinatura e inventário completo de instruções.
- Os testes existentes cobrem divergências econômicas, transfer reuse, owners, snapshots TLV, assinatura/ordem, histórico de mint, epoch e inventário de InitializeTransferFeeConfig.

### Limitação de integração a preservar
- Os contratos atuais da função `reconcile_damm_v2_economic_batch()` exigem que contexts, evidence, all_transfers e balance_deltas pertençam ao mesmo payload/transação, mas os objetos `SolanaTokenBalanceDeltaResult` e `SolanaTokenTransfer` não carregam, por si, assinatura/slot para provar essa associação.
- Isso não foi classificado como defeito confirmado na camada offline, pois o contrato do chamador declara o lote de uma transação. Porém, antes da integração operacional, o adapter/orquestrador deverá fornecer um envelope de transação comum e impedir mistura de evidências de assinaturas/slots diferentes.
- A revisão desta etapa é preliminar; não equivale a auditoria completa da reconciliação econômica nem validação com transações mainnet reais.

### Estado
- Nenhum novo bloqueio confirmado nesta leitura preliminar de recovery/DAMM v2.
- PR #31, #32 e #33 continuam OPEN/DRAFT, sem merge; os resultados de CI e as decisões estão registrados nas seções 296 e 297.
- `main` permanece em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Nenhum provider, RPC, credencial, VPS, captura contínua ou execução on-chain foi conectado.

### Próxima etapa
Aprofundar a revisão do contrato transacional end-to-end: garantir que associação swap/EvtSwap2, transfer inventory, balance deltas e snapshots históricos compartilhem a mesma assinatura/slot/ordem. Depois concluir a auditoria do recovery/backfill e dos módulos restantes da PR #23. Não fazer merge sem autorização explícita.


## Atualização de engenharia — Comando Mestre 27 (2026-11-20)

O registro histórico acima não representa sozinho a versão atual do código. O registro operacional vigente está em `docs/SMR-CODEX-CONTINUITY.md` e `docs/SMR-COMMAND-27-WS-PERSISTENT-RECOVERY.md`. **PR #111 Draft**, sem merge na `main`: recuperação persistente WebSocket reforçada contra RPC tardio, regressão de slot, resposta incompleta e falhas SQLite. A suíte integrada concluiu **1.043 testes, zero falhas, compilação aprovada** no commit de código `f2187d42ee42e076426b648352cb6af15dde2f4a` (https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44836760223). Testes offline comprovaram rollback RAW/checkpoint sob falha injetada, detecção de SHA-256 e reinício por SQLite. **Reconexão real NÃO demonstrada**, último baseline real no slot **471887787**, sem notificações live. Cobertura `UNKNOWN`; nenhuma execução financeira autorizada, `main` preservada em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Próximos gates: interrupções reais de processo nas fases restantes, concorrência multiprocesso e sessão live curta controlada.


## Consolidação CM27 — gate offline validado (2026-11-20)

- **1.049 testes, zero falhas, compileall OK** no código `24e967ddb231315750ce69e4ba8c6685accf0e19`; CI https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44838111116. SQLite RAW versão 5, isolamento entre capturadores por posse exclusiva, identificação de processo Linux por PID e ticks de inicialização, recuperação atômica de sessões incompletas e rollback SQLite sob falha injetada. `main` mantida em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`, PR #111 Draft.
- **Conclusão offline SIM (conforme cenários testados); homologação live NÃO**. Último baseline real conhecido no slot 471887787, 0 notificações. Captura real somente via opt-in manual `.github/workflows/smr-cm27-live-gate.yml`, ainda não acionado. Cobertura `UNKNOWN`; nenhuma ordem financeira ou merge.


## CM28 — continuidade 2026-11-20

- PR #111 Draft; código classificador do live e testes #CM28 1.052/1.052 aprovados em `d6e49886e9eaac5e85b81e819442873db4574201`, CI https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44840348051, Python compile OK. Ajuste de limpeza `f4af94cadc99192908b94691e31c4cf95e2d4e19`; nenhum merge. `main` segue `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Workflow CM27 live existe no branch mas a conexão GitHub do assistente não oferece operação `workflow_dispatch`; nenhuma execução live foi disparada. Não há novo baseline, notificação ou reconexão real demonstrada; cobertura `UNKNOWN`, finanças bloqueadas.
- Auditoria de PRs: 87 abertas, cadeia complexa de bases; PR #112 é divergente da #111, não mergear automaticamente nem reimplementar por duplicidade. Plano com inventário e caminho crítico: `docs/SMR-COMMAND-28-LIVE-INTEGRATION-PLAN.md`.
- Próximo gate: execução oficial do workflow via GitHub Actions quando visível/disponível e captura de artifact; paralelamente testar integração envelope RAW→sinais→risco→simulação→painel sem aumentar permissão financeira. Um executor, zero auxiliares; economia de créditos não quantificada.


## CM29 — Continuidade e integração dos dois radares (2026-11-20)

- PR #111 Draft, sem merge; CI #44841067362 validou **1.063 testes, zero falhas e compileall OK** no commit `88784877fcdac78eba8f8b291d615e1be04a3fba`. Código novo de contrato read-only em `radar_integration_status.py` e dez testes adversariais; `dashboard_read.py` expõe Launch Radar e Smart Money Radar separadamente em estado inicial `UNKNOWN`, sem permissões financeiras. `main` permaneceu `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Workflow CM27 live tem `workflow_dispatch` na branch de desenvolvimento, não existe na `main`; ferramenta GitHub conectada não expõe execução `workflow_dispatch` e não há CLI `gh` autenticada disponível. **Homologação live NÃO executada**, nenhuma nova RPC/WS/notificação. Não contornar via push ou alteração protegida sem aprovação.
- **87 PRs abertas**, PR #112 divergente da #111; metadados e dependências críticas, escopo preservado, roteiro completo e próximos gates registrados em `docs/SMR-COMMAND-29-INTEGRATION-AND-LIVE-BLOCKER.md`. Agentes auxiliares 0, economia não mensurada. Continuidade: integração autenticada de eventos de ambos radares ao painel, mantendo Launch e Smart Money independentes; para executar live, um responsável deve registrar workflow com revisão na default branch e acioná-lo pelo GitHub com opt-in.


## CM30 — integração de eventos arquivados (2026-11-21)

- **Código validado:** commit `4e4237214efcdc0785037ce2a635b3bf15444d98`, **1.081 testes, zero falhas e compilação Python aprovada** na CI https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44843689529. PR #111 segue Draft; sem merge. O total é de uma suíte, não acumular com os ciclos anteriores.
- Reutilizado `data_sources/raydium_cpmm_launch.py` da branch antiga do Launch e a fixture mainnet arquivada (slot 471578450); integrados **leitores read-only** de `cpmm_launch_evidence/cpmm_launch_raw` quando tais tabelas existirem, e recibos Smart Money `swap_replay_archive/swap_observations/observed_transactions`. `radar_event_bridge.py` produz envelopes rastreáveis e mantém LIVE versus fixture/arquivo histórico explicitamente separados. Sem afirmar autenticidade independente ou entrega contínua.
- `dashboard_read.py` e `dashboard_http.py`: seções independentes de Launch/Smart Money, fonte, carteira, SHA-256, disponibilidade, justificativas, `last_archived_event_at` **diferente de heartbeat de coletor**; status live `UNKNOWN`, cobertura `UNKNOWN`, modos paper bloqueados, nenhuma ordem. Novo teste integrado de gravação e reabertura SQLite em read-only, HTML/API e controles de hash, identidades, duplicatas, temporalidade e ausência de autorização.
- **Pendência crítica identificada:** o writer do Launch, stream cursor, backfill e monitor originais continuam nas PRs #68–#76 e precisam ser integrados sem perder funcionalidades. O snapshot local Smart não tem hash independente armazenado: `raw_hash_unanchored` → qualidade UNKNOWN. Leitura histórica não prova ordem de slots; `ordering_domain_unverified`.
- **Workflow live:** PR [#113](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/113) separada, Draft, baseada exclusivamente na `main`, com apenas `.github/workflows/smr-cm27-live-gate.yml`. Revisão e aprovação humana necessárias antes de eventual merge; ferramenta GitHub disponível não oferece `workflow_dispatch`. **Nenhuma nova captura live, 0 notificações novas comprovadas, 0 reconexões reais novas comprovadas**, último baseline conhecido slot 471887787. `main` preservada em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Detalhes técnicos e critérios de progresso: `docs/SMR-COMMAND-30-ARCHIVED-EVENT-INTEGRATION.md`. Próxima tarefa iniciada na ordem de integração: writer/cursor/monitor Launch originais, contrato de origem e replay paper estrito, mantendo os dois radares independentes. Um executor, zero auxiliares, economia de créditos não mensurável.


## CM31 — homologação offline concluída (2026-11-21)

- PR #111 Draft. Integração cirúrgica dos componentes Launch das PRs #68–#76: código inicial 50a615c274bc4676c4794d252cfefb3150811280, CI 44846283776 (1.107 testes). Restaurados writer RAW, cursor de entregas, checkpoint RPC atômico, backfill finalized, monitor WebSocket, métodos finalized do adapter Helius e CLI launch-scan/backfill/live. Não houve coleta real.
- Código complementar **824c93158e8fedf8111a97929e1e330744186900**: [CI SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44846804522), **1.113 testes, 12,251 s, zero falhas, compileall aprovado**. Seis regressões novas comprovam writer real→SQLite→reinício→projeção→DashboardReadService (fixture offline), concorrência entre writers em threads com conexões distintas, SHA e checkpoint falsos rejeitados, interrupção após último RPC e retomada, rollback em cursor RPC sem alteração do checkpoint de carteira, conflito de identidade mesmo fora do limite de página. Não afirmar crash físico/energia, concorrência multiprocesso ou browser real homologados. Proteções de paginação, slot e estado err. RAW de backfill é serialização do resultado RPC; não afirmar bytes exatos de transporte nem autenticação do provider.
- [CI risco e replay protegido](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44846812578): 6+14+5 testes direcionados aprovados, sobrepostos à suíte completa; não somar ao total. **CM31 concluído no escopo offline validado.** Origem/coverage UNKNOWN quando não atestadas; operação financeira e paper operacional bloqueados. PR #112 preservada; PR #113 revisão humana pendente. Main 5060bc65ddf181a4736fdb662c44c3fec0dd7259 intacta. Um executor, zero auxiliares.
- Próximo CM32: integrar sinais e risco às evidências arquivadas, separar Launch de consenso Smart, acoplar auditoria de mercado e risco sem promoção de UNKNOWN, preparar interface conservadora para CM33. Sem reduzir escopo definitivo.


## CM32 — marco inicial validado / CM33 iniciado (2026-11-21)
- Commit f0763e7edd62d504011fdb46ec1daddf1ae716ba: [CI SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44847766936), 1.120 testes, 9,874 s, zero falhas; [replay protegido](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44847773276) também passou. Sete testes CM32: Launch persistido, consenso com recibos simulados, escopo, cutoff, conflitos, risco. Não declarar seleção automática global ou mercado autenticado. Integração complementar de histórico SQLite usando archived_volume_at, sem promoção de volume/quote, e filtragem de eventos futuros publicada na sequência CM33; nova CI necessária.
- CM33: reutilizar replay_paper, extensão opt-in de preenchimento parcial mantendo comportamento anterior por padrão, journal SQLite append-only de testes sintéticos explicitamente separados por run/radar/estratégia/pool, risco em cada tick, replay determinístico com SHA-256 local, painel somente leitura e gate explícito BLOCKED para histórico/prospectivo/live. Novo código e testes ainda aguardam CI; não apresentar números de PnL sintético como rentabilidade. Não há execução financeira nem acesso a chaves. Próximas pendências: qualificação persistida de carteiras, vincular mercado/token safety autenticados, testar real producer Smart Money ao consenso, gestão de capital multi-pool, persistência de decisões de risco operacionais e evidência de fills, controles/autonomia. Limite de 256 ticks por teste sintético; otimização incremental posterior. Main e PR113 preservadas; 1 executor 0 auxiliares.


## CM33 validado / CM34 iniciado — 2026-11-21
- e71d258e58eb0d89d0d411afec9f0e0b64495316: [CI integrada SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44848705046), 1.128 testes em 16,809 s, zero falhas, compileall aprovado; [replay protegido SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44848712649), 6+14+5 direcionados sobrepostos. Oito novos testes CM33 aprovados: fills parciais, restart, integridade, dedup, risco, profundidade, stop/take, canais independentes. CM33 homologado apenas para escopo sintético testado. Sem resultados históricos/operacionais ou promessa de rentabilidade.
- CM34: alocação sintética multipool por escrow integral de subcontas CM33; journal com SHA-256 e cadeia de hashes local (não atestação externa), concorrência serializada, limites por radar/estratégia/token/pool/carteira, perda/drawdown, conciliação e settlement somente sem posição/ordem. Controles locais com capacidade em processo e journal auditável, pause, fault isolado, halt persistente sem reset inseguro. Painel continua read-only. Novo código e oito testes adversariais aguardam CI. Nenhum controle remoto autenticado, coletor 24h ou automação de execução real. Alocação por execução (não por ordem individual) conservadora; capital denominador único explícito, sem FX implícito. Descoberta/classificação automática de carteiras, alertas de mercado, supervisor runtime, atestação de mercado e otimização do replay persistente seguem pendentes. Preserve PR113 e main 5060bc6. 1 executor; 0 auxiliares.


## CM34 validado / CM35 recuperação — 2026-11-21
- e326077325d9e28164a51d52334115fbbc311d90: [CI SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44849505787), 1.136 testes, 15,027 s, zero falhas; [replay protegido SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44849510485). Homologação sintética dos oito casos CM34, não autonomia real. Main 5060bc6 e PR113 58958fa preservadas.
- CM35: recuperada a implementação preparada na tentativa anterior (HTTP 422 ao criar commit). Descoberta offline de candidatos, perfis/snapshots locais, filtro de qualificação conservador, painel. QUALIFIED permanece inalcançável sem evidência independente. A CI deve confirmar alterações; não declarar rentabilidade, mercado inteiro ou autonomia. CM36 supervisor offline ainda pendente. 1 executor, 0 auxiliares.


## CM35 homologado / CM36 incremento supervisor — 2026-11-21
- CM35 commit ffee1dd4712137af148e345b1d7279c373a23598: [CI SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44851268437), 1.144 testes em 11,422 s, oito novos testes aprovados, zero falhas, compilação aprovada. [Replay protegido SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44851275479), testes sobrepostos 6+14+5. Descoberta offline limitada a recibos, sem qualificação econômica independente. Main 5060bc6 e PR113 58958fa preservadas.
- CM36 incremento: supervisor offline singleton persistente com generation fencing verificável, lease/heartbeat, takeover após expiração, watchdog de expiração, transação atômica perfil/decisão/checkpoint, pausa/halt, backoff limitado, isolamento, painel read-only, CLI supervisor-offline, nove testes adversariais e benchmark de 100 ciclos (a medir). Read-only prepara trabalho antes do commit; revalida geração/controle dentro da mesma transação. Não autoriza gravações de conectores live ou execução financeira; ainda precisa integrar fencing aos writers legados antes da ativação real, cursor de ingestão exaustivo/paginação (checkpoint é última observação processada, janela limitada), coordenação dos coletores, autorização de operação simulada, reset de falhas revisado, controle de crescimento e soak real no Termux. Capital existente reconciliado em leitura. Não declarar 24h/live. CM37 pendente. Um executor, zero auxiliares.

## CM36 — validação do incremento e gate de fencing dos coletores (2026-11-21 UTC)
- Commit `c2dbec884c0049fc09d11c4d5934c92e1136632a`: [CI integrada SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44853084513), **1.153 testes aprovados**, zero falhas, 12,880 s, compileall aprovado. [Replay protegido SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44853089308), 6+14+5 testes direcionados sobrepostos (25/25; não somar à suíte). CM35 permanece homologado offline conforme registro anterior.
- Benchmark existente `tools/benchmark_cm36_supervisor.py` integrado ao workflow offline `smr-tests.yml`; novo resultado deve ser comprovado pelo log da CI, não por estimativa. Medir duração de cada ciclo, CPU, RSS, armazenamento e verificar contagem real de tarefas persistidas e SQLite. 100 ciclos acelerados em arquivo vazio NÃO equivalem a soak de 24 horas.
- Gate CM36 ainda aberto: generation fencing dos gravadores Wallet/Launch/Geyser, impedir bypass de escritores alternativos no banco operacional, rejeitar geração vencida e parada de emergência dentro da transação, tratar AuthorityLost como terminal. Não ativar rede nem execução financeira. CM37 deve reutilizar API/painel atuais, manter writes externos bloqueados, PWA sem cache de dados/credenciais/comandos.
- Pendências preservadas: qualificação econômica independente, mercado autenticado, WebSocket live, replay histórico autenticado, Paper Trading prospectivo, Android físico, operação prolongada/24h, homologação administrativa e financeira, integração controlada de PRs e retorno a privado. Dois radares independentes; arquitetura e escopo integrais; meta 14–21 dias não garantida. PR111 Draft, PR113 aprovação humana, main 5060bc6. Um executor, zero auxiliares. Nenhum serviço pago, VPS, trade ou merge.

## CM36A — fencing EventStore e benchmark comprovado (2026-11-21 UTC)
- 696012d7bd836f01de9fbadf54b7c92d85850dec: [CI SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44854672437), 1.153 testes em 12,286 s, zero falhas, compileall aprovado; [replay protegido SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44854678375), 25 testes direcionados sobrepostos.
- Benchmark EMPTY_ARCHIVE_OFFLINE real: 100 ciclos supervisor, 100 Launch + 100 Smart Money persistidos; wall 1,023951095 s; CPU 0,829231626 s; RSS 24984 KiB; armazenamento inicial 270336 B, final 360448 B; média 10,21581111 ms, p95 11,191406 ms, máximo 15,128065 ms; SQLite ["ok"]. Não equivale a desempenho live ou soak 24h.
- A: token imutável geração/owner/radar/banco, BEGIN IMMEDIATE e dupla verificação (antes da escrita e antes do commit), rollback, rejeição de writers sem token em banco com histórico de lease mesmo STOPPED. Nove métodos EventStore, seis regressões. CI nova pendente, CM36 não homologado.
- B Geyser RAW/sessões/recuperação; C propagação terminal e integração aos coletores; D testes integrados e auditoria de caminhos alternativos ainda pendentes. CM37/38 aguardam. Preservar PR111 Draft, PR113 aprovação humana, main, autonomia live bloqueada, dois radares e pendências anteriores. Um executor, zero auxiliares.

## CM36 — correção B/C e incrementos D1/D2 publicados (2026-11-21 UTC)
- A c61d6eff24cb138bcad561951f7b06201dc1b199: CI 44855921178 SUCCESS, 1.159 testes, 12,995 s; replay 44855925312 SUCCESS. Benchmark offline 100+200 ciclos, wall 0,9431449 s, CPU 0,558286963 s, RSS 25108 KiB, armazenamento 270336→360448 B, média 9,4102523 ms, p95 21,470898 ms, máximo 25,220988 ms, SQLite ok.
- B/C 719b517333bea9c44018d01b120943ef56d89446: vinte métodos dos dois stores protegidos; CI 44855968921 FAILED (1.165 executados; 6 erros de setup devido ao atributo read_only inexistente no Geyser); replay 44855974942 SUCCESS.
- Correção mínima 5c6143e7f0fe53b4a2a7c536ea63f9e64d9f775a usa _read_only sem modificar os seis testes. D1 18482802c17c68cfaf89b48c3e07efe9a06344b7 acrescenta revisão de controle por radar, revogação após pausa/retomada, emissão de handle imutável, verificação de autoridade em ambos stores, um teste. D2 8e8dfdbd7b1d3945e9c5d9dec5b7ec220c1bc7d3 acrescenta checagens nas fronteiras RPC/WS/backoff Wallet, Launch, CPMM, Yellowstone, dois testes de reconexão após expiração. Não confundir checagem de fronteira com cancelamento imediato de I/O pendente.

- Correção mínima 5c6143e: CI 44857074863 success; evidências: 2026-11-21T02:39:35.6105981Z test_expiry_during_raw_transaction_rolls_back (test_cm36_geyser_fence.CM36GeyserFence.test_expiry_during_raw_transaction_rolls_back) ... ok | 2026-11-21T02:39:35.6302221Z test_late_frame_stream_registration_is_rejected (test_cm36_geyser_fence.CM36GeyserFence.test_late_frame_stream_registration_is_rejected) ... ok | 2026-11-21T02:39:35.8604409Z test_pause_only_blocks_target_radar (test_cm36_geyser_fence.CM36GeyserFence.test_pause_only_blocks_target_radar) ... ok | 2026-11-21T02:39:36.0805371Z test_separate_db_cannot_bind_same_generation (test_cm36_geyser_fence.CM36GeyserFence.test_separate_db_cannot_bind_same_generation) ... ok | 2026-11-21T02:39:36.1345468Z test_takeover_blocks_old_raw_delivery (test_cm36_geyser_fence.CM36GeyserFence.test_takeover_blocks_old_raw_delivery) ... ok | 2026-11-21T02:39:36.1614098Z test_unbound_rejected_on_managed_database (test_cm36_geyser_fence.CM36GeyserFence.test_unbound_rejected_on_managed_database) ... ok | 2026-11-21T02:39:52.7123357Z Ran 1165 tests in 19.776s | 2026-11-21T02:39:54.8852753Z CM36_BENCHMARK {"autonomy_24h_verified": false, "cpu_seconds": 0.6796836930000001, "cycle_max_ms": 196.56150400000172, "cycle_mean_ms": 15.654542759999686, "cycle_p95_ms": 29.079408999997725, "cycles": 100, "cycles_by_radar": {"launch": 100, "smart_money": 100}, "process_peak_rss_kib": 25072, "radar_cycles": 200, "scope": "EMPTY_ARCHIVE_OFFLINE", "sqlite_integrity": ["ok"], "storage_after_bytes": 360448, "storage_before_bytes": 270336, "wall_seconds": 1.5828968610000018}

- CM36 ainda não integralmente homologado: D1/D2 requerem CI consolidada; cancelamento de I/O pendente sem eventos, source lease vinculado à geração/radar, proteção de projeções alternativas e orquestração efetiva dos coletores pelo supervisor continuam gates. Não declarar cobertura live ou 24h. Preserve todos os gates CM38, evidência autenticada, replay histórico, paper prospectivo, Android físico, administração segura, integração controlada PRs e privacidade posterior.
- CM37A iniciado em paralelo, exclusivamente leitura: navegação móvel, identidade visual escura, resumo patrimonial por conta sintética sem misturar moedas, rótulos de escopo e frescor, manifesto/ícone/service worker sem cache de dados, controles administrativos ainda indisponíveis. Gate de PWA física, gráficos patrimoniais históricos, sessão e autorização administrativa permanece aberto. Um executor/zero auxiliares. PR111 Draft, PR113 58958fa, main 5060bc6 preservadas; nenhum merge, force push, serviço pago ou operação financeira.

## CM36D3/D4 e CM37B/C — continuidade (2026-11-21 UTC)
- D1 1848280 CI 44857094990 SUCCESS e replay 44857101775 SUCCESS; D2 8e8dfdb CI 44857119035 SUCCESS e replay 44857124497 SUCCESS; CM37A 944bdd8 CI 44857169403 SUCCESS (1.171 testes em 10,875 s, zero erros), replay 44857174326 SUCCESS.
- Benchmark 944bdd8: 100+200 ciclos, wall 0,574756562 s, CPU 0,475636198 s, RSS 25332 KiB, armazenamento 270336→360448 B, média 5,73399997 ms, p95 7,143459 ms, máximo 8,128658 ms, SQLite ok. Pico anterior 196,562 ms não se repetiu; nenhuma conclusão causal.
- D3 b97b077d5219f1a8de30f872f1c84932e537a38d: wrapper await_authorized com monitoramento de I/O assíncrona e cancelamento/join; propagação terminal; três novos testes.
- D4 842140584fc827d253be901cba8984b462974324: fences em projeções Geyser e recovery store, timeline/wire, checkpoint, audit; três novos testes. CI consolidada pendente. Ainda auditar cancelamento de threads, source leases entre gerações, inicialização de esquema e orquestração live explícita, testes adversariais de todos os caminhos. CM36 não integralmente homologado.
- CM37B 2f2ab98e4a58fbec0ebd87a8dd0fb1a2e7b0e2dd: gráfico por conta e moeda com histórico sintético validado, janela máxima 500 eventos, PnL não realizado e proporção de runs sintéticos lucrativos (não taxa de trades); indisponível sem evidência. Benchmark CI triplicado em processos e bancos novos.
- CM37C: core administrativo independente, scrypt salgado, hashes de sessão e CSRF, expiração/revogação, rate limit persistente, confirmação única vinculada a comando/radar, replay de request_id bloqueado, audit hash-chain. Seis testes; nenhuma rota HTTP de escrita nem ligação à execução operacional. Segurança e integração administrativa NÃO homologadas. Ajustes de capital/risco/stop-loss/take-profit, sessão HTTP segura, auditoria e rate limit de tentativas não autenticadas, UI de controle, dados financeiros históricos/prospectivos/live permanecem gates.
- Launcher existente: bash tools/run_smr_dashboard_android.sh, somente banco existente, loopback, token efêmero. Android físico e PWA offline/install pendentes; sem afirmar aprovação. Preservar todos os módulos, duas estratégias/radares independentes, CM38, PR111 Draft, PR113 preservada, main intacta, sem merge/force push/execução financeira/24h homologada. Um executor, zero auxiliares.

## CM36D5 / CM37D — fechamento incremental e avaliação Android (2026-11-21 UTC)
- D3 b97b077 CI 44857505918 SUCCESS / replay 44857510206 SUCCESS; D4 8421405 CI 44857533592 SUCCESS / replay 44857538728 SUCCESS; CM37B 2f2ab98 CI 44857575865 SUCCESS / replay 44857581684 SUCCESS; CM37C 671646c CI 44857626197 SUCCESS, 1.184 testes em 16,762 s, replay 44857630080 SUCCESS.
- Benchmark triplo 671646c, cada amostra 100 ciclos supervisor + 200 radares, SQLite ok, 270336→360448 bytes, EMPTY_ARCHIVE_OFFLINE: S1 CPU 0,815300975 s, RSS 25300 KiB, média 10,16941928 ms, p95 11,856378 ms, max 13,050855 ms, wall 1,019302293 s. S2 CPU 0,816951629 s, RSS 25272 KiB, média 10,50435842 ms, p95 13,726245 ms, max 15,750329 ms, wall 1,055302891 s. S3 CPU 0,819258804 s, RSS 25324 KiB, média 10,50791229 ms, p95 13,925827 ms, max 14,998339 ms, wall 1,053236858 s. Média das médias 10,393896663 ms, mediana das médias 10,50435842 ms; mediana por ciclo não medida neste SHA. Não concluir causa do pico anterior nem otimizar prematuramente.
- D5 bc3d024cc518d2d0d1cc8d0b15a0882bb0bcd511: marca durável de banco gerenciado, ausência de lease falha fechada, handle já vinculado não pode ser revinculado, verificação no momento da emissão, teste de resposta tardia de thread RPC, mediana por ciclo adicionada ao benchmark. Ainda não homologar todo CM36: fonte/leases de sessão antiga, migrações/projeções fora do fence, orchestration de coletores vinculados, corrupção de marker e cobertura de testes permanecem auditoria. Sem homologação live.
- CM37D 764e04a8d86de88511911de4e968672876c25ef2: AdminSecurity verifica audit chain antes de autorizar, integração apenas em diretório/banco novo de avaliação via LocalOperationalControls, recibo único, consulta de evento efetivo, controle independente e halt persistente. Quatro testes. Não habilita HTTP de escrita, não executa ordens. Sessões HTTP, validação de origem, CSRF HTTP, configurações de capital/risco e integração UI dos comandos seguem pendências; autorização e journal são bancos distintos, sem garantia de atomicidade entre eles, falha intermediária não é sucesso.
- Avaliação Android 5f88c71b4e933b9cc70be8bb5cbbb46103c167ea: tools/install_smr_android_eval.sh e docs/SMR-ANDROID-EVALUATION.md. Pin 671646c1 validado, novo diretório mktemp privado, venv, SHA, banco novo ou backup read-only explícito, validação, loopback e inicializador existente. Corrigido requisito Python para >=3.11 conforme pyproject. Nenhuma execução física comprovada; não declarar PWA instalada ou Android homologado. 

- Preservar todos os gates CM36/37/38 anteriores, escopo original, dois radares, meta 14–21 dias aspiracional, sem VPS, custos adicionais, chaves reais, operações financeiras, merge/force push. PR111 Draft, PR113 preservada, main intacta. Um executor zero auxiliares. Repositório voltar a privado após conclusão e revisão conforme decisão anterior.

## CM36 — homologação do escopo offline testado; CM37E/F — continuidade (2026-11-21 UTC)
- 764e04a CI 44858480081 SUCCESS, 1.189 testes em 17,813 s; replay 44858484833 SUCCESS. Benchmark triplo CPU 0,821484317 / 0,801862165 / 0,813571082 s, RSS 25340/25372/25380 KiB, média 10,10072604/9,92825125/10,09003550 ms, mediana 9,949184/9,763344/9,839746 ms, p95 11,190703/11,164856/11,408258 ms; máximos 12,340853/17,607585/17,816857 ms; SQLite ok, 274432→364544 B.
- D6 5370deb2c0f528f3b138e1f8b6e849dfceac4275: tabela associativa de autoridade do lease de captura Geyser com geração, supervisor, radar, revisão e digest; recuperação de proprietário revogado mesmo no mesmo PID, preservação do RAW, fechamento de sessões órfãs como process_interrupted_unknown, bloqueio de frames tardios, radar distinto e lease ativo. CI 44859191169 SUCCESS, 1.192 testes em 13,555 s, replay 44859196001 SUCCESS; três novos testes comprovados. Benchmark D6: médias 5,76214391/5,62591433/5,62108449 ms, p95 6,249294/6,122888/6,101743 ms, máximas 6,514986/7,384434/7,336426 ms, CPU 0,466540985/0,462205487/0,466018824 s, RSS 25600/25492/25380 KiB; integridade ok, 100+200 ciclos por amostra.
- CM36: HOMOLOGADO exclusivamente no escopo offline demonstrado dos contratos e testes publicados A–D6 (100% desse escopo). Não implica auditoria universal de todos os chamadores, integração live do supervisor a todos os coletores, inexistência de todo bypass externo ao modelo de autoridade nem garantia operacional. Gates independentes: operação live autenticada, encerramento de rede real, replay histórico autenticado, cobertura UNKNOWN, Android físico, soak 24h, proteção contra falhas adicionais descobertas, integração controlada e revisão humana PR113. Não remover.
- Instalador 03fcf8d35f55cc0c370e33ba6fb99aad5e364d65: CI 44859230914 SUCCESS, 1.196 testes em 18,228 s, replay 44859235995 SUCCESS. Job Python 3.14 136708508625 SUCCESS: 14 testes CM37 + 3 launcher + 4 installer = 21; job principal 136708508763 SUCCESS. Quatro testes: sintaxe/loopback, banco novo, cópia read-only preservada, destino préexistente rejeitado. Blob ef3fa18467bb7ccdadb360e81296c29e72ce6268, SHA-256 40a0c279c1e8b5645ea8864051a1e71a10d9c27de51429c43ee4cff21985ec21 sobre 3491 bytes (base64 blob decodificado e conteúdo raw conferidos). Pin do código 764e04a8d86de88511911de4e968672876c25ef2. LIBERADO PARA PRIMEIRO TESTE FÍSICO ANDROID somente leitura, banco vazio isolado por padrão, com verificação sha256sum -c, sem homologação física, sem garantia de wheels Termux. Proprietário executará comando e reportará resultado sanitizado; não inserir credenciais reais.
- CM37E 710339fde097b12ffea5f4e549aa9622203496d8: HTTP de administração exclusivamente em avaliação nova e separada, host IPv4 loopback fixo, Origin/Host exatos, sem headers de proxy, corpo JSON limitado/sem duplicatas, bearer + CSRF em memória, no-store, rate limits persistentes existentes, logout, sessão, confirmação, identidade de comando, consulta de recibos próprios e resultado no journal. Seis testes adversariais. Servidor normal permanece 405 para POST. Sem exposição remota; HTTPS obrigatório em futura revisão. CI observada: [{"id":44859631221,"name":"SMR strict paper replay checks","conclusion":"success","status":"completed"},{"id":44859626659,"name":"SMR tests","conclusion":"success","status":"completed"}].
- CM37F 9f0543f4d9542d60c1fbd321a8922b58c00ae714: política sintética futura append-only no journal de capital, alterações permitidas apenas sem reservas, principal/equity preservados, comparação idempotente, nova alocação obrigada a usar configuração auditada, exposição/limites, stop-loss/take-profit futuros e validação. Filtros de posição e negociações por radar/estratégia/período UTC no painel, limites visíveis e remoção de dados antigos em falha de atualização. Cinco testes publicados. CI pendente neste registro. Não equivale a integração de configuração administrativa HTTP, capitalização/descapitalização ou política separada por estratégia; essas funcionalidades permanecem gates obrigatórios. Não confundir win rate de runs com trades.
- Restrições: PR111 Draft, PR113 head 58958fa3113130b2cf78ad2430300f5b7c97e02c, main 5060bc65ddf181a4736fdb662c44c3fec0dd7259; nenhum merge, force push, VPS, serviço pago, chave privada ou operação financeira real. Um executor zero auxiliares. Preservar arquitetura e todos os objetivos; CM38 aguardando consolidação; meta 14–21 dias aspiracional.

## Primeiro teste físico Android — relato do proprietário (2026-11-21 UTC)
Instalação Termux, Python 3.14.10, dependências, SHA-256, criação SQLite isolado, localhost, carregamento visual, desativação da restrição de bateria e reinicialização relatados aprovados. Versão 764e04a. Conexão via token não aprovada: mensagem inicial persistente. Causa exata ainda não reproduzida. Correção Android 1: diagnóstico de inicialização JS, health autenticado separado do render, erros explícitos, timeout, proteção de concorrência, tratamento de espaços externos e atualização do worker sem cache. Teste Chromium móvel em CI dedicado; não substitui confirmação física. Banco existente permanece read-only, nenhuma migração. Restantes gates preservados.

## Homologação física Android — consulta autenticada aprovada (2026-11-21 UTC)
- Evidência do proprietário: captura do painel com "Consulta local concluída em 20/11/2026, 23:54:03" e "Conectado · dados atualizados · somente leitura". Instalação Termux, dependências, SHA-256, Python 3.14.10, servidor localhost, interface, autenticação, API e consulta SQLite aprovados no escopo físico observado. Banco de avaliação vazio: nenhuma conta sintética/negociação/rentabilidade comprovada. A imagem não atesta o SHA instalado; versão inicial 764e04a, atualização corretiva publicada 2180cd251a10924e2cc51841b145b0f4e0076376. A mensagem da captura é compatível com a interface anterior, portanto não atribuir causalidade à correção sem confirmação do SHA. Sem reinstalação ou novo teste solicitado.
- Correção 2180cd2: src/smart_money_radar/services/dashboard_http.py; tests/test_cm37_browser_auth.py; .github/workflows/smr-browser-auth.yml; REGISTRO-MESTRE-SMR.md; docs/SMR-CODEX-CONTINUITY.md. CI principal 44862967206 SUCCESS (1208 testes descobertos, 1207 aprovados, 1 skip dedicado); teste Chromium viewport móvel 44862967062 SUCCESS (1 aprovado), Python 3.14 job 136720249538 SUCCESS, replay 44862970399 SUCCESS. Total combinado 1208 aprovados, zero falhas. CM37F 9f0543f CI 44859706429 SUCCESS (1207 testes), replay 44859714579 SUCCESS.
- Reinício da instalação física existente: encerrar servidor com Ctrl+C, ativar o venv do mesmo diretório de avaliação, exportar SMR_DB_PATH para evaluation.sqlite desse diretório e executar bash code/tools/run_smr_dashboard_android.sh --host 127.0.0.1 --port 8765. Novo token a cada processo; sem migração, sem nova base, sem copiar dados reais. Não registrar token, senha ou caminho privado específico do proprietário no repositório público.
- Android 100% somente instalação e consulta autenticada testadas; CM36 100% no escopo offline testado; CM37 estimado 85%; ainda faltam integração administrativa de capital por conta/radar/estratégia, controles autenticados de política e testes correspondentes. PWA instalada, soak 24h, validação live autenticada, aprovação humana PR113 e segurança de escrita fora da avaliação permanecem gates independentes.
- Obrigação permanente: retornar repositório a privado após validações necessárias, por ação autorizada do proprietário se a interface de conexão não oferecer essa operação. Main 5060bc65ddf181a4736fdb662c44c3fec0dd7259 e PR113 58958fa3113130b2cf78ad2430300f5b7c97e02c preservadas; PR111 Draft. Sem merge/force push, VPS, serviço pago adicional ou operação financeira real.

## CM37H / CM38B-C / CM39 — continuidade de 2026-11-21 UTC
- CM37G cc7c464, CI 44863805989 SUCCESS: 1218 descobertos, 1217 aprovados e 1 teste dedicado; navegador 44863805949 SUCCESS, replay 44863810320 SUCCESS, Python 3.14 aprovado. Total combinado 1218 aprovados, zero falhas. CM38A 17d7a71: CI 44863763807 SUCCESS, seis testes aprovados, replay 44863767452 SUCCESS.
- CM37H 73daa3454458e12135fc26aebf6ae7f2f0ae5fdb: campos individuais em avaliação administrativa, orçamento absoluto por radar e estratégia, validação no servidor e confirmação vinculada ao conteúdo, bloqueio de reservas acima do teto, três testes de persistência/concorrência e um Chromium. Não homologar antes das CIs; manter administração externa e escrita financeira bloqueadas. Capital total multi-conta ainda não agregado; não confundir criação de contas com transferências.
- CM38B 04680906139bacd4650188009166bf271ce44e96: captura original Helius via caminho existente, sem chamada duplicada; WalletMonitor confirmed e LaunchBackfill finalized, autoridade antes de persistir, bytes e horários retornam do worker sem escrita tardia. Legados não fabricam RAW. Dois testes publicados; CI pendente. Vinculação explícita de cada derivado e RAW Geyser/baseline continua pendente.
- CM38C: dimensões explícitas de confiança sem promover rótulos, hashes, concordância e commitment a atestação. CM39 preflight bloqueia mesmo flags afirmativas de caller; nenhuma execução real ou prospectiva. Dois testes publicados. docs/SMR-CM38-TRUST-AND-LIVE-GATES.md contém sequência mínima da PR113 e gates.
- Android físico aprovado no escopo previamente observado, sem nova instalação. Preservar banco e inicializador. Main e PR113 não alteradas. Retornar repo a privado após validações necessárias. Sem VPS, serviços pagos, chaves privadas, merge ou force push. Um executor, zero auxiliares. CM37 estimado 96%, CM38 30%, CM39 10%, sujeitos à CI; demais gates permanecem.

## CM37 — HOMOLOGAÇÃO FORMAL OFFLINE / ADMINISTRAÇÃO ISOLADA (2026-11-21)
- Base integral e testes: commit dc2d5e2a4a75a28d14f99dc1f7c5bc4d59fe48dd, Actions SMR tests 44864188331 SUCCESS (1226 testes descobertos, 1224 OK, 2 skips de navegador dedicado); Chromium 44864188348 SUCCESS (2 testes OK); strict paper replay 44864192833 SUCCESS; job Python 3.14 também SUCCESS.
- Homologação 100% estritamente do escopo offline testado: autenticação isolada, sessões e revogação, CSRF, Origin/Host loopback, rate limiting, idempotência/replay, confirmação de comandos críticos, journal administrativo, controles operacionais, capital virtual, limites por radar/estratégia, risco futuro, bloqueio com reservas, interface responsiva e Chromium. Os dois radares permanecem independentes e no modo de avaliação; comandos remotos/escrita em produção e operações reais não autorizados.
- Android físico: somente instalação, autenticação do painel read-only, API e SQLite de avaliação confirmados pelo proprietário. A interface administrativa isolada não foi homologada fisicamente no Android. Não solicitar instalação repetida. A prova física da interface não determina o SHA exato do código instalado.
- CM38D pendente: vincular transação normalizada, classificação, swap, evidência econômica, reconciliador, oportunidade e checkpoint ao RAW RPC imutável com transação única/rollback, sem confundir resposta confirmed com finalized. CM38E/F pendentes: qualificação independente Launch e Smart Money e consenso sem dados insuficientes. CM39 preflight bloqueado sem qualificação; nunca inventar desempenho.
- Gates que permanecem: integração WebSocket/Geyser de RAW e baseline, captura live/24h, autenticação ou independência dos dados de mercado, cobertura UNKNOWN, qualificação econômica, Paper Trading prospectivo, autorização humana para PR113 e decisão de merge separada; após validações, voltar repositório a privado. Main e PR113 preservadas. Sem merge, force push, VPS, compras, chaves privadas, serviço pago adicional ou operações financeiras reais.

## CM38D/E/F e CM39A — evidência e qualificação offline (21/11/2026 UTC)
**CM37** formalmente homologado offline no commit 4e1d4c93d4b637a1ae92ba0db103af723e403226, baseado na CI 44864188331: 1224 testes principais OK, dois skips do navegador; CI Chromium 44864188348: 2 testes OK, replay 44864192833 SUCCESS. Total combinado anterior 1226 aprovados, zero falhas.

**Commits integrados nesta rodada — PR111 continua Draft, sem merge:**
- abf649b5c433194044a725e0aef6cbe51ba606ef: CM38D vincula evidência RPC aos resultados de carteira, swap e classificação, reconciliação, oportunidade de replay, checkpoint da carteira. Launch vincula a assinatura e fonte finalized ao RAW/arquivo econômico e checkpoint RPC na mesma transação SQLite. Caso exista captura original, não aceitar checkpoint sem link. Caso não exista captura, legado pode avançar como UNKNOWN; não alegar que todos os caminhos foram atestados.
- e440d9c1127d624b49df667cd6e3f2f51c9de123: 7 testes adversariais CM38D de integridade, atomismo, divergência, replay, rollback e reinicialização. CI 44889052756 SUCCESS, 1233 testes descobertos (1231 principais OK, 2 skips navegador); navegadores e replay dedicados aprovados.
- ce8da99bdd11756ef5f133ea28cdca7e6e0fb5d3: CM38E/F reutilizam market_opportunity_bridge, market_safety_liquidity, market_volume_audit, opportunity_classifier, wallet_discovery e consenso; a qualificação impede PnL, win rate, custos, drawdown e independência inventados. CM39A preflight lê conta sintética e jamais movimenta capital ou autoriza paper prospectivo sem atestação.
- 03b64042a79a415e8e16aa9ed66c84223f2b6b09: cinco testes de vínculo transacional filho (swap, classificação, reconciliação, replay e cursor Launch), com rollback no erro.
- f76da7b50552d01bf4e48fb3dc7faf347b643ceb: correção de contrato em CM38E para rebaixar simultaneamente independência do consenso e da evidência. CI 44889375684 SUCCESS (1243 descobertos, 1241 principais OK e 2 browser skips); Chromium 44889375659 SUCCESS; replay 44889380276 SUCCESS. A CI pré-correção falhou por independência contraditória, não maquiar falha histórica.
- 8b4e66f4c70930931ee83167510d3a1ee8483730: Geyser RAW de conta + RPC vinculados como TEMPORAL_CONTEXT_ONLY, hash, momento e fonte registrados, sem inferir assinatura causal nem finalização. Três testes offline; CI 44889448430 SUCCESS (1246 descobertos, 1244 testes principais OK e dois skips do navegador); browser 44889448382 SUCCESS, replay 44889452566 SUCCESS.
- e95f0562a765d9cb776f7e4d7b3aba6281683bd5: vinculação de carteira exige source_id helius-wallet-rpc, teste de operação econômica realmente vinculada mas PnL não comprovado, teste de fonte divergente sem checkpoint. CI **44889543648 SUCCESS**: 1248 testes descobertos, 1246 principais OK, 2 skips do browser dedicado; Chromium **44889543645 SUCCESS** 2/2; replay **44889547638 SUCCESS**, Python 3.14 aprovado. **TOTAL COMBINADO 1248/1248, ZERO falhas.**
Não foram realizadas operações live, trades reais, merges ou force pushes.

**Percentuais estimativos, escopo offline:** CM36 100%, CM37 100%, Android instalação/autenticação 100% do escopo físico observado; CM38D ~85% dos vínculos offline, CM38E ~45%, CM38F ~40%, CM38 global ~50%, CM39 ~15%. Nada implica autorização operacional. Cenários ainda sem prova: economic PnL/fees, origem autenticada, segurança token mint/freeze/Token-2022, holders, liquidez dinâmica, volume e manipulação, causalidade Geyser-RPC, cobertura temporal, deduplicação entre todas as fontes, orçamento em rede real e autonomia 24h. Evidências insuficientes continuam UNKNOWN, sem carteiras qualificadas e sem ticks prospectivos.

**Caminho mínimo live:** PR113 Draft somente YAML de workflow manual exige aprovação e merge exclusivamente humanos, depois acionamento manual READ_ONLY_BOUNDED_CM27 com branch operacional selecionada explicitamente, duração máxima 75 segundos, quatro contas CPMM, uma reconexão no máximo, sem ordens. Auditar artifacts RAW/SQLite/manifesto, baseline finalized, lacunas, checkpoints, evidência econômica; follow-up limitado apenas para gaps não observados; dois radares independentes, estabilidade 24 horas e homologação específica do paper prospectivo. Não inferir autenticação de hashes locais, hosts distintos, TLS isolado ou compromisso requested.
Main 5060bc65ddf181a4736fdb662c44c3fec0dd7259 intacta; PR113 head 58958fa3113130b2cf78ad2430300f5b7c97e02c preservada, PR111 Draft; repositorio continua PUBLICO TEMPORARIO e DEVE VOLTAR A PRIVADO após as validações necessárias. Android já homologado fisicamente apenas no escopo declarado, sem solicitar nova atualização. Sem VPS, serviços pagos, chaves privadas ou operações financeiras reais; um executor, zero auxiliares.
**Próxima tarefa:** CM38G: evidências de origem/cobertura e integração de sinal/verificações de liquidez, custo, PnL, causalidade verificada e preflight prospectivo sem lookahead, condicionados à evidência live suficiente e aprovação humana.

## Comando Mestre 40 — CM38G checkpoints e cobertura RPC (2026-11-21 UTC)
Ponto inicial: PR111 Draft head 96f29bcbbee725b452e879d3dad61430dea39f9f. Commit documental teve apenas browser 44889702235 e replay 44889705591 SUCCESS; a última CI principal anterior e95f0562 tinha 1248 testes combinados OK.
Tentativa 93dd0da8ea58c533ebfb3e93e4105a29193c6af9 fechou caminhos alternativos sem considerar bootstrap legado e falhou na CI 44890317101 (16 errors), NÃO homologada.
Correção ec98aa1c34f924d2796fee04a7d85d681a4886a2 preservou bootstrap legado e bloqueou avanço sem evidence_id quando existe RAW capturado; CI 44890413760 falhou um teste cuja expectativa indevida tentava usar a API legada após vínculo correto.
Commit **6d5f6bc6d0b7266904810f427aa742f4e689539f**: expectativa corrigida preservando bloqueio estrito, nenhum bypass no checkpoint. CI 44890497716 SUCCESS (1254 descobertos, 1252 testes principais OK, 2 skips Chromium); browser 44890497766 SUCCESS (2/2); replay 44890501245 SUCCESS. Total 1254 combinados, zero falhas.
Commits **d2e2ef8067545e6f71ab6b5218c86ca676a8968c** e **27ed832ae51b83fb70edf9ac09af5d98109735b3**: novo auditor apenas leitura por radar, fonte e intervalo temporal com preservação confirmed/finalized, validação local SHA256 e identidade, sem rede, sem inferir continuidade ou independência. Consulta de intervalo é anterior à aplicação do limite; truncamento é indicado. Cinco testes novos com intervalos vazios, múltiplas fontes, isolamento, corrupção, truncamento e futuro. CI **44890576620 SUCCESS** (1259 descobertos, 1257 Python OK, 2 skips browser), CI Chromium **44890576732 SUCCESS** (2/2), replay **44890581614 SUCCESS**. Total **1259/1259 testes combinados OK, ZERO falhas**.
CM38D vínculos atômicos com checkpoints e resposta RPC original; Geyser frame é contexto temporal UNKNOWN sem prova de assinatura causal. Modos legados sem RAW não ganham atestação nem cobertura. Reprocessamento e trilha completa de cada entidade continuam pendentes, sem alegar 100%.
CM38E/F continuam informativos; métricas financeiras e independência de carteiras permanecem UNKNOWN. CM39 prospectivo permanece BLOCKED sem prova independente. Proibido inferir autenticidade independente de SHA256 local, concordância RPC, hostname/TLS ou commitment solicitado.
PR113 segue Draft e requer revisão/merge apenas humanos do YAML workflow_dispatch, depois execução manual separada READ_ONLY_BOUNDED_CM27; máximo 75 segundos, quatro contas CPMM e até uma reconexão, artefatos RAW/SQLite/manifesto, checkout explicitamente da branch de desenvolvimento onde existe o script (não main). Não foi executado live. Manter main inalterada, PR111 Draft, PR113 preservada. Repositório público temporário e obrigação de voltar a privado após provas. Sem VPS, serviços pagos, chaves privadas, ordens reais, merge ou force push, nem update Android.
Percentuais estimados: CM36 100% offline, CM37 100% administração offline, Android 100% escopo físico observado, CM38D 90%, CM38E 45%, CM38F 40%, CM38G 35%, CM38 global 53%, CM39 15%. Percentuais não constituem homologação live nem prontidão financeira.
Próxima tarefa: cobertura de reprocessamento vinculada a RAW, vínculos de oportunidade e risco auditáveis e revisão final do caminho de prova live sob aprovação humana.

## Comando Mestre 41 — CM38H / Rastreabilidade e auditoria PR113 (21/11/2026 UTC)
HEAD inicial PR111 9f1372b758c3782446594f5e4a78acf6db2f27ec; GitHub Actions do commit documental: navegador 44890716003 SUCCESS e replay 44890720174 SUCCESS, SEM nova suíte Python. Referência de código anterior 27ed832 com 1259 testes aprovados combinados.
CM38H reprocessamento: commit 40c158585c9df0f782b58ea5b4617dab80d8a341 adicionou cm38_reprocessing_history (recibo histórico de parser com SHA256 do resultado, versão, antecessor hash e vínculo opcional a RPC original). A primeira CI 44891216538 falhou em 4 testes, devido à tabela referenciada ausente em bases legadas e a tentativa de reprocessar RAW capturado sem vínculo. Essa execução NÃO foi homologada. Commit corretivo 02b1631af03a634d6e255dfec5572df62b3d20b2 inicializa sidecar RPC vazio em arquivos legados, mantém reprocessamento sem RAW como legado, proíbe reparsing RAW capturado sem vínculo, não movimenta checkpoint e preserva rollback. CI **44891309193 SUCCESS**: 1264 testes descobertos, 1262 Python OK, 2 skips Chromium; CI Chromium **44891309201 SUCCESS** 2/2 e replay **44891313728 SUCCESS**. Total combinado 1264, zero falhas.
Auditoria PR113 estática publicada em docs/SMR-PR113-SECURITY-REVIEW.md no commit 91966c82867be9e51d39efd6c51a76bb630a804c. 3 novos testes de escopo, acionamento e permissões. CI **44891463801 SUCCESS**: 1267 descobertos, 1265 Python OK, 2 skips navegador, Chromium **44891463697 SUCCESS** 2/2, replay **44891468048 SUCCESS**. TOTAL 1267/1267 aprovados, zero falhas, incluindo Python 3.14 do workflow.
Escopo PR113 verificado no YAML .github/workflows/smr-cm27-live-gate.yml: evento workflow_dispatch com entrada textual READ_ONLY_BOUNDED_CM27, if no job, permissions contents:read, timeout job 3 min e upload de RAW/SQLite/manifest por if:always e retenção de 7 dias. Coletor real na branch de desenvolvimento em tools/capture_live_cpmm_ws_baseline.py: opt-in env explícito, MAX_SECONDS=75 e MAX_FRAMES=80, quatro contas CPMM, endpoints públicos, getMultipleAccounts RPC de leitura e WebSocket de leitura, coverage UNKNOWN, sem ordens e sem chaves.
Riscos PR113: checkout@v4 sem ref explícito e sem pin SHA, setup-python@v5 e upload-artifact@v4 também sem pin SHA, dependências pip -e . sem hashes. Script live só na branch de desenvolvimento, não na main; não confundir 75 s da captura com timeout total de 3 min. manifest.json pode faltar se runner.run falhar antes de escrever manifesto. Verificar reconexão <=1 e integridade dos artefatos na prática antes de alegar prova live. PR113 permanece Draft e NÃO recomendada para merge antes de sanar os riscos, duas decisões humanas separadas (aprovação YAML e disparo live).
CM38H é rastreabilidade adicional do reprocessamento, não fechamento do ciclo completo RAW-oportunidade-risco-papel. Qualificação Launch e Smart Money e métricas econômicas permanecem UNKNOWN onde faltar prova. CM39 permanece em gate BLOCKED e sem mutação financeira real. Independência dos dois radares e histórico legado preservados. CM36/CM37 offline e Android escopo físico preservados.
Percentuais estimados: CM38D 92%; CM38E 46%; CM38F 42%; CM38G 35%; CM38H 30%; CM38 global 56%; CM39 16%. Não são autorização operacional. Captura real e estabilidade 24h NÃO comprovadas. Repositório temporariamente público; obrigação de retorno a privado após validações necessárias. Main intacta, PR111 e PR113 Draft; nenhum merge, force push, pagamento, VPS, chave ou ordem real.
Próximos incrementos independentes: recibos persistentes de oportunidade, decisão e risco com proveniência/tempo, adaptação fail-closed ao Paper Trading existente, auditoria de conteúdo econômico PnL/custo/fees sem inventar dados. Depois de sanar os bloqueadores de PR113 e aprovação humana, executar uma única captura manual auditada, não automaticamente.


## Comando Mestre 43 — CM38J e auditoria independente da PR113 (2026-11-21)

**Base auditada no GitHub:** main `5060bc65ddf181a4736fdb662c44c3fec0dd7259`; PR111 Draft `5bd7cde13a43eebbf2ef9ef19440638cc31b9081`; PR113 Draft `00f6a6a9225524501e8a6bb1fd4d784a2d902ef6`. Revisão imutável do workflow `49bb5e7763926d28e540ca13d9557056b9d87833`; HEAD de código comparado `18633e9764b6cc6894699e88c564740274887948`. A comparação registra dois commits posteriores apenas em cm38i_decision_audit.py, prospective_paper_plan.py e testes. O script `tools/capture_live_cpmm_ws_baseline.py` possui o mesmo blob SHA `321951f7e51d1dadf485d23af75970d3d7e948c4` em ambos os commits.

**Parecer PR113: pronta para REVISÃO HUMANA, não aprovada automaticamente para merge ou captura live.** O YAML usa exclusivamente `workflow_dispatch` e frase `READ_ONLY_BOUNDED_CM27`, token com `contents: read`, `persist-credentials: false`, actions fixadas por SHA, checkout de código e controles separados, lock de três wheels com SHA256 (python-dotenv, websockets, protobuf), Python 3.12, coleta interna até 75 s, 80 frames, quatro contas fixas e política com até uma reconexão. Timeout externo de 90 s mais kill-after de 5 s, job total de 3 minutos. O script verifica SHA256 da fixture CPMM e não contém ordens. Manifesto de término independente registra estado FAILED_OR_INCOMPLETE se execução, DB ou manifesto falharem. CIs PR113 SHA 00f6a6a: 44892872327, 44892867795 e teste offline de lock 44892867802: SUCCESS. CI da revisão imutável 49bb5e7: 44892556113 SUCCESS; 18633e9: 44893099199 SUCCESS. Nenhuma captura live ocorreu nesta revisão.

**Riscos residuais e gates humanos:** as strings de inspeção estática no workflow não substituem teste de comportamento em runtime; não foi feita captura real. O lock SHA256 do wheel não prova por si só a procedência do provedor; a retenção do artifact é 7 dias, exigindo arquivamento autorizado e verificação de metadados antes de eventual publicidade. O workflow de registro precisa de avaliação humana do diff e do conteúdo dos artifacts; uma aprovação para merge não habilita automaticamente execução. O commit efetivo configurado para eventual captura é `49bb5e7763926d28e540ca13d9557056b9d87833`, não a branch móvel. Antes de qualquer ação, conferir SHA e permissão de execução na interface. Interromper uma eventual captura na página Actions via Cancel workflow, preservar artifacts e não repetir a execução até auditoria. O repositório permanece público temporariamente, devendo retornar a privado após validações necessárias, com ação humana independente.

**CM38J:** branch isolada `codex/cm38j-economic-evidence-audit` baseada em `18633e9`. Adicionados `cm38j_metric_provenance.py` e sete testes offline `test_cm38j_metric_provenance.py`: contratos para nove indicadores Launch e nove Smart Money, fonte, janela de observação, disponibilidade, cutoff, qualidade, evidências SHA256 e causa obrigatória de indisponibilidade. Bloqueia lookahead, valores financeiros sem vínculo verificado e cruzamento entre radares; não inventa valor, liquidez, rentabilidade ou consenso e nunca autoriza operação ou paper prospectivo. Não substitui a reconciliação econômica granular pendente. CM38I/CM39 existentes permanecem fail-closed e devem ser integrados à qualificação somente após evidências verificáveis. Percentuais de referência antes desta publicação: CM38E ~46%, F ~42%, G ~35%, H ~30%, I ~60%, CM38 global ~58%, CM39 ~20%; CM38J inicial ~15% sujeito aos testes. Progresso numérico é estimativa técnica, não homologação live.

**Próximas tarefas de implementação:** compor métricas usando market_safety_liquidity e market_volume_audit, validar janelas e custos; reconstruir PnL com custo de aquisição, fees, marcação e drawdown sob evidências verificáveis; ligar indicadores completos ao recibo imutável de CM38I e entrada CM39 somente leitura com snapshot de capital, reavaliação temporal e cenários de reinício, duplicata e reprocessamento. Proibido liberar ordens, paper prospectivo, merges, force push, atualizar Android ou executar captura live sem ações humanas independentes.


## Comando Mestre 44 — CM38J integração econômica offline (2026-11-21 UTC)

Base de continuidade: branch `codex/cm38j-economic-evidence-audit`, originada de `18633e9`. Commit documental CM43 `bdac645087d9cecd336407657e4d1f8fa961238b` confirmado como HEAD inicial. A CI daquele commit documental não constava nas execuções consultadas; CI de código anterior `596ff48` aprovada com 1.287 testes Python executados, dois skips do navegador dedicado. PR #111 permanece Draft no HEAD `5bd7cde`, PR #113 Draft no `00f6a6a`; main `5060bc6` não foi tocada.

Commits CM44:
- `2f6a03d1c765b7fd0b0621f54c68fc4ae605fd49`: recibos CM38J com radar, estratégia, unidade, precisão, método, versão, categoria OBSERVED/MODEL_ESTIMATE/UNAVAILABLE, origem SHA e verificação de integridade antes de agregação. Contratos de estimativa não são promovidos a fatos.
- `f5cd42e15241c73270266cd7a232864abcad5ce6`: adaptador `cm38j_launch_integration.py` reutiliza `assess_token_liquidity`, `audit_swap_volume`, `validate_snapshot` e `estimate_from_snapshot`; mantém pool/intervalo, observação e modelo separados, retém sinais de segurança e ambos os modos imediata/confirmada BLOCKED. Valores observados permanecem informativos, não VERIFIED por conta própria.
- `066f9afb372d6d18028af126679e4d31fe74f9bb`: nove cenários adversariais (dado futuro, outro pool, duplicidade, modelo disfarçado, radar divergente, fonte ausente).
- `ee714d5cebff0ebaf0bd23874a631c7df5f33088`: qualificação CM38E/F passa a retornar `economic_receipts` e `economic_receipt_audit`. Smart Money continua sem PnL, custos, win rate ou owner-independence alegados. Launch conecta mercado e recibos sem liberar ambas estratégias.
- `df1f7260ff51414e28648827144bd4fd7f208c42`: pré-flight CM39 verifica integridade e escopo de recibos quando fornecidos e mantém BLOCKED; não altera capital sintético.
- `969c33e6836388992628e13edc3edbb5a1cc64e0`: testes CM39 adversariais de recibo adulterado, misturado, duplicado e falta de economia, com invariância do capital sintético.

CI comprovada de `ee714d5`: Actions `44895935577` SUCCESS, 1298 testes descobertos, 1296 Python OK, 2 skips Chromium (navegador dedicado), zero falhas e Python 3.14 evaluation SUCCESS. CIs dos commits seguintes requerem confirmação independente. Não contar os skips como navegador executado nesta branch.

Limites: ainda não há integração de cálculo de custo de aquisição, lotes parciais, realized/unrealized PnL, taxas econômicas autenticadas, posição por carteira, drawdown auditado, consenso de proprietários independentes nem preço de execução de mercado com fontes independentes. Modelo CPMM é estimativa, não cotação executável. Recibos UNKNOWN permanecem indisponíveis. Papel prospectivo bloqueado com zero ticks/entradas/saídas. O CM38I persistente permanece imutável, não foi reescrito; o CM39 valida os novos recibos na consulta prospectiva, ainda sem vinculação econômica persistida à decisão CM38I. Essa vinculação exige nova camada imutável e testes de reinicialização/replay. Percentuais indicativos: CM38E 50%, CM38F 47%, CM38J 32%, CM38I 60%, CM39 23%, CM38 global 60% (sujeito a CI final e revisão); são estimativas, não prontidão live.

Próxima tarefa: criar trilha econômica por operação com política de custo de aquisição por lote, venda parcial, transferência e fees verificáveis, incluindo auditoria de tempo, pool e origem RAW; depois persistir referência digest nos recibos de CM38I, sem alterar decisão existente, e ampliar testes de recuperação. Preservar repositório público temporário até validações necessárias e retornar a privado mediante ação autorizada. Proibidos merge, force push, VPS, chave privada, compra, execução financeira real, captura live e atualização Android; workflow PR113/commit fixado devem permanecer intactos.


## Comando Mestre 45 — CM38K livro FIFO offline e vínculo de decisão (2026-11-21 UTC)

**Estado confirmado na abertura:** branch codex/cm38j-economic-evidence-audit HEAD f5d778f20a2a473f5c4d43c2133ef87fd7873bdc; CM44 código 969c33e CI 44896037492 SUCCESS, 1302 testes descobertos, 1300 Python aprovados, 2 skips Chromium. Commit documental f5d778f sem CI própria observada. Main 5060bc65ddf181a4736fdb662c44c3fec0dd7259, PR111 5bd7cde e PR113 00f6a6a permanecem intactos e Draft. Repositório ainda PUBLICO TEMPORARIAMENTE, retorno a PRIVATE obrigatório após validações necessárias.

**Commits publicados CM45:**
- 56ca6d1e5073a832bd89f42732019621b1e56932: cm38k_fifo_reconstruction.py; reconstrução determinística de lotes por carteira, token, quote mint, FIFO versionado. Decimal, operação/RAW origem SHA256, quantidade, datas de disponibilidade, custo conhecido ou UNKNOWN. Compras e vendas fracionadas, transferências de base desconhecida, venda acima do saldo, bloqueios de taxa em ativo não convertido, multietapas incompletas, cutoff e separação das moedas. Hash do recibo e reprocessamento determinístico. ZERO ordem, rede, contas reais ou alteração de capital.
- c58634992d26088f4baa80c2cece3519e1a8ebce: 14 testes FIFO; GitHub Actions 44896367979 SUCCESS, 1316 descobertos, 1314 testes Python aprovados e 2 browser skips, Python 3.14 OK.
- 7408824526667978717090a45d5f049727ce212d: cm38k_decision_links.py; associação append-only entre recibos FIFO e decisão CM38I BLOCKED, em tabela separada com chaves estrangeiras e triggers contra UPDATE/DELETE. Idempotência somente para mesmo payload e recusa divergência, SHA256 do recibo e da associação, cutoff e identidade do radar. Não reescreve decisão imutável.
- 8b338a4318cf7f5a10a8dd65711554b52b6ae90f: reforço para identidade de carteira e verificação do escopo de evidência RPC original.
- 557ce5a6a88d952516c7fbd661a45ecaf0e82e77: cinco testes de associação, integridade do recibo, idempotência, reinício em read-only, janela temporal, divergência e trigger imutável. CI 44896481962 SUCCESS: 1321 descobertos, 1319 Python aprovados, 2 skips Chromium, zero falhas, Python 3.14 OK.

**Alcance e bloqueadores:** a fórmula FIFO foi exercitada com dados de teste, não representa PnL auditado de carteiras reais. O sistema não consegue inferir que fontes indicadas no recibo tenham autenticação externa a partir do texto do próprio chamador; os cálculos e o book mantêm INFORMATION_ONLY/NOT_COMPUTABLE. Transferências recebidas sem base conhecida não são lançadas com custo zero. Resultado realizado requer trilha completa, custos/taxas e moeda homogênea; sem prova, valor fica null e reason code explica a lacuna. PnL não realizado requer cotação comprovada no tempo e mesmo quote mint. Drawdown, consistência temporal e owner-independence não tiveram habilitação a partir de dados simulados. O livro ainda consome operações fornecidas pela camada de avaliação; falta um adaptador persistente que construa operações exclusivamente de swaps reconciliados + RPC RAW autenticados, sem confiar em flags de chamador. Vínculo à CM38I é um sidecar imutável posterior, não atribui causalidade econômica anterior ao instante histórico; a proveniência de cada linha FIFO ainda precisa ser conferida contra o arquivo original via join controlado. Não promover progresso live.

**Estimativas CM45 sujeitas a auditoria:** CM38F 49%, CM38J 34%, CM38K 30%, CM38I 62%, CM39 24%, CM38 global 62%. Não significam produção ou trades habilitados. Launch Radar e ambas estratégias intactos. CM39 mantém zero ticks, entradas e execuções financeiras.

**Próxima tarefa:** implementar vínculo per-operation da projeção FIFO a swaps e classificações existentes, fonte RPC imutável e tempo, com rejeição da classificação corrigida, contabilidade de taxas token e lançamentos parciais; ampliar testes de origem conflitante, rollback e reinício. Preservar PR111/PR113 e main; não mergear, não force-push, não executar captura real, não pedir Android, e restaurar PRIVATE após validações autorizadas.
