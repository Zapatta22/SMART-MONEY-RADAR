# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-17 — PR #1 validado e integrado à main

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
