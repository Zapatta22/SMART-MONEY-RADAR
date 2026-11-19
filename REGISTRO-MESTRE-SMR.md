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


## 93. Atribuição de referral DAMM v2 — PR #22 e CI #544 aprovados (18/11/2026)

- Criado PR #22, Draft, branch `feat/damm-v2-referral-transfer-attribution`, empilhado sobre PR #21.
- `DammV2TransferEvidence` agora inclui `referral_transfer`.
- A atribuição deriva o vault/mint/programa de referral pela matriz oficial `FeeMode::get_fee_mode`, espelhada por `resolve_damm_fee_mode`.
- Para `has_referral=True` e `referral_fee>0`, exige exatamente uma transferência descendente do vault de cobrança correto para `referral_token_account`, com amount bruto igual ao `EvtSwap2.swap_result.referral_fee`.
- Valida programa, mint, decimals, taxa de `TRANSFER_CHECKED_WITH_FEE`, hierarquia CPI, ordem anterior ao evento e não reutilização da transferência entre operações/papéis.
- Casos ausentes, duplicados, CPI não confiável, divergência de mint/programa/amount e `referral_fee` incompatível com `has_referral` não são promovidos indevidamente.
- CI #544 (`44270156613`) no HEAD `90da41436022b2875f76b88a5c999b1328fade01`: **completed/success**; 359 testes aprovados e compileall aprovado.
- PR #22 permanece Draft, aberto e não integrado. PR #21 permanece Draft. PR #17 e #18 também permanecem Draft. PR #20 foi fechado sem merge por duplicação de decoder. `main` intacta.
- Limite atual: a evidência DAMM v2 permanece `ATTRIBUTED`; ainda não há reconciliação econômica por operação usando deltas de contas/vaults, fees input/output/referral e estado withheld. Sem RPC/Helius, RAW fixtures, SQLite, checkpoints ou operações on-chain.


## 94. Reconciliação econômica DAMM v2 por transação — PR #23 em validação (18/11/2026)

- Criado PR #23, Draft, branch `feat/damm-v2-economic-reconciliation`, empilhado sobre PR #22.
- Novo módulo `src/smart_money_radar/data_sources/damm_v2_economic_reconciliation.py` agrega os deltas esperados por token account para o conjunto completo de swaps DAMM v2 da transação.
- Invariantes:
  - input: débito bruto do usuário = `EvtSwap2.included_transfer_fee_amount_in`; crédito spendable do input vault = `swap_result.included_fee_input_amount`;
  - output: débito bruto do output vault = `included_transfer_fee_amount_out`; crédito spendable da carteira = `excluded_transfer_fee_amount_out`;
  - referral: débito bruto = `swap_result.referral_fee`; vault/mint/programa revalidados pela matriz FeeMode; crédito Token-2022 exige taxa explícita em `TransferCheckedWithFee`.
- Revalida proveniência CPI, execução, identidade de instrução, contas, mint/programa, fee explícita e não reutilização de transferências.
- Exige o inventário completo de transferências decodificadas; qualquer transferência não atribuída que toque contas do swap faz o lote falhar fechado.
- Agrega múltiplos swaps sequenciais por token account antes de comparar com os deltas pre/post, evitando repartir delta líquido arbitrariamente.
- Testes adicionados para gross/net, taxa explícita e implícita, fee inválida, referral, snapshots incompletos, delta divergente, transferências não atribuídas e dois swaps compartilhando contas.
- CI #549, #551 e #577 apareceram como failure, mas o job #577 (run `44296507348`) foi consultado diretamente: `runner_id=0`, `runner_name` vazio e `steps=[]`; os logs retornam BlobNotFound. O runner não iniciou o job, portanto não há evidência de execução dos testes. Não classificar como falha de teste nem como aprovação.
- HEAD atual: `c58932b634346cded1bbc52e7c067c62486dada4`; comparação PR #23 contra PR #22: 16 commits à frente, 0 atrás, quatro arquivos próprios e mergeable=true. A revisão estática final encontrou e corrigiu chamadas de teste sem o inventário completo, retorno de referência duplicada, validação estrita de CPI e consistência `included_transfer_fee_amount_out == swap_result.output_amount`.
- A validação de CI continua pendente por indisponibilidade do runner GitHub Actions; a revisão estática foi feita, mas não substitui a suíte automatizada.
- Limites: não cria `SwapObservation`, BUY/SELL ou sinal; não consulta mint/epoch, RPC/Helius, RAW fixtures, SQLite ou checkpoints; não executa operações on-chain. `RECONCILED` valida apenas o lote com os inventários completos fornecidos e não é, sozinho, autorização para trading.
- PR #23 permanece aberto, Draft e não integrado. PRs #17, #18, #21 e #22 permanecem Draft. PR #20 fechado sem merge. `main` intacta.


## 95. Runner GitHub Actions indisponível no PR #23 — 18/11/2026

- Nova execução CI #579 (`44296622580`) no head de código `1d65ae34b1a074544c9013bf85f8ff85129a0765` terminou failure antes de iniciar runner.
- Consulta direta do job `134775210155`: `runner_id=0`, `runner_name=""`, `steps=[]`; logs não foram gerados (BlobNotFound). A execução não chegou ao unittest nem ao compileall.
- Isso confirma problema de provisionamento/indisponibilidade do runner GitHub Actions; não há evidência de falha dos testes e também não há aprovação automatizada.
- Naquele head, PR #23 vs PR #22 estava 17 commits à frente, 0 atrás, quatro arquivos próprios e mergeable=true. O commit desta seção altera somente o Registro Mestre.
- Próxima ação técnica segura: restaurar runner funcional e executar a suíte/compileall sobre o head atualizado antes de avançar para integração com SwapObservation. PRs permanecem Draft; `main` intacta.



## 96. Correção da completude do inventário no PR #23 — 18/11/2026

- Auditoria estática identificou lacuna no reconciliador econômico: ele rejeitava transferências não atribuídas que aparecessem em `all_transfers`, mas não verificava se todas as transferências referenciadas pelas evidências atribuídas estavam contidas nesse inventário.
- Isso permitia que o chamador fornecesse um inventário parcial (inclusive sem uma das transferências atribuídas) sem a ausência ser detectada.
- Corrigido em `src/smart_money_radar/data_sources/damm_v2_economic_reconciliation.py`: o conjunto de IDs das transferências atribuídas agora precisa estar contido no conjunto de IDs do inventário. Transferência atribuída ausente resulta em `INCOMPLETE`.
- Novo teste `test_rejects_claimed_transfer_missing_from_complete_inventory` adicionado em `tests/test_damm_v2_economic_reconciliation.py`.
- Commits: código `62721773a028c0b85da5712b31811ab1b605484c`; teste `262c59a9a23171f1015843625fb611d6ab0dd969`.
- GitHub confirmou a presença da guarda e do teste; isso não equivale à execução dos testes.
- PR #23 continua Draft, aberto e sem merge. HEAD conhecido após a correção: `262c59a9a23171f1015843625fb611d6ab0dd969`; compare com PR #22: 20 commits à frente, 0 atrás, quatro arquivos próprios.
- CI e execução local da suíte permanecem pendentes. Não houve alteração em `main`, RAW fixtures, SQLite, checkpoints, RPC/Helius ou operações on-chain.



## 97. CI #584 após correção de inventário — 18/11/2026

- O commit documental `f9ed8f22b983df070c1365e12e196b1427981d06` acionou o workflow `SMR tests`, run #584, ID `44300868194`.
- Job `test`, ID `134789931058`, terminou failure; consulta de etapas retornou lista vazia (`steps=[]`) e download de logs retornou 404 `BlobNotFound`.
- A resposta resumida disponível não expôs `runner_id`; não inferir esse campo. Não há evidência de que checkout, instalação, unittest ou compileall tenham iniciado.
- A falha não comprova defeito nos testes e tampouco representa aprovação. Causa raiz externa do problema pré-etapas continua não confirmada.
- Nenhum retry foi realizado. PR #23 permanece Draft, aberto e sem merge.
- A validação local no Termux permanece pendente; não declarar testes aprovados até obter saída real.


## 98. Validação local completa do PR #23 e CI sem runner — 18/11/2026 12:55 UTC

- O clone Termux `~/SMART-MONEY-RADAR-PR23` foi atualizado com `git pull --ff-only origin feat/damm-v2-economic-reconciliation`, fast-forward de `b06e022` para `d6142ba37c55aae45f9756b9adec2e2be3520895`.
- A suíte completa foi executada localmente no Android/Termux: `PYTHONPATH=src python -m unittest discover -s tests -v`; resultado: **374 testes executados, 374 aprovados, 0 falhas**, em 6.382 segundos.
- O teste `test_rejects_transfer_reuse`, que havia falhado na primeira execução por o cenário não isolar reutilização de evidência de duplicidade de inventário, passou após a correção exclusiva do teste: `all_transfers=[self.input, self.output]`. Nenhuma lógica de produção foi alterada nesse commit.
- Na mesma cadeia de comandos foi executado `python -m compileall -q src tests`. O processo retornou ao prompt sem erro; portanto compileall local aprovado.
- Foram emitidos alguns `ResourceWarning` de HTTPError/conexões SQLite e avisos de lentidão asyncio; não interromperam a suíte e não causaram falhas. Permanecem como itens secundários de higiene técnica.
- CI no mesmo HEAD `d6142ba...`: runs #586 (push, ID `44302535748`) e #587 (pull_request, ID `44302544704`) terminaram `failure` antes das etapas. Consulta direta do job #587, ID `134795696264`: `runner_id=0`, `runner_name=""`, `steps=[]`. Logo, esses runs não executaram checkout, unittest ou compileall; não são falhas dos testes nem aprovações de CI.
- Estado remoto conferido: PR #23 continua aberto, Draft e sem merge; branch `feat/damm-v2-economic-reconciliation`, HEAD `d6142ba37c55aae45f9756b9adec2e2be3520895`, base `feat/damm-v2-referral-transfer-attribution` (PR #22). Quatro arquivos próprios; PR permanece empilhado sobre PR #22.
- Conclusão: suíte local completa e compileall aprovados no Termux. Validação CI remota permanece bloqueada por ausência de runner provisionado. Não fazer retry repetido sem mudança/diagnóstico do ambiente.
- Próximas pendências: (1) atualizar o texto desatualizado da descrição do PR para refletir a validação local e o estado CI; (2) investigar provisionamento do runner sem mascarar a falha; (3) após CI ou plano alternativo de validação acordado, executar auditoria RAW controlada com evidência mainnet apropriada. Só depois avaliar integração econômica com `SwapObservation`.
- Nenhuma alteração em `main`, RAW fixtures, SQLite persistente, checkpoints, RPC/Helius ou estado on-chain. PR #23 permanece Draft e não integrado.


## 99. Primeiro adaptador DAMM v2 → contratos de domínio — PR #24 (18/11/2026)

- Criada branch `feat/damm-v2-swap-domain-adapter` a partir do HEAD validado documentalmente do PR #23: `947c056e01bfc7b22037e19e3600a5248a29e281`. PR #24 aberto em Draft, base `feat/damm-v2-economic-reconciliation`; não integrado.
- Implementado `src/smart_money_radar/data_sources/damm_v2_swap_domain_adapter.py`, que converte o lote DAMM v2 já reconciliado em três contratos independentes: `SwapObservation`, `SwapClassification` e `SwapEvidence`, ligados por `operation_id` determinístico.
- Guarda principal: só aceita resultado `RECONCILED`, snapshots completos e cardinalidade idêntica entre contextos, evidências e operações.
- A carteira monitorada só é aceita quando o campo `owner` dos deltas da token account de origem do input e da token account de destino do output coincide com o endereço monitorado.
- Semântica econômica explícita: input é débito bruto `included_transfer_fee_amount_in`; output é crédito spendable líquido `excluded_transfer_fee_amount_out`. Conversão para `Decimal` usa decimals dos transfers.
- `SwapClassification` permanece `UNKNOWN`, confiança zero. A direção A→B/B→A não basta para definir ativo-base/quote ou BUY/SELL.
- Testes novos em `tests/test_damm_v2_swap_domain_adapter.py`: construção e vínculo dos três contratos, conversão Decimal bruto/líquido, rejeição de lote não reconciliado e rejeição de owner divergente.
- Documentação criada em `docs/DAMM-V2-SWAP-DOMAIN-ADAPTER.md`.
- Commits da branch até esta atualização: código/testes `7933eba86931b387ae60385b459cf531b396f435`; documentação `9f3b3d5e151f8b380094e68a7877dd38721a9286`. Esta seção será registrada no commit documental seguinte.
- Validação pendente: executar os testes novos e suíte completa, compileall e CI. Nenhuma execução foi alegada nesta etapa; o CI ainda precisa ser consultado.
- Limites: o adaptador não integra parser/normalizador, não persiste SQLite, não altera checkpoints, não consulta RPC/Helius, não modifica fixtures RAW e não cria sinais ou ordens. PR #24 permanece Draft; nenhuma alteração na `main`.


## 100. Endurecimento de proveniência CPI no adaptador de domínio — PR #24 (18/11/2026)

- Revisão estática do novo adaptador identificou necessidade de não depender exclusivamente do status `RECONCILED` recebido: o adaptador também revalida localmente que input/output transfer têm `cpi_path_valid is True`, pertencem à instrução externa associada, ocorrem antes do Event CPI, têm stackHeight descendente e caminho CPI descendente do swap.
- Também revalida que os Token Programs das transferências correspondem aos programas de input/output resolvidos nas contas DAMM v2.
- Adicionado teste negativo para rejeitar `cpi_path_valid=False`.
- Commits adicionais: guarda CPI/programa `84036f22db67b0e68d2289a6c47885f13f897383`; teste `24135bbde0a6b2d7d04913370d66760a6f15182a`.
- Nenhum teste foi executado por esta atualização GitHub; a validação runtime continua pendente.
- PR #24 continua Draft, aberto e não integrado; PR #23 continua sendo sua base. `main` permanece intacta.


## 101. Teste de integração do adaptador com persistência SQLite existente — PR #24 (18/11/2026)

- A inspeção do branch-base PR #23 confirmou que `src/smart_money_radar/storage/event_store.py` já contém as tabelas `swap_observations`, `swap_classifications`, `swap_evidence`, além de `save_swap_bundle()` e `get_swap_bundle()`. A documentação anterior que descrevia a persistência como disponível apenas em branch isolada estava desatualizada em relação ao conteúdo efetivo do branch-base.
- Confirmado também o teste `tests/test_swap_persistence.py` cobrindo round-trip Decimal, idempotência, atualização, rollback, FK/cascade e pré-requisitos do registro pai. A existência do teste não é declaração de execução nesta etapa.
- Adicionado ao PR #24 teste de integração em banco SQLite `:memory:`: o adaptador produz o bundle, cria uma observação pai isolada e persiste/recupera os três contratos via EventStore, comparando os objetos completos.
- O teste usa exclusivamente banco efêmero em memória; não abre nem altera banco persistente, arquivos RAW ou checkpoints reais.
- Commit do teste de integração: `dec4726592f386fea53b01a12c282ad8c340a55a`; atualização documental: `61c92db828c282ad8634565ecf888fff47e32bf4`.
- Execução de testes ainda pendente. CI #598 no commit anterior terminou sem etapas (`steps=[]`) e logs BlobNotFound; não há evidência de execução nem aprovação CI. Não repetir retries automáticos.
- PR #24 continua Draft, aberto e sem merge. `main` permanece intacta.


## 102. Endurecimento adicional da ligação swap↔EvtSwap2 e CI #602 — PR #24 (18/11/2026)

- O adaptador passou a revalidar também a relação pai/filho do próprio evento: `event_stack_height == swap_stack_height + 1`, caminho do Event CPI exatamente um nível abaixo do caminho do swap, evento posterior à instrução swap e índices tipados/não negativos.
- Exige que o programa das contas resolvidas seja o Program ID canônico Meteora DAMM v2.
- Confere que o índice inner da evidência atribuída coincide com o índice da associação.
- Testes existentes foram ajustados para usar o Program ID canônico; novo teste negativo cobre caminho CPI do evento que não descende do swap.
- Commits: reforço de vínculo CPI `09916957bc37eb71c1b480bd3da59dcdef35821a`; fixture com programa canônico `70ae114da9cf143d78ae2288852788f8ada7e4cc`; teste negativo `20a77ac331d0414835ea4168eb8d9e2801443c70`; endurecimento final de índices/identidade `80e3735b458c66dc63223c09b8fdba179fe49c7c`.
- CI #602 (run `44310450270`) no commit documental anterior terminou `failure`; job `134822897989` retornou `steps=[]`, sem logs disponíveis. Não há evidência de checkout/testes/compileall; não classificar como falha de testes nem aprovação. Nenhum retry realizado.
- Nenhum teste local foi executado nesta atualização GitHub. PR #24 permanece Draft, aberto e sem merge; `main` intacta.


## 103. Estado consolidado do adaptador de domínio e CI #612 — PR #24 (18/11/2026)

- HEAD de código/documentação do PR #24 nesta atualização: `b375caad55b6fc3fd2525e342733e046e02f1961`.
- O adaptador agora exige identidade CPI tipada, stackHeight de evento exatamente um nível abaixo do swap, caminho do Event CPI descendente imediato, índice de evento posterior ao swap, Program ID canônico e identidade/descendência das transferências.
- Testes de integração cobrem o round-trip do bundle pelo EventStore em SQLite `:memory:`; teste negativo cobre Event CPI com caminho que não descende do swap.
- CI #612 (run `44310869715`) no commit `b375caad...`: job `134824365125` terminou failure antes das etapas; consulta retornou `steps=[]` e logs ausentes. Nenhum unittest/compileall foi executado pelo runner. Não classificar como falha de código nem aprovação.
- CI #593, #598, #602 e #612 indicam indisponibilidade pré-etapas recorrente; não repetir retries automáticos.
- Validação runtime do PR #24 continua pendente. A suíte 374/374 e compileall aprovados anteriormente pertencem ao HEAD de código/teste do PR #23 (`d6142ba...`), não cobrem o adaptador novo.
- PR #24 permanece aberto, Draft e sem merge, empilhado sobre PR #23. Nenhuma alteração na `main`, banco persistente, RAW, checkpoints, RPC/Helius ou estado on-chain.


## 104. Orquestrador transacional DAMM v2 — PR #25 (18/11/2026)

- Criada branch `feat/damm-v2-transaction-pipeline` a partir do HEAD PR #24 `c67a574cc29b090842aebe08dd4018b282df9b85`.
- Criado PR #25, Draft, base `feat/damm-v2-swap-domain-adapter`, HEAD inicial `0fe1b1c1b851ccd9c33938d8ae62c39e8133bc20`; três arquivos próprios.
- Novo módulo `src/smart_money_radar/data_sources/damm_v2_transaction_pipeline.py` encadeia: validação do payload e execução; associação swap/Event CPI; resolução da instrução externa/inner e account keys/loaded addresses; resolução de contas; decodificação de transferências; atribuição CPI; snapshots de token accounts; reconciliação econômica em lote; adaptador para os três contratos de domínio.
- O pipeline rejeita o lote inteiro se existir swap/evento não associado, ambiguidade, transferência não atribuída, snapshot incompleto, divergência econômica ou erro de estrutura. Estados públicos: `NO_DAMM_V2_SWAPS`, `REJECTED`, `RECONCILED`.
- O pipeline não chama `transaction_parser.py` nem `normalize_transaction`, não persiste EventStore, não avança checkpoint, não chama RPC/Helius e não executa ações on-chain. A classificação de domínio continua `UNKNOWN`.
- Criados testes sintéticos para transação sem swap DAMM v2, estado de execução ausente, transação falha, metadados ausentes e campos obrigatórios.
- Documentação: `docs/DAMM-V2-TRANSACTION-PIPELINE.md`.
- CI #615 (run `44311776265`) e #616 (run `44311887367`) terminaram failure antes de etapas. Jobs `134827468470` e `134827833045` retornaram `steps=[]`; logs BlobNotFound. Não há evidência de checkout, unittest ou compileall. Não classificar como falha de código nem aprovação; não repetir retries sem diagnóstico do runner.
- Comparação PR #25 contra PR #24: 3 commits à frente, 0 atrás; três arquivos próprios (266 linhas pipeline, 82 testes, 39 docs).
- Validação runtime do PR #25 permanece pendente. Nenhuma fixture RAW mainnet prova ainda o caminho completo de swap DAMM v2.
- PR #25 permanece Draft, aberto e sem merge; PR #24 permanece Draft e é a base. `main` intacta; sem alteração em RAW persistente, SQLite persistente, checkpoints, RPC/Helius ou estado on-chain.
- Próximo trabalho: obter validação executável do código e criar fixture RAW mainnet auditada; depois, avaliar integração controlada do pipeline com normalização/parser, sem promover BUY/SELL até haver regra de ativo-base/quote comprovada.


## 105. Persistência DAMM v2 e bloqueio de checkpoint no WalletMonitor — PR #25 (18/11/2026)

- Continuação do PR #25 na branch `feat/damm-v2-transaction-pipeline`, ainda Draft e baseado no PR #24.
- Criado `src/smart_money_radar/domain/damm_v2_persistence_pipeline.py`: envolve o pipeline transacional DAMM v2, arquiva a observação normalizada, persiste bundles reconciliados e registra tentativas de reconciliação no `SQLiteEventStore`.
- O adaptador de persistência **não avança checkpoint** em nenhum caminho. Em transação falha on-chain, delega o fluxo ao pipeline CPMM existente, que já trata esse estado.
- O `WalletMonitor._collect_transaction` agora executa DAMM v2 antes de Raydium CPMM. Se DAMM v2 retornar pendência, o processamento CPMM é bloqueado e o checkpoint permanece intacto. Se não houver swap DAMM v2 ou o lote for reconciliado, o fluxo segue para CPMM, que permanece coordenador final do checkpoint nesta etapa.
- Idempotência de bundles continua garantida por `SQLiteEventStore.save_swap_bundle`; retries de transação não devem duplicar bundles já gravados.
- Testes adicionados:
  - `tests/test_damm_v2_persistence_pipeline.py`: observação sem swap arquivada sem checkpoint, transação falha delegada sem checkpoint e assinatura divergente rejeitada antes de persistir.
  - `tests/test_wallet_monitor.py`: cenário em que DAMM v2 permanece pendente; confirma que CPMM não é chamado e checkpoint não avança.
- Documentação `docs/DAMM-V2-TRANSACTION-PIPELINE.md` atualizada com persistência e coordenação do checkpoint.
- CI após as alterações anteriores (#620–#623) continuou falhando sem etapas executadas; run #624 (`44312969425`) também terminou sem runner/steps. Não há evidência de unittest ou compileall via CI. Não fazer retries repetidos sem correção do runner.
- **Validação runtime destes novos arquivos e integração ainda pendente**; os testes sintéticos foram adicionados, mas não foram executados nesta sessão.
- PR #25 permanece Draft e sem merge. `main` intacta; sem alteração de RAW persistente, SQLite persistente, checkpoints locais, RPC/Helius ou estado on-chain.
- Próxima etapa: validar a nova integração em ambiente executável; depois ampliar testes para erro de persistência e recuperação idempotente, antes de promover integração adicional a outros venues.


## 106. Endurecimento do pipeline e verificação de assinatura — PR #25 (18/11/2026)

- `process_damm_v2_transaction` agora valida, quando presente no payload RPC, que a assinatura informada consta em `transaction.signatures`; payload divergente é `REJECTED`.
- O pipeline exige cardinalidade exata entre swaps reconciliados e bundles de domínio; divergência não pode retornar `RECONCILED`.
- Adicionado teste negativo para assinatura divergente.
- O adaptador de persistência conta rejeições estruturais sem swap decodificado como pendência não resolvida, evitando mensagem enganosa de 0/0 swaps concluídos.
- Logs do `WalletMonitor` agora expõem total de pendências DAMM v2 além da contagem de swaps reconciliados.
- Runs CI #627–#633 permanecem sem steps executados; #633 (`44313351764`) também terminou failure com `steps=[]`. Não há evidência de execução de testes ou compileall. Não repetir retries.
- Nenhuma validação runtime do PR #25 foi comprovada ainda; alterações de persistência e coordenação do monitor precisam de execução no Termux antes de qualquer merge.
- PR #25 permanece Draft, sem merge; `main` intacta.


## 107. Auditoria negativa de swap DAMM v2 e replay — PR #25 (18/11/2026)

- Adicionado cenário sintético que contém uma associação swap + `EvtSwap2` estruturalmente MATCHED, mas inventário de contas inválido (menos de 14 contas).
- O teste percorre o adaptador de persistência real até a falha de resolução de contas e verifica que:
  - o resultado permanece `pending_reconciliation`;
  - o swap é contabilizado como não resolvido;
  - uma tentativa `INCOMPLETE` é gravada no SQLite `:memory:`;
  - a assinatura permanece em `get_pending_signatures`;
  - nenhum checkpoint é avançado.
- Corrigido o pipeline para preservar associações e evidências intermediárias quando uma etapa posterior rejeita a transação; sem isso, a persistência perdia o swap que precisava auditar.
- Corrigido helper Base58 do teste para contar bytes zero iniciais sem escape ambíguo.
- CI #639–#642 sem execução de etapas; #642 (`44313722273`) também terminou com job sem steps. Nenhum teste/compileall foi executado pelo runner.
- PR #25 continua Draft; validação runtime do teste sintético e integração ainda depende de Termux ou runner funcional.


## 108. Preservação de RAW em erro de normalização e fail-closed abrangente — PR #25 (18/11/2026)

- O orquestrador transacional agora captura exceções inesperadas de estágio como `REJECTED`, preservando associações, contextos, transferências, snapshots e reconciliação já produzidos.
- O adaptador de persistência arquiva payload RAW com `parse_status=parse_error` quando a normalização falha, registra o tipo da exceção e mantém checkpoint intacto para replay.
- Teste adicional simula erro de normalização e exige RAW arquivado, estado `parse_error` e ausência de assinatura processada.
- Teste de inventário inválido verifica fila de replay e tentativa `INCOMPLETE` persistida em SQLite `:memory:`.
- CI mais recente observado antes deste registro (#645) falhou sem etapas; runs posteriores a cada commit seguem indisponíveis sem evidência de execução de testes.
- Nenhum teste runtime foi executado nesta sessão; PR #25 permanece Draft, sem merge, e `main` intacta.


## 109. Estado de CI após integração do monitor — PR #25 (18/11/2026)

- CI #646–#652 continua sem executar testes. Último run observado: #652 (`44314028359`), job `134835287722`, status failure com `steps=null`; consulta de steps retorna lista vazia. Não há logs disponíveis.
- O padrão é indisponibilidade do runner/artefato de log, não evidência de falha de unittest ou compileall. Nenhum retry adicional foi disparado.
- PR #25 permanece Draft, aberto, sem merge; `main` intacta.


## 110. Coletor dedicado para fixture RAW mainnet DAMM v2 — PR #25 (18/11/2026)

- Identificado no catálogo versionado `data/fixtures/candidates/solana_mainnet_candidates.json` um candidato específico Meteora DAMM v2:
  `1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT`, slot reportado 451432630.
- Criado `tools/collect_damm_v2_fixture.py`, que seleciona exatamente um candidato DAMM v2 no catálogo e usa o `RpcFixtureCollector` existente para obter `getTransaction` finalized/JSON.
- O coletor grava RAW e manifesto local em `data/fixtures/raw/damm-v2/`, com SHA-256; não envia fixture ao GitHub, não anonimiza, não importa SQLite e não avança checkpoint.
- Criado `tests/test_damm_v2_fixture_collector.py` para confirmar seleção única e rejeitar catálogo ausente/ambíguo.
- Documentado comando Termux com endpoint RPC somente leitura em `docs/DAMM-V2-TRANSACTION-PIPELINE.md`.
- A fixture ainda não foi coletada nesta sessão; a transação candidata não foi tratada como evidência RAW até o retorno do RPC e validação de hash/estrutura.


## 111. Bloqueio fail-closed quando metadados CPI estão ausentes — PR #25 (18/11/2026)

- Auditoria estática identificou uma lacuna crítica: o pipeline podia interpretar meta.innerInstructions ausente ou nulo como lista vazia, pois o analyzer usa meta.get("innerInstructions") or [].
- Em Solana, innerInstructions null/ausente não comprova que não houve CPI. Como DAMM v2 pode ser chamado por agregadores, esse cenário poderia produzir falsamente NO_DAMM_V2_SWAPS, liberar o pipeline CPMM e avançar checkpoint sem analisar o swap DAMM v2.
- Corrigido process_damm_v2_transaction: agora exige meta.innerInstructions como lista explícita; lista vazia é aceita, campo ausente/nulo gera REJECTED e bloqueia a próxima venue/checkpoint.
- Adicionados testes negativos para campo ausente e nulo em tests/test_damm_v2_transaction_pipeline.py.
- Ajustados dois fixtures de tests/test_wallet_monitor.py para declarar explicitamente innerInstructions: [] nos cenários sem CPI.
- Atualizada a documentação docs/DAMM-V2-TRANSACTION-PIPELINE.md.
- Commits: implementação 3ca36505d11ec53bbd8dcc4f290db2db7962a5f4; testes do pipeline 455fd607e18550b39939fac60ae4a308830d1d7b; fixtures do monitor fc1541f974f932fa4f15654089e7941cc40ab270; documentação 73292b0fed108ca8a14e5cc8831abf5160b50043.
- Esta é revisão estática/correção enviada à branch do PR #25. Ainda não há execução local ou CI confirmada para estes commits; não declarar testes aprovados até obter execução real.
- PR #25 permanece Draft e sem merge. main, RAW persistente, SQLite persistente, checkpoints, RPC/Helius e estado on-chain não foram alterados.


## 112. Integridade de Address Lookup Tables antes da análise CPI — PR #25 (18/11/2026)

- Segunda lacuna fail-open identificada na auditoria: para transações versionadas compiladas, a análise de programIdIndex dependia de meta.loadedAddresses. Se addressTableLookups existisse e loadedAddresses estivesse ausente/incompleto, o analyzer poderia não resolver o Program ID DAMM v2 e retornar falsamente ausência de swap.
- O pipeline agora resolve/valida accountKeys antes de chamar o analyzer.
- Quando message.addressTableLookups é não vazio e accountKeys usa chaves compiladas, exige meta.loadedAddresses e valida writable/readonly contra a soma dos writableIndexes/readonlyIndexes das lookup tables. Índices inválidos, contagem divergente ou metadados ausentes rejeitam a transação.
- Adicionados testes negativos para loadedAddresses ausente e cardinalidade divergente; documentação atualizada.
- Commits: validação dcad62896dde85a244fa975daaeb72416b6d3f77; testes 1fa5c91e0378a96b5c9c81c8aaa5f9c71b476dc0; documentação e355ac5f8cff1d119ed2810635debb383cb0754f.
- Revisão estática enviada ao PR #25. Testes runtime e compileall continuam sem execução comprovada; CI segue sem steps/logs. Não afirmar aprovação.
- PR #25 Draft, sem merge; main, RAW persistente, SQLite persistente, checkpoints, RPC/Helius e estado on-chain preservados.


## 113. Teste de integração da proteção CPI até a fila de replay — PR #25 (18/11/2026)

- Adicionado teste no adaptador de persistência que remove meta.innerInstructions do payload e executa o caminho real de persistência com SQLite :memory:.
- O teste exige pending_reconciliation, ready_for_next_venue=False, RAW arquivado, assinatura na fila de replay e ausência de assinatura processada/checkpoint. Assim, cobre a propagação do novo bloqueio até a fronteira que impede o WalletMonitor de liberar CPMM.
- Teste ainda não executado em runtime; CI segue sem steps/logs. Commit do teste: ceb008d1a980290204cf4d4224c05cac4a9b98b0.
- PR #25 Draft, sem merge; main e estado persistente preservados.


## 114. Formato homogêneo obrigatório para accountKeys — PR #25 (18/11/2026)

- Auditoria estática identificou que os helpers de resolução usavam `any(dict)` para decidir se `accountKeys` estava em formato `jsonParsed`. Uma lista mista (objetos e strings) podia ser aceita parcialmente e produzir índices/chaves inconsistentes.
- O pipeline DAMM v2, o analyzer DAMM v2, o decodificador SPL/Token-2022 e o decodificador de deltas agora rejeitam listas que misturam objetos `jsonParsed` e strings `compiled`. A validação ocorre antes de resolver endereços/índices.
- Testes negativos adicionados nos quatro níveis: pipeline DAMM v2 retorna `REJECTED`; analyzer e decodificador de transferências levantam `ValueError`; decodificador de deltas retorna `ACCOUNT_KEYS_INVALID`.
- Hardening adicional do analyzer: `f8769c377b0ae533a3a68659312bbe24245958fd`; teste `e816e6be973982639691f3bb2181454d5e9992d3`.
- Commits de implementação: `45c1372bd535c1608b348569ea8e7db53bb228b9`, `d8fa7b8c41809b9c0c701057577b58ff30e09750`, `93853ccf8e28a1e60d0b4165327aae9d1b061cea`.
- Commits de testes: `fc40f28931eec6d247f5203ff5391c5f602c1d77`, `8a4bac2cdb57fcdeff390bd750feb7b8363ce479`, `f6b9f818a3d14941eded6b779444711fd2daabf1`.
- Documentação atualizada. Esta alteração é revisão estática enviada à branch; nenhum teste runtime/compileall foi executado por esta ação. A CI continua sujeita à indisponibilidade pré-etapas já registrada.
- PR #25 permanece Draft e sem merge; `main`, fixtures RAW, SQLite persistente, checkpoints, RPC/Helius e estado on-chain permanecem intocados.

- CI no HEAD subsequente: run #691 (`44317299989`), job `134846680569`, terminou `failure`, mas steps retornou `[]` e logs retornaram `BlobNotFound`. Portanto, também não há evidência de checkout/testes/compileall; não repetir retry sem diagnóstico do runner.


## 115. Validação ALT consistente em analyzer e decodificadores — PR #25 (18/11/2026)

- Auditoria identificou que o pipeline transacional conferia cardinalidade das ALT, mas os caminhos independentes do analyzer DAMM v2, decodificador SPL/Token-2022 e decodificador de deltas apenas anexavam `loadedAddresses`, sem confrontar `addressTableLookups`.
- Os quatro caminhos agora validam a estrutura de `addressTableLookups`, índices writable/readonly (inteiros não negativos, sem bool), presença de `meta.loadedAddresses` quando há lookup tables e cardinalidade exata por tipo.
- Endereços carregados não vazios sem lookup tables são rejeitados para impedir deslocamento/contaminação dos índices. Campos ausentes equivalem a lista vazia somente quando a transação não declara ALT.
- Testes negativos adicionados para ausência de lookup com endereços carregados e contagem divergente; fixtures existentes com ALT foram corrigidas para colocar `addressTableLookups` em `transaction.message`, conforme o formato Solana.
- Implementações: analyzer `4100eeff8073bf5795b0d26a149d3f888345c88d`; transfer decoder `1e3ff7501967c8584807f5296763c0fcdeb605dc`; balance decoder `fa5e9dbfb1a6f84c3d8fe3d70e769221b68ce9f8`; pipeline `487e75b9354c6c4311f5bb846a67967623e2c88e`.
- Testes/fixtures: pipeline `01e8ac636edd74f2dbdbf65b344e631ef07c2c18`; analyzer `e95d51f5844a1d0a33b37545fa287933590ee5e8`; transfer fixtures `7d25ffb608c2dea85d24cd3adbd2ced0247122ef`, `5c4c3224c6370bfd173d3daccbc19676b5f1737f`; balance deltas `a5434719122a4e02ed0291d1c450d85f2de31eed`.
- Revisão estática enviada ao PR #25. Os novos testes não foram executados em runtime/compileall nesta etapa. CI não é evidência de execução se o job não iniciar steps.
- PR #25 permanece Draft e sem merge; `main`, fixtures RAW, SQLite persistente, checkpoints, RPC/Helius e estado on-chain permanecem intocados.


## 116. Vinculação obrigatória à assinatura primária da transação — PR #25 (18/11/2026)

- Auditoria identificou que o pipeline aceitava ausência do campo `transaction.signatures` e também aceitava a assinatura solicitada em qualquer posição da lista. Em Solana, a assinatura que identifica a transação é a primeira da lista; aceitar uma assinatura secundária ou payload sem assinaturas enfraquece a vinculação do RAW à notificação recebida.
- O pipeline agora exige lista de assinaturas presente, não vazia, composta apenas por strings não vazias, sem duplicatas, e exige `signatures[0] == signature`.
- A validação duplicada mais permissiva na camada de persistência foi removida; a camada persiste o RAW/normalização e o pipeline transacional retorna REJECTED, mantendo a assinatura sem checkpoint quando a vinculação falha.
- Testes negativos adicionados para assinaturas ausentes, assinatura solicitada apenas em posição secundária e lista com duplicatas. Fixtures de WalletMonitor atualizadas para refletir a resposta RPC Solana com assinatura primária.
- Implementação: `f4c075ebb63efe658364b29a71c15f5fca0d8d2d`; remoção da checagem duplicada na persistência: `e419f4158a27e3177e492a63d72995bb468bb5ff`; testes do pipeline: `b5c0512ba4eb8f519b4d66ed72a7b867ded6b84a`; fixtures WalletMonitor: `ad9bc80c03f56f5e3b888838e35a1ae05ed69a1b`.
- Revisão estática enviada ao PR #25. Testes runtime/compileall ainda não foram executados para esses commits; CI sem steps/logs não conta como validação.
- PR #25 permanece Draft e sem merge; `main`, fixtures RAW, SQLite persistente, checkpoints, RPC/Helius e estado on-chain permanecem intocados.

- CI do HEAD `c04cdfa910e36fccf23a66c9f220c92ffb72655d`: run #726 (`44318847758`), job `134852085527`, `steps=null` e `logs_url=null`. Falhou antes de disponibilizar etapas/logs; não há evidência de execução de unittest/compileall. Nenhum retry foi disparado.

- CI do HEAD `50c64ead640aa2ae1be4eefb60dad32587114423`: run #717 (`44318265798`), job `134850068290`, falhou antes de iniciar steps (`steps=null`, `logs_url=null`). Não comprova falha nem aprovação dos testes; sem retry automático.


## 117. Correção de fixtures e assinatura primária no coordenador CPMM — PR #25 (18/11/2026)

- Auditoria dos call sites de `simulated_transaction()` em `tests/test_wallet_monitor.py` encontrou fixtures que usavam a assinatura padrão em cenários com outra assinatura solicitada. Corrigidos os retornos dos data sources para propagar o argumento `signature`; corrigido também o RAW arquivado para replay de primeira execução (`pending-first-run`).
- Revisão da coordenação DAMM→CPMM identificou que a validação de assinatura primária estava no pipeline DAMM, mas o CPMM ainda aceitava `transaction.signatures` ausente e assinatura solicitada em posição secundária. Isso deixava um caminho independente/failed-on-chain mais permissivo.
- O pipeline CPMM agora exige lista de assinaturas presente, não vazia, somente strings não vazias, sem duplicatas, e `signatures[0] == signature`, antes de normalizar ou persistir.
- Adicionados testes negativos CPMM para assinaturas ausentes, secundárias e duplicadas; fixture base do teste agora contém a assinatura primária correspondente.
- Idempotência verificada estaticamente no `SQLiteEventStore.save_swap_bundle()`: os três contratos são gravados em uma única transação SQLite, com `ON CONFLICT(operation_id) DO UPDATE`; replay após falha parcial de múltiplos bundles atualiza os já persistidos sem duplicar operações. Cada bundle é atômico; o lote completo não é uma única transação.
- Commits desta rodada: fixtures WalletMonitor `2b53a5d5a129f38465e3d453b9c254b82694264b` e `31bde375367f54ea9348ec1d5b7b99b621b1b02f`; validação CPMM `689e8eb311b01018ad5cd3ea5154e38f1324d38f`; testes CPMM `14a0eeabfff92802f7befc93185bc579ce99ad91`.
- Revisão estática apenas: não houve execução runtime/compileall nesta rodada; CI sem steps/logs continua sem valor probatório. PR #25 permanece Draft e sem merge; `main`, fixtures RAW, SQLite persistente, checkpoints, RPC/Helius e estado on-chain permanecem intocados.


## 120. ID JSON-RPC estritamente inteiro — PR #25 (18/11/2026)

- Hardening adicional da validação do envelope: Python considera `True == 1`; portanto, comparar apenas igualdade permitiria que resposta JSON com `id: true` fosse aceita para requisição `id: 1`.
- O cliente agora exige ID de resposta do tipo inteiro JSON, rejeita booleanos e compara com o ID enviado.
- Adicionado teste negativo específico para `id: true`.
- Commits: cliente `ff1b04eaf076c91a8d84c445add6cac5320fefd7`; teste `1e9d010906bcfa065669d80641807c6b897efda8`.
- Revisão estática; runtime/compileall pendentes. Nenhuma chamada RPC real. PR #25 Draft, sem merge e sem alterações em main/estado persistente.


## 121. Envelope JSON-RPC do WebSocket logsSubscribe — PR #25 (18/11/2026)

- Auditoria do WalletMonitor encontrou a mesma classe de coerção booleana no WebSocket: em Python, `True` pode equivaler à chave inteira `1`. IDs de requisição, IDs de assinatura e IDs de subscription recebidos em notificações agora rejeitam booleanos; identificadores precisam ser inteiros válidos.
- Respostas de inscrição também precisam declarar `jsonrpc == "2.0"`; notificações com subscription ID inválido são ignoradas, sem associação acidental à carteira de outra inscrição.
- Adicionados testes para versão JSON-RPC ausente, request ID booleano e subscription ID booleano.
- Commits: WalletMonitor `5a689b522a47a4eca6402880c45b186be35ba536`, `3961a3f9d7db3ee14e41e8c289b125ec523171c1`, `252e34e7c1b5dba7fbd7f10e2e580b9f86631a9e`; testes `28383b0f737c75b67f316f6e20cf7ee5d664a693`, `ed5939f849d4e079b486e371e2591fd6d455aba2`.
- Auditoria estática adicional de `_backfill_wallet`, `save_observation` e normalização: falhas on-chain no backfill são registradas como resultado conhecido e avançam checkpoint pelo padrão `advance_checkpoint=True`; observações pendentes são processadas antes do backfill histórico; ausência do checkpoint no limite configurado interrompe recuperação em vez de criar lacuna silenciosa. Não foi feita alteração nesses fluxos nesta rodada.
- Sem execução runtime/compileall e sem conexão WebSocket/RPC real. PR #25 continua Draft; main, banco persistente, checkpoints e estado on-chain preservados.


## 122. Validação fail-closed das páginas de assinaturas do backfill — PR #25 (18/11/2026)

- Auditoria do caminho `getSignaturesForAddress` → `_backfill_wallet` encontrou risco de lacuna silenciosa: a fonte RPC aceitava itens sem `signature`, e o backfill ignorava esses itens intermediários enquanto podia continuar até o checkpoint e avançar.
- `HeliusDataSource.get_signatures_for_address()` agora valida todos os itens da página antes de devolvê-la: cada item deve ser objeto com assinatura string não vazia e nenhuma assinatura pode se repetir na mesma página. Página malformada rejeita a chamada inteira; o backfill não recebe uma lista parcialmente válida.
- Adicionados testes para item sem assinatura e duplicata na mesma página.
- Commits: fonte `ccef35f7c217df62c7902b98be68aafa97e91885`; testes `98dc46b74ece2767451334cbc2253f407245634f`.
- Revisão estática do backfill indica que falha de página interrompe antes do processamento/avanço subsequente; o checkpoint existente permanece como referência para nova tentativa. Sem runtime/compileall ou RPC real nesta rodada. PR #25 Draft; main e estado persistente preservados.


## 123. Parser SPL valida representação bruta e identidade de token account — PR #25 (18/11/2026)

- Auditoria adicional do parser encontrou dois riscos de saldo fabricado: `uiTokenAmount.amount` aceitava representações decimais/fracionárias que não correspondem ao campo bruto inteiro do JSON-RPC; e entradas repetidas com o mesmo `accountIndex` podiam ser somadas como se fossem token accounts distintas.
- O parser agora exige `amount` como string ASCII de dígitos (unidades mínimas inteiras) e, quando `accountIndex` é fornecido, exige inteiro não negativo e identidade única por snapshot. Índices repetidos ou conflitantes invalidam as mints envolvidas e impedem delta.
- Adicionados testes negativos para amount fracionário e accountIndex duplicado.
- Commits: parser `668bdbe869eab50273a089acaecaa578dbcb8f3c`; testes `657c1175dcbbfe3e5ff9eff12f0d82f7d6187a3c`.
- Revisão estática; runtime/compileall pendentes. Nenhum dado persistente ou RPC real foi alterado.


## 124. Identidade um-para-um obrigatória na reconciliação CPMM — PR #25 (18/11/2026)

- Auditoria encontrou um caso de falsa conclusão possível: com dois swaps decodificados A e B, um reconciliador defeituoso poderia devolver dois resultados MATCHED para A. A cardinalidade seria 2 = 2, mas B ficaria sem resultado; o pipeline anterior podia considerar a contagem suficiente e avançar checkpoint.
- O CPMM agora compara as chaves completas `(instruction_index, inner_instruction_index, cpi_path)` entre swaps decodificados e resultados de reconciliação. Exige unicidade em ambos os conjuntos e igualdade exata entre eles. Duplicatas, identidades ausentes, extras ou duplicadas nos swaps mantêm a transação pendente.
- A auditoria por swap continua registrando explicitamente UNRESOLVED para a instrução sem resultado.
- Adicionado teste de regressão com dois swaps decodificados e duas respostas MATCHED duplicadas para o primeiro; o segundo é registrado UNRESOLVED e o checkpoint não avança.
- Commits: pipeline `faa53c65eba293e81707a6c3584e2f51ab5de684`; teste `1d79b5b701f757c72ff516e36f1b17309b794ac2`.
- Revisão estática; execução runtime/compileall pendente. PR #25 Draft; main e estado persistente preservados.


## 125. Bundles CPMM vinculados exatamente aos swaps MATCHED — PR #25 (18/11/2026)

- Após exigir identidade um-para-um na reconciliação, a auditoria avançou até o construtor/persistência de bundles. A checagem anterior de cardinalidade também não garantia que os bundles correspondiam aos swaps MATCHED: um builder poderia devolver o mesmo bundle duas vezes, omitindo outro swap, e ainda manter o mesmo tamanho da lista.
- O pipeline agora calcula o conjunto esperado de `operation_id` diretamente dos swaps MATCHED e compara com os bundles produzidos. Exige IDs únicos, conjunto exato, chain Solana, carteira monitorada, assinatura solicitada e consistência dos operation IDs entre observation/classification/evidence. Divergência mantém a transação pendente e bloqueia checkpoint.
- Adicionado teste de regressão com dois swaps MATCHED e builder que devolve bundle A duas vezes, omitindo B; o pipeline permanece pendente.
- Commits: pipeline `eb45db263ca39176f12b479e0960516ad003760b`; teste `de732ebe754eeeb07eea38776986e17eb53d1f22`.
- Revisão estática; runtime/compileall pendentes. Nenhuma gravação persistente real ou chamada RPC foi realizada.


## 126. Identidade única por operação nos lotes DAMM v2 — PR #25 (18/11/2026)

- Auditoria estendida ao caminho DAMM v2 encontrou que o reconciliador econômico e o adaptador de domínio validavam cardinalidade, mas não rejeitavam explicitamente duas entradas com a mesma identidade de instrução/CPI se os objetos de transferência fossem distintos.
- `reconcile_damm_v2_economic_batch()` agora rejeita identidade duplicada `(instruction_index, inner_instruction_index, cpi_path)` no mesmo lote como AMBIGUOUS.
- `build_damm_v2_swap_domain_bundles()` repete a proteção independentemente, para que o adaptador não dependa exclusivamente do reconciliador chamador.
- Testes adicionados: reconciliação econômica com transferências distintas mas mesma identidade; adaptador com contextos duplicados.
- Commits: reconciliação `89de7d3645aa3d86b5a5f7e258bd922b865ed14f`, mensagem alinhada a teste legado `43332c99917737fdcdaaba2f21648c7780fc912e`, teste econômico `97acda5a8cf2e9355533ae4127b322b98d0d3f91`, adaptador `c1ea1f8b64a1bd4cbbf56c45cee218172c8a5277`, teste adaptador `19828b904d453f4b4b85ea6c569970eab27f6d87`.
- Revisão estática; runtime/compileall ainda pendentes. PR #25 Draft; main e dados persistentes preservados.


## 127. Pipeline transacional DAMM v2 valida identidade exata dos bundles — PR #25 (18/11/2026)

- Após hardening do adaptador, a camada de orquestração DAMM v2 também passou a conferir os bundles que recebe: operation IDs precisam ser únicos e coincidir exatamente com as identidades dos contextos reconciliados; observation deve corresponder à carteira/assinatura monitoradas; classification/evidence devem compartilhar o operation_id da observation.
- Isso impede que uma implementação defeituosa/substituída do builder retorne bundles duplicados ou de outra transação mantendo apenas a cardinalidade esperada.
- Commit: pipeline transacional `10a5836c2957ffc23555d1d2715bc6b5454522b3`.
- A proteção é revisada estaticamente; testes runtime ainda não executados. O adaptador e reconciliador têm testes específicos de identidade duplicada registrados na seção 126.


## 128. Colisão de accountIndex entre owners no parser SPL — PR #25 (18/11/2026)

- Hardening do parser: a verificação inicial de duplicidade de `accountIndex` considerava apenas entradas cujo owner já era a carteira monitorada. Um índice duplicado em uma segunda entrada atribuída a outro owner poderia passar despercebido e deixar o primeiro saldo ser usado.
- O parser agora acompanha identidade de accountIndex em todas as entradas do snapshot, mesmo de outros owners. Se um índice se repete, invalida a mint de qualquer entrada envolvida que pertença à carteira monitorada; também rejeita índice malformado na entrada monitorada.
- Adicionado teste em que o mesmo accountIndex aparece para a carteira monitorada e outro owner; o delta da mint não é emitido.
- Commits: parser `bbb5e58c34311bc3e4ee4ccbb48c7c5b75d3b768`; teste `a22fe36fffcf47719b96340b8df5adf63c2beb28`.
- Revisão estática; runtime/compileall pendentes. Nenhum RPC real ou banco persistente alterado.


## 129. WalletMonitor aceita somente logsNotification JSON-RPC 2.0 — PR #25 (18/11/2026)

- Auditoria do dispatcher WebSocket identificou que qualquer mensagem com `params.subscription` e `params.result.value.signature` poderia ser tratada como notificação de logs, mesmo sem validar `method` ou versão JSON-RPC. Isso permitia que mensagens de outro método fossem confundidas com eventos de carteira.
- O monitor agora só processa notificações com `jsonrpc == "2.0"` e `method == "logsNotification"`; subscription ID continua validado como inteiro não booleano.
- Fixtures de teste atualizadas para envelopes JSON-RPC válidos; o teste de integração inclui uma mensagem de método desconhecido com assinatura forjada antes da notificação legítima e confirma que ela é ignorada.
- Commits: dispatcher `8ad9bfd7f8bdcfe1fd539c381098f03f0501dbc1`; fixtures `a376f6a9d4024586a710ab1bafa1945a769852f9`; teste `9ed84a5083ccd4516e8eab2db824c24798ae24b8`.
- Revisão estática; runtime/compileall pendentes. Nenhuma conexão WebSocket real foi aberta.


## 130. Consolidação da auditoria de identidade multi-venue e WebSocket — PR #25 (18/11/2026)

- CPMM: reconciliação agora exige cobertura um-para-um por identidade completa; bundles precisam corresponder exatamente ao conjunto MATCHED, sem IDs repetidos, e à carteira/assinatura da observação.
- DAMM v2: reconciliação econômica e adaptador rejeitam identidades de swap duplicadas; a orquestração transacional verifica operation IDs únicos e conjunto exato dos contextos reconciliados antes de retornar RECONCILED.
- WebSocket: dispatcher aceita somente `jsonrpc == "2.0"` + `method == "logsNotification"`; resposta de subscription também valida versão e IDs inteiros não booleanos. Fixtures foram atualizadas e um teste inclui mensagem de método desconhecido com assinatura forjada.
- Commit adicional de formatação das fixtures: `b5bc5ed431ffe89f80fb1a9eb063eac171698601`.
- Revisão estática das rotas DAMM persistence → WalletMonitor → CPMM: DAMM não avança checkpoint; pendência DAMM impede CPMM; CPMM é o único coordenador final de checkpoint; falhas/exceções deixam observação replayável. Falhas on-chain são resultado terminal conhecido e podem avançar checkpoint após validação no CPMM.
- Nenhum teste runtime/compileall foi executado nesta rodada; nenhum RPC/WebSocket real foi acessado. PR #25 continua Draft, main e estado persistente preservados.


## 131. Validação estrita dos argumentos do cliente Helius — PR #25 (18/11/2026)

- Auditoria de API pública encontrou coerção de booleanos em limites: `True` passava por comparações numéricas e podia ser enviado como `limit=1`; também não havia validação explícita de assinatura/cursor vazios em alguns métodos.
- `get_signatures_for_address()` agora exige carteira string não vazia, limite inteiro não booleano entre 1 e 1000 e cursores `before/until` como strings não vazias quando fornecidos.
- `get_activity()` exige limite inteiro não booleano entre 1 e 100; `get_transaction()` exige assinatura string não vazia.
- Testes negativos adicionados para limite booleano em paginação e histórico, cursor vazio e assinatura vazia.
- Commits: cliente `5e3717e17ded1ed1b15e2c9e440c072fec900f4d`; testes `c3eb02a34a11c60a9564d4387aa87e638e884845`.
- Revisão estática; unittest/compileall ainda não executados. Sem RPC real.


## 132. Validação de tipos e timeout finito em HeliusSettings — PR #25 (18/11/2026)

- Configuração aceitava timeout booleano (`True`) e valores não finitos como NaN/Infinity porque comparações `<= 0` não os rejeitam corretamente; também assumia que API key e cluster eram strings.
- `HeliusSettings` agora exige API key string não vazia, cluster string em `mainnet/devnet` e timeout numérico finito positivo, rejeitando booleanos.
- Testes adicionados para timeout booleano, NaN, Infinity, inteiro excessivamente grande, zero, negativo e API key de tipo inválido. Overflow ao avaliar finitude de inteiros gigantes é convertido em `SettingsError`.
- Commits: settings `db819ced08e3dbf9f4851405b83129d0615f6b40` e `d27d604c251881750c473f820833aa03044f5330`; testes `41ca7f2af36174e829b2c4237d83774bc569cd26` e `87fc209218ed46730e5920c81ec8a5ec3750ec29`.
- Revisão estática; unittest/compileall pendentes. Nenhuma autorização de rede ou chamada externa foi ativada.

- CI do HEAD `3b0cdb82f58ac70ff9d08ebcf1e5092d25c91eeb`: workflow `SMR tests`, run #829 (`44322124291`), job `134863546972`, terminou `failure`, mas `steps=null` e `logs_url=null`; não há evidência de que instalação, unittest ou compileall tenham iniciado. Classificar como falha de infraestrutura/runner sem diagnóstico, não como falha de teste. Não disparar retry sem logs/steps.


## 133. Validação estrita de parâmetros do WalletMonitor — PR #25 (18/11/2026)

- O construtor aceitava booleanos como números em retries/backfill e valores NaN/Infinity em parâmetros temporais; `stable_session_seconds` não tinha validação explícita. Esses valores podiam gerar comportamento imprevisível ou falhas tardias em `range`, `sleep` e backfill.
- WalletMonitor agora exige parâmetros temporais numéricos finitos (sem booleanos), backoff inicial positivo, máximo não inferior ao inicial, sessão estável e retry inicial não negativos; tentativas e limites de paginação exigem inteiros não booleanos positivos, com page limit até 1000.
- Helper trata overflow de inteiros gigantes como valor inválido. Teste cobre backoff booleano, máximo infinito, sessão NaN, retry booleano e limites booleanos.
- Commits: construtor `b65d6be329519f42ab13d15da1db07714f74ae66`, helper overflow `810dd2ff550c0b90f3aace95e1151ab0de768f0e`, testes `853d640238268ac85c4b4ff01f2a023d5e5ce14b`.
- Revisão estática; unittest/compileall pendentes. Nenhum serviço remoto ativado.


## 134. Correção sintática no teste do adaptador DAMM v2 — PR #25 (18/11/2026)

- Revisão estática dos testes encontrou uma instrução `import` em `tests/test_damm_v2_swap_domain_adapter.py` contendo sequências literais `\\n` em vez de quebras de linha reais. O arquivo não era Python sintaticamente válido e poderia impedir a descoberta/execução da suíte.
- Corrigida somente a instrução de importação; conteúdo restante preservado. Verificação posterior do conteúdo GitHub confirmou ausência de sequências literais `\\n` e import multilinha formatado corretamente.
- Commit corretivo: `a5715de67228cee087905ca1a941fbb98943fe1c`.
- Esta é uma correção revisada estaticamente, não uma validação runtime. `unittest` e `compileall` continuam pendentes no ambiente Termux/runner funcional.


## 135. Corrigida ordem de validação dos bundles CPMM — PR #25 (18/11/2026)

- Auditoria do caminho de persistência Raydium CPMM encontrou uso de `bundle_identity_mismatch` no cálculo de `unresolved` antes da atribuição da variável. Em qualquer caminho com swap decodificado, isso podia gerar `UnboundLocalError`, cair no tratamento de exceção e manter a observação em replay mesmo quando reconciliação e bundle fossem válidos.
- Reordenado o fluxo: primeiro calcula a divergência de cardinalidade/identidade das reconciliações, constrói e valida os bundles (IDs únicos, conjunto exato, chain/carteira/assinatura e consistência dos três operation IDs); somente depois calcula `unresolved` e decide se pode marcar a assinatura como processada.
- O teste já existente `test_matched_swap_is_persisted_before_checkpoint` cobre o caminho positivo MATCHED + bundle válido e deverá exercitar a variável na execução runtime.
- Commit corretivo: `e323cb91f2d6ea6c122a9d5cb11ffe97ae5c13a5`. Revisão estática posterior confirmou `bundle_identity_mismatch` definido antes do cálculo de `unresolved`.
- Ainda sem unittest/compileall runtime após a correção. Nenhum checkpoint, banco persistente, RPC ou estado on-chain foi alterado.

## 136. Imutabilidade da evidência RAW por assinatura — PR #25 (18/11/2026)

- Auditoria da persistência encontrou que `save_observation()` fazia UPSERT substituindo `payload_json` sempre que uma nova chamada trazia payload não nulo. Como a chave é `(wallet_address, signature)`, um payload divergente para a mesma assinatura poderia sobrescrever a evidência RAW original durante retry/replay.
- Adicionada guarda transacional: se já existe payload não nulo para a mesma carteira/assinatura e o novo payload serializado diverge, a operação falha com `ValueError` antes de atualizar qualquer tabela/checkpoint. Payload originalmente nulo ainda pode ser preenchido posteriormente, preservando o fluxo de falha on-chain/reconsulta.
- Adicionados testes para rejeitar payload conflitante sem alterar RAW/checkpoint e para permitir preencher payload inicialmente ausente.
- Commits: fonte `360168809ba6ac79c8e0a7c55c96a6767a010b11`; testes `6aaf9be8bc6a34959d856d236f392002c16a3b5b`.
- Revisão estática e re-leitura GitHub concluídas; runtime unittest/compileall ainda pendente. Nenhum banco persistente ou estado on-chain foi tocado.

## 137. Monotonicidade do checkpoint por slot — PR #25 (18/11/2026)

- Auditoria de WalletMonitor/EventStore encontrou que notificações/replays fora de ordem podiam regredir `wallet_checkpoints.signature`: o UPSERT anterior substituía o cursor sem comparar a posição da transação.
- `wallet_checkpoints` agora recebe coluna nullable `slot`, com migração incremental para bancos existentes. `_mark_processed_in_connection()` e `save_checkpoint()` consultam o slot da observação e só substituem checkpoint quando o novo slot é estritamente maior; se ambos os slots forem desconhecidos, mantém o comportamento legado. Um slot desconhecido não substitui checkpoint com slot conhecido; transações antigas continuam registradas em `processed_signatures` sem regredir o cursor.
- Testes adicionados para processamento fora de ordem (slot 450 depois do 500) e para impedir substituição de checkpoint conhecido por assinatura sem slot.
- Commits: fonte `b65255e29ff8adf8cf77c3229759c91adc38a1ef`; testes `68f49b842ce0cc3b1558e7b0ba2b016286371a52`.
- Revisão estática/releitura GitHub concluídas. Runtime unittest/compileall ainda não executados após as alterações. Banco persistente do usuário não foi aberto nem migrado nesta atividade.

## 138. Slot de transações com falha no backfill — PR #25 (18/11/2026)

- A monotonicidade por slot revelou um caso adjacente: o ramo de backfill para falhas on-chain arquivava `payload=None` e descartava o `slot` já fornecido por `getSignaturesForAddress`. Sem slot, uma assinatura falhada mais recente não conseguiria avançar um checkpoint que já tivesse slot conhecido.
- `save_observation()` agora aceita `slot` explícito opcional, valida inteiro não negativo (booleans rejeitados) e rejeita divergência com o slot do envelope normalizado. O backfill transmite `item.slot` ao arquivar falhas on-chain.
- Teste adicionado confirmando que o slot RPC de uma transação falhada fica gravado no checkpoint.
- Commits: EventStore `548175d93e324c16ef25e7126c8550c592940703`; WalletMonitor `10f6cd9b35914e257783d55bda75f116f7a56e76`; teste `94cddbf1c506b0ece2665de4ebdf4733615519dc`.
- Revisão estática/releitura GitHub concluídas; runtime unittest/compileall ainda pendentes.

## 139. Migração dos slots de checkpoints legados — PR #25 (18/11/2026)

- A coluna `wallet_checkpoints.slot` é adicionada incrementalmente; bancos já existentes podem ter `observed_transactions.slot` preenchido para a assinatura do checkpoint. Sem backfill da nova coluna, a primeira notificação antiga poderia substituir o cursor antes que o novo slot fosse conhecido.
- Migração agora recupera o slot do registro `observed_transactions` correspondente ao checkpoint existente, sem modificar assinatura, RAW ou dados processados.
- Teste de migração cria esquema legado com checkpoint e observação slot 1200 e confirma a recuperação do slot após inicialização.
- Commits: fonte `d632a07d28af9613c6729ef4218bd9bbd19b8ed4`; teste `4ddcf30387afb10ed3a3f39b43c0f657459177f8`.
- Runtime unittest/compileall ainda pendentes.

## 140. Checkpoint ordenado para múltiplas transações no mesmo slot — PR #25 (18/11/2026)

- A comparação estrita por slot impede regressão, mas não distingue transações diferentes no mesmo slot. Como `getSignaturesForAddress` retorna a lista em ordem cronológica reversa, o backfill já percorre `reversed(collected)` em ordem cronológica crescente.
- Adicionado `SQLiteEventStore.advance_checkpoint_in_order()`: exige assinatura já processada, observação persistida, slot inteiro não negativo idêntico ao slot arquivado e proíbe retrocesso para slot menor; permite avançar a assinatura dentro do mesmo slot somente quando chamado pelo caminho de backfill que conhece a ordem RPC.
- O backfill chama esse método após processar com sucesso cada assinatura e após arquivar falhas on-chain com slot válido. Slots ausentes não acionam avanço ordenado. Notificações live continuam sujeitas à regra conservadora de slot estritamente maior.
- Teste adicionado para duas assinaturas processadas em ordem no mesmo slot, confirmando que o checkpoint termina na segunda assinatura.
- Commits: EventStore `bba78356d91d07bb881a0f7d8205111f37442533`; WalletMonitor `b9213855505da9ea3b8850d51121464b8cebf7a2`; teste `cfbd48b4068cd1c7e9a475af8f14fe24351a2203`; guarda slot ausente `e0e50e81ae563675428c0d13f501d2ab4326c776`.
- Revisão estática e re-leitura GitHub pendentes de fechamento; runtime unittest/compileall ainda não executados.

## 141. Idempotência imutável de bundles de swap — PR #25 (18/11/2026)

- Auditoria de replay/crash parcial encontrou que `save_swap_bundle()` usava `ON CONFLICT(operation_id) DO UPDATE` nos três contratos. Uma repetição com mesma identidade determinística e conteúdo divergente poderia substituir observação/classificação/evidência silenciosamente.
- Agora, replay idêntico retorna `False` sem regravar. Replay divergente para `operation_id` existente é rejeitado por padrão e preserva os três registros. Bundle parcialmente existente também é rejeitado, sem reparo silencioso.
- Substituição continua tecnicamente possível somente com `replace_existing=True` explícito, reservado a reprocessamento deliberado. Os pipelines normais DAMM v2/CPMM não passam esse argumento e, portanto, permanecem fail-closed.
- Testes atualizados/adicionados: replay idêntico, conflito sem sobrescrita, substituição explícita e bundle incompleto sem reparo automático.
- Commits: EventStore `1656aa6626fde43cea3e67e6c931edad7642cf34`; testes `000d0123d57a340f06a9a45f8fd2a2114bfbb06c` e `9f9a49cba684c288637f3f1e24573c4eca643fb6`.
- Releitura GitHub confirmou o guard e os testes; runtime unittest/compileall ainda não executados.


## 142. Serialização das gravações críticas SQLite — PR #25 (18/11/2026)

- Auditoria de concorrência identificou que `save_observation()` e `save_swap_bundle()` consultavam o estado existente antes de obter o bloqueio de escrita SQLite. Com duas conexões/processos, ambas poderiam tomar decisões com base em leituras concorrentes antigas antes de disputar a gravação.
- As duas operações agora iniciam a transação com `BEGIN IMMEDIATE`, obtendo o bloqueio de escrita antes da leitura de RAW/bundle e mantendo a verificação + persistência atômicas. O RAW divergente continua sendo rejeitado; bundle idêntico é no-op, divergente/incompleto é rejeitado salvo substituição explicitamente autorizada.
- Commit: EventStore `ebc753a7c555c0390cfdf5abd280b7b73215e53b`.
- Revisão estática no GitHub. Runtime unittest/compileall ainda pendentes; nenhum banco persistente do usuário foi aberto.

## 143. Compare-and-swap para checkpoint no mesmo slot — PR #25 (18/11/2026)

- A função anterior `advance_checkpoint_in_order()` validava slot não regressivo, mas aceitava qualquer assinatura processada no mesmo slot. Dois workers concorrentes poderiam ler o mesmo predecessor e depois substituir o cursor um pelo outro, perdendo a ordem RPC.
- A função agora exige `expected_previous_signature`, inicia `BEGIN IMMEDIATE`, compara o cursor atual com o predecessor esperado e rejeita a atualização se outro worker já tiver avançado. Repetição quando o cursor já é a assinatura alvo permanece idempotente. Slot menor continua rejeitado.
- O WalletMonitor captura o predecessor antes de processar cada item do backfill e o transmite no avanço, inclusive para falhas on-chain. O teste cobre sequência correta no mesmo slot e rejeição de tentativa concorrente obsoleta.
- Commits: EventStore `ebc753a7c555c0390cfdf5abd280b7b73215e53b`; WalletMonitor `071444007e1feb5fa42e81dd438b969b0ea0535d`; teste `7d7d6d94ab2b3c78133f2925fc32cfb36da8e218` e ajuste de fixture `0100230332f226370e06e12a31d7c97fdaf8c7b9`.
- Revisão estática; runtime unittest/compileall ainda pendentes. Não altera `main`, SQLite persistente, RAW ou checkpoints reais.

## 144. Correção do coletor de fixture DAMM v2 — PR #25 (18/11/2026)

- Revisão do script `tools/collect_damm_v2_fixture.py` encontrou que `find_damm_v2_signature()` chamava a si própria sem condição de parada e que a função `main()` estava ausente, tornando o coletor inutilizável e fazendo o teste do catálogo terminar em recursão.
- Restaurada a função pura de seleção: exige catálogo em lista e exatamente um candidato `Meteora DAMM v2` com assinatura não vazia. Restaurado `main()`, leitura JSON do catálogo, argumentos `--candidate-file` e `--output`, diretório padrão `data/fixtures/raw/damm-v2/` e chamada ao coletor RPC somente leitura.
- Commit: `88f56b84c9d539f4904f6f939c0b49869750c1df`.
- Revisão estática; teste do catálogo e execução real da coleta ainda pendentes. Nenhuma chamada RPC foi realizada e nenhum RAW foi criado.


## 145. Testes de corrida para RAW e bundles — PR #25 (18/11/2026)

- Adicionados testes concorrentes com duas threads e banco SQLite em arquivo temporário. Para a mesma chave de observação, dois RAW divergentes disputados simultaneamente devem produzir exatamente uma gravação e uma rejeição por conflito, mantendo intacto o payload vencedor.
- Para o mesmo `operation_id`, dois bundles divergentes disputados simultaneamente devem produzir uma gravação nova e uma rejeição, preservando o bundle vencedor. Isso exercita o bloqueio obtido por `BEGIN IMMEDIATE`, não apenas o comportamento sequencial.
- Commits de teste: `98cddab2d5c3cff86c0872a949761e353dbf9030` (bundles) e `9fa31a0f6ace1ad329b16b3c9f74537d9ac2d782` (RAW); documentação `f2f2ded8b8edaa6eb2fda47a46a5f5436ace3726`.
- Revisão estática; os testes concorrentes ainda precisam ser executados no Termux/runner funcional. Nenhum RAW ou banco persistente foi alterado.


## 146. CI sem execução de etapas após hardening de concorrência — PR #25 (18/11/2026)

- HEAD avaliado: `fcf207938d38b3099d562929802afdfbbbd1bfff`.
- Workflow `SMR tests`, run #884 (`44328496652`), terminou `failure`; job `134886166955` terminou `failure`, mas `steps=[]` e `logs_url=null`. A consulta direta de steps também retornou lista vazia.
- Não há evidência de checkout, instalação, unittest, compileall ou execução de qualquer comando do projeto. Portanto, o resultado não prova falha de código nem aprovação dos novos testes concorrentes.
- Não foi disparado retry automático, pois o runner não forneceu etapas/logs para diagnóstico.
- Próxima validação executável: atualizar clone Termux da branch `feat/damm-v2-transaction-pipeline`, rodar testes focais de EventStore, bundles, coletor e WalletMonitor; em seguida executar `compileall` e suíte completa. A fixture RAW mainnet permanece pendente e não deve ser coletada até os testes locais passarem.


## 147. Backfill não pode avançar checkpoint antes do compare-and-swap — PR #25 (18/11/2026)

- Auditoria de fluxo ponta a ponta encontrou uma lacuna na proteção recém-adicionada: `process_raydium_cpmm_observation()` chamava `mark_processed()` com avanço automático. Em slots maiores, isso atualizava o checkpoint antes de `advance_checkpoint_in_order()`; o CAS então encontrava a assinatura já como cursor atual e retornava idempotentemente, sem validar o predecessor esperado. Para slots iguais, o teste anterior não expunha esse desvio.
- Corrigido com `mark_processed(..., advance_checkpoint=False)` e parâmetro `advance_checkpoint` no pipeline CPMM. O WalletMonitor usa esse modo somente no backfill; o WebSocket preserva o comportamento anterior. Assim, o backfill primeiro persiste a conclusão em `processed_signatures`, sem mover cursor, e depois executa o CAS ordenado.
- Transações do backfill com slot inválido agora interrompem a recuperação explicitamente; não são silenciosamente marcadas como avanço concluído.
- Testes adicionados: EventStore confirma processamento sem mover checkpoint e posterior CAS; pipeline CPMM confirma que modo backfill deixa cursor anterior intacto até o CAS. Commits: `d13a163`, `db89d46`, `1feaa0f`, `efdc47d`, `a551ea7`, `e9b95b5`, `7a91dab`.
- Revisão estática no GitHub. Execução runtime ainda pendente.


## 148. Observações pendentes não podem antecipar backfill ancorado — PR #25 (18/11/2026)

- A revisão do fluxo completo encontrou que `_backfill_wallet()` processava observações pendentes já arquivadas antes de consultar `getSignaturesForAddress`. Com checkpoint preexistente, esse replay poderia marcar e avançar uma assinatura fora da sequência autoritativa, contornando o CAS.
- Corrigido: quando há checkpoint inicial, o replay dessas observações usa `advance_checkpoint=False`; a consulta RPC subsequente determina a ordem e o avanço via CAS. Quando não existe checkpoint inicial, preserva-se o comportamento de bootstrap já coberto pelo teste de primeira execução, sem iniciar varredura histórica ampla.
- Commit: `2084fec2ebd62722323295b2c0d88dc7dd0261f1`. Documentação atualizada.
- Revisão estática; runtime ainda pendente.


## 149. CI #902 repetido sem iniciar etapas — PR #25 (18/11/2026)

- O push associado ao commit de código `2084fec2ebd62722323295b2c0d88dc7dd0261f1` disparou o workflow `SMR tests`, run #902 (`44329781440`).
- O primeiro job terminou `failure` sem steps nem logs (`steps=null`, `logs_url=null`). Foi solicitado rerun específico do job; a nova tentativa também terminou `failure` sem iniciar steps e sem logs.
- Isso não comprova falha de unittest/compileall nem aprovação. Runner/execução continua sem diagnóstico observável. Não repetir rerun em loop; manter runtime local Termux como validação executável.
- HEAD atual do PR após atualização do Registro Mestre: `40e5db109803dce825ec2e55b35602b73894627c`.


## 150. Verificação final de integridade do PR #25 após hardening de backfill — 18/11/2026

- HEAD atual: `0781ac8c360097b8e191317363517303b99f9ac7`; PR #25 permanece aberto, Draft e sem merge.
- GitHub confirma `mergeable=true`, `mergeable_state=unstable`; branch base é `feat/damm-v2-swap-domain-adapter`, não `main`. O PR permanece empilhado sobre essa branch-base; não fazer merge isolado sem revisar a sequência de PRs.
- PR: 194 commits, 31 arquivos, 3.247 inserções e 87 remoções.
- Verificação estática pós-alterações confirmou: EventStore tem bloqueios `BEGIN IMMEDIATE`; `mark_processed` aceita modo de deferimento; CPMM encaminha a opção aos três caminhos de conclusão; WalletMonitor usa deferimento no backfill, valida slot e só então chama CAS; testes e Registro Mestre estão presentes.
- Run #902 e seu rerun falharam sem steps/logs. Nenhuma execução de unittest/compileall pode ser declarada.
- Próxima ação operacional: atualizar clone Termux para o HEAD acima e executar primeiro os testes focais; depois suíte completa e compileall. A coleta da fixture mainnet continua bloqueada até essa validação.


## 151. Teste de regressão para pendência arquivada com checkpoint existente — 18/11/2026

- Adicionado teste assíncrono em `tests/test_wallet_monitor.py` para cenário que não estava coberto: há checkpoint anterior e uma observação pendente arquivada posterior.
- O teste verifica que o replay preliminar da pendência não altera o checkpoint antes da consulta `getSignaturesForAddress`; em seguida a assinatura aparece na sequência RPC, é processada e o cursor avança por CAS para ela. Também confirma que a assinatura termina processada e deixa de constar como pendente.
- Commit: `839e873017a61f869515e30268379cd9cb2bad29`.
- Teste ainda não executado em runtime. Próxima validação continua sendo Termux; CI #902 não forneceu steps/logs.


## 152. Semântica correta de checkpoint_advanced no modo deferido — 18/11/2026

- Auditoria do novo modo `advance_checkpoint=False` encontrou que o pipeline CPMM continuava retornando `checkpoint_advanced=True` nos resultados de sucesso/no-swap/falha on-chain, embora o cursor estivesse deliberadamente parado para o CAS do WalletMonitor.
- Corrigido: os resultados agora refletem o argumento efetivo `advance_checkpoint`; no modo deferido retornam `False`. Isso evita que consumidores interpretem processamento persistido como cursor já avançado.
- Teste `test_backfill_mode_marks_processed_without_advancing_checkpoint` atualizado para exigir `checkpoint_advanced=False` e depois comprovar o CAS separado.
- Commits: implementação e teste em `033f0d2de6558762b9dd42bbc37dd391598d57db`; documentação atualizada neste registro.
- Revisão estática; execução runtime pendente.


## 153. Correção do isolamento transacional em teste SQLite — 18/11/2026

- Execução Termux após fast-forward para HEAD `9d248f053f8fe16356d0cdec6d5c3cdf90bc4ae3`: `test_event_store.py` passou (26 testes). `test_swap_persistence.py` teve 1 erro e 22 testes passaram.
- Erro: `sqlite3.OperationalError: cannot start a transaction within a transaction` em `test_incomplete_existing_bundle_is_not_silently_repaired`.
- Causa identificada no teste: o DELETE manual em conexão SQLite compartilhada `:memory:` não era confirmado antes da próxima chamada, que inicia `BEGIN IMMEDIATE`. Corrigido envolvendo o DELETE em `with connection:`, garantindo commit/fechamento da transação do teste.
- Commit da correção: `c1c87ae61517eb6e1550bb257fe300c9a4ed0f62`.
- A correção ainda não foi executada em runtime. Reexecutar `test_swap_persistence.py`; se passar, prosseguir com os três testes focais restantes e compileall.


## 154. Validação runtime parcial e novo diagnóstico de CI — PR #25 (18/11/2026)

- HEAD de referência desta atualização: `357361c6dac197fe277fc47ec2a8ae38bd591ca6`; PR #25 permanece aberto, Draft, sem merge, com base `feat/damm-v2-swap-domain-adapter`. A branch `main` permanece preservada.
- Resultado runtime informado pelo usuário no Termux após fast-forward para esse HEAD: `test_swap_persistence.py` passou integralmente, **23 testes OK**. A execução anterior de `test_event_store.py` já havia passado com **26 testes OK**. Esses resultados são evidência runtime local para os dois módulos, não aprovação da suíte completa.
- Ainda não há resultado runtime para `test_damm_v2_fixture_collector.py`, `test_raydium_cpmm_persistence_pipeline.py`, `test_wallet_monitor.py`, `compileall` ou suíte completa.
- CI no HEAD: workflow `SMR tests`, run #916 (`44331026593`) terminou `failure`. A consulta do job `134895145577` retornou `steps=null` e `logs_url=null`; portanto não há evidência de checkout, instalação, unittest ou compileall. Não classificar como falha de código nem aprovação; não repetir rerun sem diagnóstico de execução.
- Revisão GitHub confirmou que o workflow contém etapas explícitas de checkout, Python 3.12, instalação, unittest completo e compileall, mas o run #916 não expôs execução dessas etapas.
- Próxima ação de validação: continuar a revisão estática pelo GitHub dos três módulos de teste restantes e das respectivas implementações; buscar um caminho de CI executável antes de declarar testes aprovados. A fixture RAW mainnet continua bloqueada até validação runtime focada e suíte completa. Não alterar `main` nem fazer merge do PR #25.


## 155. Validação estrita da identidade JSON-RPC no coletor de fixtures — PR #25 (18/11/2026)

- Auditoria estática do coletor `RpcFixtureCollector` identificou uma lacuna de protocolo: a resposta de `getTransaction` era aceita sem validar `jsonrpc == "2.0"` nem confirmar que o ID inteiro da resposta correspondia ao ID `1` enviado. Isso enfraquecia a correlação entre requisição e resposta usada como evidência da fixture.
- O coletor agora rejeita versão JSON-RPC ausente/incorreta e ID ausente, divergente, booleano ou de tipo inválido antes de aceitar o campo `result`. A verificação da assinatura solicitada e do slot permanece adicional, não substituta.
- Testes adicionados para versão ausente/1.0, ID divergente e booleano; fixture do teste de resultado nulo atualizada para incluir envelope JSON-RPC válido.
- Commits: implementação `db7a6ade8e1ec61640a703e662a4cd64b9b9fbff`; testes `81a70ec413af112090e835c931239cfd90e0a5c6` e ajuste de cobertura `e9bdd7d2c90024267842d9f99e99e82533135401`.
- Releitura GitHub confirmou a implementação e os testes adicionados. Runtime unittest/compileall ainda não executados para esta alteração. A consulta de runs associadas ao commit final ainda não retornou workflow; não declarar CI executado.
- PR #25 permanece Draft, aberto e sem merge; base empilhada `feat/damm-v2-swap-domain-adapter`. A fixture RAW mainnet segue bloqueada até validação runtime focada e suíte completa.


## 156. CI #922 sem steps após hardening do coletor RPC — PR #25 (18/11/2026)

- O push de alterações no coletor e seus testes disparou o workflow `SMR tests`, run #922 (`44331723476`), associado ao PR #25 e ao commit de teste `e9bdd7d2c90024267842d9f99e99e82533135401`.
- A consulta do job `134897601983` retornou `steps=null` e `logs_url=null`, embora o run tenha concluído como `failure`. Não há evidência de checkout, instalação, unittest ou compileall. Não classificar como falha dos testes nem aprovação.
- Não foi disparado rerun: o padrão de falha pré-etapas permanece sem diagnóstico observável e retries repetidos não acrescentam evidência.
- Os commits de código/teste permanecem na branch do PR; validação runtime do novo hardening JSON-RPC ainda pendente. PR #25 segue Draft, sem merge e empilhado sobre `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 157. Runner não provisionado e hardening adicional do coletor RPC — PR #25 (18/11/2026)

- Consulta direta à API do GitHub para o run #922 (`44331723476`) detalhou o job `134897601983`: `runner_id=0`, `runner_name=""`, `steps=[]`, início em `15:06:18Z` e conclusão em `15:06:20Z`. A evidência é consistente com falha de alocação/inicialização do runner antes de qualquer step; não é falha demonstrada de unittest/compileall. O endpoint de logs também retornou 404 (blob inexistente). Não fazer retries em loop; a causa está fora do código de teste observável pelo repositório.
- Auditoria do coletor `RpcFixtureCollector` encontrou que `bool` era aceito como slot por ser subtipo de `int`, versões de transação não eram validadas e a assinatura podia estar em posição secundária, repetida ou num campo `signatures` que nem fosse lista.
- Corrigido para exigir slot inteiro não booleano e não negativo; versão `legacy` ou inteiro não booleano não negativo; objeto `transaction`; lista não vazia de assinaturas string não vazias, sem duplicatas e com a assinatura solicitada na posição primária (índice 0). Campo `error` não nulo agora é rejeitado mesmo se for um objeto vazio. O valor de versão validado é reutilizado no manifesto.
- Testes negativos adicionados para slot booleano/negativo, versão nula/booleana/negativa/objeto e assinatura em formato incorreto, posição secundária, duplicata e item inválido.
- Commits: implementação `6d0bd74de6b8c8c811cbe57f6273b9cd67c22bc1`; testes `14093a16d9396d4f2ef771e7ed9081b227636645`; limpeza `a0069e093c13024270d0d048387f5fa1a1aac1e8`; teste de versão nula `eb50a431163ef6c5cab4f14e125b5a605469e4db`.
- Alterações revisadas estaticamente no GitHub. Runtime unittest/compileall ainda não executados para estes commits; CI depende de runner funcional. Fixture RAW mainnet segue bloqueada até execução runtime e revisão da fixture real.
- PR #25 permanece aberto, Draft, sem merge, com base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 158. Reincidência de falha de provisionamento do runner — CI #932 (18/11/2026)

- O commit `4f40a51518fc9b808e8e7e04eaf08c7728306fae` disparou run #932 (`44332421990`). A consulta direta ao endpoint de jobs confirmou novamente: job `134900072387`, `runner_id=0`, `runner_name=""`, `steps=[]`, início `15:09:57Z`, fim `15:09:59Z`, conclusão `failure`.
- A repetição confirma que o workflow está sendo disparado corretamente, mas nenhum runner `ubuntu-latest` chega a ser atribuído ao job. Portanto, a falha está na alocação/infraestrutura GitHub Actions ou na disponibilidade de runner para o repositório, antes de checkout e antes de qualquer teste. Não alterar código de produção para tentar corrigir esse sintoma e não repetir retries em loop.
- A alteração RPC recente segue validada apenas por inspeção estática no GitHub; execução runtime ainda pendente. Para runtime sem Termux, é necessário restabelecer runner GitHub Actions ou usar outro executor autorizado e conectado ao repositório.
- PR #25 segue Draft, aberto, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 159. Coletor RPC: configuração temporal estrita e CI #933 — PR #25 (18/11/2026)

- Auditoria adicional encontrou que `timeout` e `min_interval_seconds` aceitavam booleanos e valores não finitos; inteiros gigantes podiam gerar `OverflowError` dentro de `math.isfinite`. Implementado helper `_is_finite_number`, que rejeita booleanos, tipos não numéricos, NaN, infinitos e inteiros que excedem a conversão numérica segura. Timeout deve ser finito e positivo; intervalo deve ser finito e não negativo.
- Testes negativos adicionados para timeout/intervalo booleanos, zero/negativos, NaN, infinito, string e inteiro excessivamente grande. Também foi adicionado teste garantindo que qualquer campo `error` JSON-RPC não nulo seja rejeitado, mesmo quando objeto vazio.
- Commits: helper/configuração `0b6fd719395cca7601931e24b4b7a3ca31acae14`, robustez contra inteiro excessivo `cf801cde448f51829b3d869372231100731bd97a`, testes temporais `be869a2bc5ee7e72a0b8fbb9312a9bf645513f1e`, teste de erro RPC `6b5944551e7ae6cf8df2081b73a4b28476ee34ba`.
- CI #933 (`44332520139`), disparado no HEAD anterior `f2541b7`, repetiu falha de job sem steps/logs. A API confirmou `runner_id=0`, `runner_name=""`, `steps=[]`, duração aproximada de 2 s. Runner `ubuntu-latest` continua sem provisionamento; testes não foram executados.
- Código e testes do coletor foram relidos no GitHub após as alterações; revisão estática apenas. Runtime unittest/compileall ainda pendente. Não coletar fixture RAW mainnet até validação runtime.
- PR #25 continua Draft, aberto, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 160. Revisão dos novos testes temporais e CI #942 — PR #25 (18/11/2026)

- Revisão estática dos testes temporais detectou que `repr(10**10000)` no parâmetro de `subTest` poderia lançar `ValueError` pela proteção de conversão de inteiros muito grandes do Python, antes de testar o construtor. Corrigido usando rótulos descritivos estáveis para cada caso, mantendo a entrada inteira gigantesca no teste de rejeição.
- Commit da correção do teste: `163fbbbdbe66b4fed394b855a2e06bdda4d37591`.
- CI #942 (`44332736153`), HEAD `684917bbc4061cf08d089b2a3142c14ddb65c991`, job `134901176367`: `runner_id=0`, `runner_name=""`, `steps=[]`, duração aproximada de 4 s. Repetição do problema de provisionamento do runner, sem execução de testes. O commit de correção dos testes ocorreu depois desse run, portanto não foi coberto por ele.
- Código e testes RPC reconsultados no GitHub após correções; revisão estática, sem runtime. Aguardar runner funcional para unittest e compileall; não coletar fixture mainnet antes disso.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 161. Limites do protocolo Solana e CI #943/#944 — PR #25 (18/11/2026)

- Coletor RPC agora limita `slot` ao intervalo unsigned 64-bit (`0..2**64-1`) e restringe `version` a `"legacy"` ou `0`, coerente com `maxSupportedTransactionVersion: 0` enviado na requisição. Versões futuras/inesperadas e slots fora do domínio são rejeitados antes de persistir RAW. Testes negativos ampliados para `slot=2**64` e `version=1`.
- Commits: implementação `cc3344690bd19a8994dea880f0541051b2e55ac3`; testes `cd4965e04460e174e17ff8b1bffc53b0a0f9266a`.
- CI #943 (`44332831615`) e #944 (`44332856069`) foram disparados no commit `163fbbbdbe66b4fed394b855a2e06bdda4d37591`; ambos jobs falharam sem executar steps. API confirmou runner IDs `0`, nomes vazios, listas de steps vazias e duração aproximada de 3 s. São novas ocorrências do problema de provisionamento, não resultados dos testes. As alterações de limite de slot/versão ocorreram após esses runs e não foram testadas por eles.
- Revisão estática do coletor/testes segue em andamento; runtime e compileall ainda pendentes. Não repetir reruns automáticos; não coletar fixture RAW mainnet.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 162. Documentação do coletor e CI #951 — PR #25 (18/11/2026)

- `docs/DAMM-V2-TRANSACTION-PIPELINE.md` agora documenta as validações do coletor RPC: envelope JSON-RPC 2.0 e ID correspondente, rejeição de erro não nulo, assinatura primária única, slot unsigned 64-bit, versão `legacy`/0 e parâmetros temporais finitos/estritos. Commit `3fea83f58d2d84b87195b1b68f5ea723d4a2f9c7`.
- CI #951 (`44333240301`) associado ao commit documental acima terminou failure; job `134902924895` tem `runner_id=0`, nome vazio e `steps=[]`, com duração aproximada de 3 s. Confirma que o job não chegou a executar steps. Causa operacional exata (por exemplo, disponibilidade/limite de runner) não foi exposta pela API consultável; não atribuir a quota/billing sem evidência.
- O HEAD atual do PR foi confirmado com a implementação e testes RPC atualizados; runtime ainda não foi executado devido à ausência de runner. A revisão estática não substitui unittest/compileall.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 163. Analyzer DAMM v2 independente em fail-closed e CI #954/#955 — PR #25 (18/11/2026)

- Auditoria encontrou que chamadas diretas a `analyze_damm_v2_swap_events()` podiam interpretar `innerInstructions` ausente/nulo como lista vazia e, em outros casos, retornar `[]` para transaction/meta/message/instructions ausentes ou quando `meta.err` não existia. Isso poderia confundir metadado insuficiente com ausência comprovada de swap se o analyzer fosse usado fora do pipeline transacional.
- Analyzer agora exige `transaction` e `meta` objetos, campo explícito `meta.err`, `transaction.message` objeto, `message.instructions` lista e `meta.innerInstructions` lista. Transação com `meta.err` não nulo continua retornando lista vazia porque a falha on-chain é conhecida; metadados ausentes/nulos levantam `ValueError`.
- Testes negativos adicionados para `meta.err` ausente, `message.instructions` ausente e `innerInstructions` ausente/nulo. Commits: implementação CPI `13e0d9b784d9106c0ca7d0e0e378bce38e3eed03`, testes CPI `ebc9018d0c6278a2471c0bf05ba4d9c8af85399f`; validação de execução/mensagem `e18445672e752a88e6e89a78cf1b71180072f505`, testes `4ff8360c908f614f9c07396c058862b7547ebd2c`; documentação `c891fe2c33af850516025f3591d76cb9f99e575e`.
- CI #954 (`44333690855`) e #955 (`44333692330`) repetiram falha sem runner: jobs `134904496188` e `134904503144`, ambos `runner_id=0`, nomes vazios, steps vazias, ~3 s. As alterações subsequentes do analyzer/testes ocorreram depois desses runs e ainda não tiveram execução runtime.
- Revisão estática no GitHub confirmou as novas condições e testes. Runtime unittest/compileall segue bloqueado pela ausência de runner; não declarar testes aprovados e não coletar fixture mainnet.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 164. Metadados obrigatórios do analyzer e CI #962 — PR #25 (18/11/2026)

- O endurecimento do analyzer independente foi completado: ausência/invalidez de `transaction/meta`, ausência de `meta.err`, `transaction.message` inválido, `message.instructions` ausente/não-lista e `meta.innerInstructions` ausente/nulo são erros explícitos. Somente uma transação com falha on-chain comprovada (`meta.err` não nulo) retorna lista vazia de operações.
- Testes negativos para `meta.err` e `message.instructions` ausentes foram adicionados; os testes anteriores cobrem `innerInstructions` ausente/nulo. Commits `e18445672e752a88e6e89a78cf1b71180072f505` e `4ff8360c908f614f9c07396c058862b7547ebd2c`.
- Documentação atualizada para refletir os metadados obrigatórios do analyzer independente. Commit `e13d6f2ed68b56436e090d3f49a6aac5c6524984`.
- CI #962 (`44333898967`), HEAD `f1b5e50ae442a49cd6fffb79c9d22b07902be7dc`, job `134905241316`: `runner_id=0`, nome vazio, `steps=[]`, ~3 s. Falha antes da execução. As alterações finais do analyzer/documentação foram posteriores e não foram executadas em runtime.
- Revisão estática GitHub confirmada. Runtime unittest/compileall continua bloqueado por ausência de runner; não declarar testes aprovados nem coletar fixture mainnet.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 165. CI #963/#964 confirma falha pré-runner no HEAD atual — PR #25 (18/11/2026)

- Run #963 (`44334123428`), commit `e13d6f2ed68b56436e090d3f49a6aac5c6524984`, e run #964 (`44334170775`), HEAD do PR `22115b529a909fd9df44884468496f41e4dc899c`, concluíram em failure antes de qualquer step.
- Para o run #964, job `134906226864`: `runner_id=0`, `runner_name=""`, `steps=[]`, início `15:18:49Z`, conclusão `15:18:51Z`. Confirma que até o HEAD atual do PR não houve runner provisionado; nenhuma etapa de instalação, unittest ou compileall foi executada.
- Não disparar rerun repetido. O código e os testes foram atualizados no GitHub, mas validação runtime requer que GitHub Actions consiga atribuir um runner ou que exista executor autorizado alternativo. Não coletar fixture RAW mainnet antes da validação.
- PR #25 permanece aberto, Draft, mergeable, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 166. CI runner labels alternativos e assinatura Base58 limitada — PR #25 (18/11/2026)

- Tentativa de estabilização do CI: workflow alterado de `ubuntu-latest` para `ubuntu-24.04` com timeout de 20 min (commit `bab75d8e89462ed87a27e759716566b42018fe6e`); depois para `ubuntu-slim` com timeout de 14 min, compatível com limite desse runner (commit `c1ab9cc499c6a5cd8c9d9bba1435f3762f417c48`). Documentação oficial confirma que `ubuntu-slim` é opção padrão também para repositórios privados.
- CI #968 (`44334936768`) e #969 (`44334953397`) falharam antes de steps mesmo após pinagem em `ubuntu-slim`; run #970 (`44335052271`) no commit `63936f3df0dfb08d7913412cf5e9549d1822651a` também terminou failure com job sem steps/logs. Não há evidência de que o workflow tenha iniciado; trocar a label não resolveu.
- Auditoria do coletor RPC identificou vetor de consumo desnecessário de CPU/memória: assinatura Base58 arbitrariamente longa era convertida em inteiro antes de verificar comprimento decodificado. Agora o validador rejeita strings com mais de 88 caracteres antes da conversão; teste negativo de 89 caracteres adicionado. Commits `63936f3df0dfb08d7913412cf5e9549d1822651a` e `005b4f16f4bd7277da42071977ef8529ff4eb2e9`.
- A página pública GitHub Status consultada em 18/11/2026 mostra Actions operacional e nenhum incidente reportado nesse dia. Isso não exclui restrição individual da conta/repositório. Há relatos públicos recentes de outros usuários com assinatura idêntica (`runner_id=0`, nome vazio, steps vazias, logs 404), inclusive discussões que associam o comportamento a bloqueio de uso/cobrança em repositórios privados; não é possível atribuir essa causa à conta SMR sem consultar seu painel de cobrança ou anotação interna do job.
- Próxima verificação necessária fora do acesso do conector: proprietário confirmar em Settings → Billing and licensing → Usage se o compute incluído de Actions foi esgotado ou se existe bloqueio/budget. Não adicionar método de pagamento, alterar visibilidade do repositório ou aceitar custos sem decisão expressa do usuário. Alternativa sem custo de runner hospedado: self-hosted runner, mas exigiria instalação e autorização no dispositivo do usuário.
- Runtime unittest/compileall ainda pendente; não coletar fixture mainnet. PR #25 permanece Draft, aberto, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 167. Retorno ao runner padrão e CI #974/#975 — PR #25 (18/11/2026)

- Após teste diagnóstico com `ubuntu-slim`, workflow retornou a `ubuntu-24.04` com timeout de 20 min para preservar capacidade e evitar o limite rígido de 15 min do runner slim. Commit `e267c39ae7939f122df86a8789036d0fd43ad2e7`; blob atual do workflow `d013ff5bb0f37a8004ce65ac0fd95fd53e7c58af`.
- CI #974 (`44335188436`) e #975 (`44335201908`), ambos no HEAD `e267c39ae7939f122df86a8789036d0fd43ad2e7`, terminaram failure. Jobs `134909840361` e `134909888028` retornaram `logs_url=null` e `steps=null`; consulta individual de logs retorna 404 BlobNotFound. Não houve evidência de execução de qualquer etapa. O problema persiste com `ubuntu-latest`, `ubuntu-24.04` e `ubuntu-slim`.
- GitHub Status consultado em 18/11/2026 informa Actions operacional e nenhum incidente reportado no dia. Isso, combinado com falhas pré-runner em múltiplos labels, desloca a hipótese principal para uma restrição de conta/compute/budget ou falha específica não exposta pelo job; a causa exata não é observável pelas permissões atuais do conector.
- Documentação oficial: runners hospedados em repositórios privados consomem compute incluído; GitHub Free inclui US$12/mês, e, sem método de pagamento válido, o uso é bloqueado após consumir a cota. Runners auto-hospedados e runners padrão em repositórios públicos não consomem essa cota. Não tornar o repositório público nem adicionar pagamento sem consentimento explícito.
- Próxima ação indispensável para fechar o diagnóstico: proprietário abrir Settings → Billing and licensing → Usage e conferir o consumo de GitHub Actions compute e os budgets/bloqueios. Se a cota estiver esgotada, aguardar reset ou escolher conscientemente entre método de pagamento/budget e self-hosted runner. O usuário deve enviar o valor/estado exibido; não precisa compartilhar dados de cartão.
- Runtime unittest/compileall permanece pendente; não coletar fixture mainnet. PR #25 Draft, aberto, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 168. CI #976 e reconciliação do estado atual do PR #25 (18/11/2026)

- Consulta direta à API confirma PR #25 aberto, Draft, não merged, `mergeable=true`, com HEAD `ef8289df552532137a7d88a7e176631002ef43ea` e base `feat/damm-v2-swap-domain-adapter`. A lista atual contém 34 arquivos alterados; `main` permanece fora do alvo deste PR empilhado.
- CI #976 (`44335312235`), disparado no HEAD atual `ef8289df552532137a7d88a7e176631002ef43ea`, concluiu em failure. Job `134910278443` retornou `steps=null` e `logs_url=null`. Nenhuma etapa de checkout, instalação, unittest ou compileall foi comprovada. Isso não caracteriza falha dos testes nem aprovação.
- A reincidência confirma que a troca entre `ubuntu-latest`, `ubuntu-24.04` e `ubuntu-slim` não resolveu a ausência de runner. Não disparar retries em loop e não alterar código de produção/workflow apenas para contornar falha pré-runner.
- Testes runtime já comprovados pelo usuário no Termux: `test_event_store.py` (26 testes OK) e `test_swap_persistence.py` (23 testes OK), após correção de transação no teste SQLite. Não repetir esses testes sem motivo.
- Ainda pendentes em runtime: `test_damm_v2_fixture_collector.py`, `test_raydium_cpmm_persistence_pipeline.py`, `test_wallet_monitor.py`, `test_rpc_fixture_collector.py`, `test_damm_v2_analyzer.py`, `test_damm_v2_persistence_pipeline.py`, `test_damm_v2_transaction_pipeline.py` e `python -m compileall -q src tests`. Antes de coletar fixture RAW mainnet, executar os testes restantes e revisar o resultado.
- A causa específica do provisionamento continua não confirmada. O próximo avanço técnico confiável é executar os testes restantes em runtime no clone local do usuário ou restabelecer runner GitHub Actions. Não tornar o repositório público, não ativar pagamento e não fazer merge sem decisão expressa.
- PR #25 segue Draft, aberto, sem merge; branch `feat/damm-v2-transaction-pipeline` continua baseada em `feat/damm-v2-swap-domain-adapter`.


## 169. Primeiro ciclo de runtime dos testes restantes e ajuste de mensagem — PR #25 (18/11/2026)

- O usuário atualizou o clone Termux até o commit `4be884d333f86d3449af3afe2ba48ba7123e38e9` (Registro Mestre seção 168) e iniciou a bateria pendente.
- `test_damm_v2_fixture_collector.py`: 2 testes executados, OK.
- `test_raydium_cpmm_persistence_pipeline.py`: 13 testes executados; 12 passaram e 1 falhou exclusivamente porque a asserção `assertRaisesRegex(ValueError, "não corresponde")` esperava uma expressão que não estava presente na mensagem emitida. A validação rejeitou a assinatura divergente antes da persistência, conforme esperado; não há evidência de defeito na regra de rejeição.
- Correção aplicada diretamente na branch `feat/damm-v2-transaction-pipeline`, commit `c9a772a90a12539237899868f409f2f8f0a2836a`: mensagem agora declara explicitamente `A assinatura informada não corresponde à primeira assinatura única do payload RPC.` A regra de validação não foi enfraquecida. A presença do novo texto foi confirmada via leitura do arquivo no GitHub.
- Como o loop do usuário foi interrompido no primeiro teste com falha, `test_wallet_monitor.py`, `test_rpc_fixture_collector.py`, `test_damm_v2_analyzer.py`, `test_damm_v2_persistence_pipeline.py`, `test_damm_v2_transaction_pipeline.py` e `compileall` ainda não foram executados nessa bateria. Reexecutar após sincronizar o novo commit; não repetir o teste já aprovado do fixture collector, salvo necessidade.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; não coletar fixture RAW mainnet antes da validação runtime completa.



## 170. Correção do processamento diferido no backfill e alinhamento dos testes WalletMonitor — PR #25 (18/11/2026)

- A execução runtime do usuário confirmou 3 erros e 1 falha em `test_wallet_monitor.py`, mas a saída fornecida não continha tracebacks; a execução foi interrompida durante reconexões WebSocket. Não atribuir causa ao ciclo de reconexão sem evidência.
- Auditoria estática identificou defeito real em `src/smart_money_radar/services/wallet_monitor.py`: `_collect_transaction(..., advance_checkpoint=False)` passava o modo de checkpoint diferido ao pipeline CPMM, mas depois tratava `result.checkpoint_advanced == False` como falha de processamento. No backfill, esse valor é falso por projeto; o cursor só deve avançar depois pelo CAS ordenado com slot e assinatura da página RPC. Assim, swaps corretamente reconciliados eram indevidamente mantidos como pendentes e impediam o CAS.
- Correção aplicada diretamente na branch do PR, commit `bcbe05d2565f9ecdf623c89084d4404d2358dcb6`: o monitor agora determina conclusão pelo status terminal (`processed`, `failed_on_chain`, `no_cpmm_swaps`) e por `unresolved_swaps == 0`, sem confundir conclusão do processamento com avanço do checkpoint. Status pendentes continuam bloqueando.
- Alinhamento dos testes, commit `dc300604e629c80fc36addcd041bd491d8536eb2`: fixtures do backfill agora incluem slots RPC explícitos para transação nova e falha on-chain; mock DAMM do teste de bloqueio inclui `unresolved_swaps=1`, conforme o contrato real do resultado.
- Esses commits foram aplicados no GitHub e ainda não foram validados em runtime. Próxima ação: sincronizar o clone Termux e executar primeiro apenas `test_wallet_monitor.py` com `-v` e timeout; se passar, continuar os testes pendentes restantes e `compileall`. Não coletar fixture RAW mainnet antes de concluir a validação e revisar a fixture real.
- PR #25 permanece aberto, Draft, sem merge, base `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 171. Diagnóstico da falha de checkpoint no teste de backfill — PR #25 (18/11/2026)

- A execução runtime de `test_wallet_monitor.py` confirmou que a correção do processamento diferido funcionou para os casos de falha on-chain, replay pendente e bloqueio por swap DAMM v2. Restou uma falha em `test_backfills_signatures_since_persisted_checkpoint`.
- Causa identificada por inspeção do teste e do contrato de persistência: a página simulada de `getSignaturesForAddress` informava slot 901, mas a transação simulada de `getTransaction` não continha o campo `slot`. O normalizador persistia a observação com slot `None`; o CAS ordenado corretamente rejeitava avançar para slot 901, pois exige igualdade entre o slot da página RPC e o slot persistido.
- Correção de teste aplicada na branch do PR: a fixture de `new-signature` agora inclui `slot = 901`, reproduzindo o campo fornecido pela resposta real de `getTransaction`. Nenhuma validação de produção foi afrouxada.
- Commit da correção de fixture: ba3ccd0e8b1292b6b47f1312be5f4d90346a85e7.
- Próxima validação: executar isoladamente apenas `test_backfills_signatures_since_persisted_checkpoint`. Se passar, executar `test_wallet_monitor.py` uma vez com timeout curto; investigar separadamente o teste de sobreposição se não houver resumo final. Não repetir testes já aprovados.
- PR #25 permanece aberto, Draft, sem merge; branch `feat/damm-v2-transaction-pipeline` baseada em `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 172. Runtime aprovado para avanço do checkpoint no backfill — PR #25 (18/11/2026)

- Após sincronizar o commit `c376593e20e87feda74e6b84184a14429218fe65`, o usuário executou isoladamente `tests.test_wallet_monitor.WalletMonitorTests.test_backfills_signatures_since_persisted_checkpoint`.
- Resultado observado no Termux: `Ran 1 test ... OK`. A fixture agora fornece slot 901 tanto na página de assinaturas quanto na transação, e o checkpoint avançou para `new-signature`, conforme a asserção.
- Isso valida em runtime o caminho específico de backfill/CAS anteriormente bloqueado. Ainda não valida a classe completa `WalletMonitor`.
- Próxima ação: executar isoladamente `test_websocket_notification_overlapping_backfill_is_deduplicated`, pois foi o teste que impediu a bateria anterior de apresentar resumo final. Não repetir o teste de checkpoint já aprovado.
- PR #25 permanece aberto, Draft, sem merge; branch `feat/damm-v2-transaction-pipeline` baseada em `feat/damm-v2-swap-domain-adapter`; `main` preservada.


## 173. Correção do fixture de sobreposição WebSocket/backfill — 18/11/2026

- O teste isolado `test_websocket_notification_overlapping_backfill_is_deduplicated` foi executado no Termux com limite de 20 segundos, mas não apresentou resultado final; a execução entrou em reconexões progressivas (1, 2, 4, 8 e 16 segundos). Portanto, o teste não foi considerado aprovado.
- A inspeção do teste identificou a causa: o fixture de `get_signatures_for_address_async` não informava os slots das assinaturas e a transação simulada também não continha `slot`. O backfill exige slot inteiro válido para executar `advance_checkpoint_in_order`; sem esse dado, a recuperação falhava antes de consumir a notificação WebSocket, provocando reconexões sucessivas.
- Correção aplicada somente ao fixture em `tests/test_wallet_monitor.py`: assinatura nova com slot 901, checkpoint anterior com slot 900 e transação simulada com `slot = 901`. Nenhuma regra de produção foi alterada.
- Commit: `13b0c64b5ec03350f04dc2147fc9b91ecb398996` — `Fix overlap backfill test slot fixture`.
- Estado: correção registrada no branch `feat/damm-v2-transaction-pipeline`; aguarda execução isolada no Termux. Não declarar o teste aprovado até receber saída final `OK`.


## 174. Validação do teste de sobreposição WebSocket/backfill — 18/11/2026

- Após o commit `13b0c64b5ec03350f04dc2147fc9b91ecb398996`, o usuário atualizou o Termux com fast-forward até o commit de registro anterior e executou:
  `PYTHONPATH=src timeout 20s python -m unittest tests.test_wallet_monitor.WalletMonitorTests.test_websocket_notification_overlapping_backfill_is_deduplicated -v`
- Resultado observado: `Ran 1 test in 0.102s` e `OK`.
- Evidência: o cenário de notificação WebSocket concorrente com backfill concluiu sem reconexões; a correção do fixture com slots 901/900 e slot 901 na transação simulada removeu a falha que interrompia o teste.
- O teste isolado `test_backfills_signatures_since_persisted_checkpoint` também havia passado anteriormente (seção 172).
- Próxima validação: executar uma única vez a suíte completa `test_wallet_monitor.py`, agora que os dois casos isolados relevantes passaram. Não repetir os testes isolados já aprovados.


## 175. Estado da execução remota de CI — 18/11/2026

- Após o registro da seção 174, foi consultada a execução GitHub Actions associada ao commit `cdfbdee5baabc069bf5cfc07469b801011e49cf7`.
- Execução `SMR tests`, run `44350299820`, run number `992`: conclusão `failure`.
- O job `test` (ID `134963775404`) terminou como `failure`, mas a API retornou `logs_url: null` e `steps: null`; portanto, não há evidência de que os testes tenham iniciado. Isso é consistente com a falha de provisionamento de runner observada anteriormente, mas a causa raiz ainda não está confirmada.
- O teste isolado de sobreposição WebSocket/backfill está aprovado localmente no Termux conforme seção 174. A suíte completa continua sem validação.
- Não repetir disparos de CI sem corrigir ou esclarecer a indisponibilidade do runner. Não pedir ao usuário nova execução isolada. Próxima ação deve consolidar uma validação local única, ou resolver primeiro o provisionamento do CI; não alterar `main` nem mesclar PR #25.


## 176. Validação consolidada em uma única execução — 18/11/2026

- Para eliminar a sequência de comandos isolados no Termux, foi criado `tools/validate_pr25.sh` no branch `feat/damm-v2-transaction-pipeline`.
- Commit: `54caae0dc6ff07f510f6fdce9361051e6bb30b00`.
- O script verifica que o clone está no branch correto, sincroniza por `git pull --ff-only`, executa uma única vez a suíte completa `python -m unittest discover -s tests -v` com `PYTHONPATH=src` e, se a suíte passar, executa `python -m compileall -q src tests`.
- A execução local ainda precisa ocorrer no Termux do usuário; não afirmar validação concluída antes da mensagem final de sucesso do script.
- CI remoto permanece indisponível antes do provisionamento do runner (run 992, seção 175). Não disparar retries em loop.
- Próxima ação operacional: uma única execução de `bash tools/validate_pr25.sh` no diretório local do projeto. O script interrompe no primeiro erro e preserva o resultado real.


## 177. Diagnóstico e correções da validação consolidada PR #25 — 18/11/2026

- O usuário executou `tools/validate_pr25.sh` no Termux. A suíte completa iniciou, mas a saída compartilhada foi truncada; foram identificados um FAIL em `test_signature_mismatch_is_rejected_before_persistence` e um ERROR em `test_adapter_bundle_round_trips_through_existing_sqlite_event_store`. A validação consolidada não passou.
- A revisão direta dos arquivos no HEAD do PR identificou a causa do FAIL: `process_damm_v2_observation()` chamava `normalize_transaction()` e persistia a observação antes de validar que a assinatura solicitada era a assinatura primária única de `transaction.signatures`. O teste exigia rejeição antes de qualquer persistência.
- Correção de produção aplicada: validação fail-closed da lista de assinaturas (lista presente/não vazia, strings não vazias, sem duplicatas e primeira assinatura igual à solicitada) imediatamente após extrair o payload e antes de normalização/persistência. Mensagem de erro explicita a divergência. Commit `31aa18dd98ba60609689eba4563aa8898f071f17`.
- A revisão do ERROR confirmou que o teste de round-trip usava `SQLiteEventStore` sem importá-lo. Correção exclusiva de teste: import explícito do EventStore. Commit `ec86778b13b8fbf3a7dab184a7eddfb836053243`.
- CI associado ao HEAD anterior: run #995 (`44351173108`) terminou failure; job `134966891758` retornou `logs_url=null` e `steps=null`. Não há evidência de execução remota dos testes.
- As duas correções foram gravadas diretamente na branch `feat/damm-v2-transaction-pipeline`; ainda não há validação runtime posterior aos commits. PR #25 permanece aberto, Draft, sem merge; nenhuma alteração em `main`.
- Próxima ação: sincronizar a branch e executar novamente a validação consolidada uma única vez. Não repetir testes isolados já aprovados nem coletar fixture RAW mainnet antes do resultado completo.


## 178. Correções adicionais e CI completo aprovado no PR #25 — 18/11/2026

- CI #998 (44372325999) executou 466 testes e revelou 2 erros nos testes da fixture CPMM real e 1 falha de mensagem no coletor RPC. O log completo foi consultado diretamente no GitHub.
- Causa dos dois erros CPMM: a projeção anonimizada legada preserva meta.loadedAddresses, mas não contém message.addressTableLookups. A validação fail-closed estava correta; não foi afrouxada. O teste agora cria uma cópia em memória da projeção, expande a ordem canônica accountKeys estáticas + loaded writable + loaded readonly e remove meta.loadedAddresses dessa cópia. A fixture original, seu hash e manifesto permanecem intactos. Commit 077e17e4bc10f47581c7a86d6e49dbf316ffc6bc.
- Causa da falha do coletor: a assinatura divergente já era rejeitada, mas a mensagem não continha a expressão esperada pelo teste. Texto ajustado para explicitar “não confere”, sem mudar a regra de validação. Commit 7c002eeec37d73bcce929aa61ca36a585edc9bc6.
- CI #1001 (44372720945), evento pull_request, job 135043570248: checkout, instalação, 466/466 testes e compileall concluídos com sucesso. Esta é a validação integrada do PR e a evidência principal de aprovação do HEAD atual.
- CI #1002 (44372728943), evento push, job 135043598061, reportou uma falha de mensagem no teste do coletor, embora o CI do PR #1001 tenha passado com a branch integrada. Manter a observação para reconciliação; não substituir o resultado verde do evento pull_request por esse evento push divergente.
- Correções de assinatura e import SQLite já registradas na seção 177. Registro Mestre atualizado neste commit documental.
- PR #25 permanece aberto, Draft, sem merge; main preservada. A fixture RAW mainnet DAMM v2 ainda não foi coletada; aprovação da suíte não equivale à validação de fixture DAMM v2 real nem autoriza execução de ordens.


## 179. Confirmação final da CI integrada e continuidade — 18/11/2026

- Após as correções da seção 178, o commit documental HEAD `3950ab575ada8b38b3870b7f9280efa87173e576` disparou CI #1004 (`44372973018`).
- Job `135044474473` concluiu com status SUCCESS. Steps confirmados: checkout, setup Python, instalação do projeto, unittest completo (466 testes) e compileall; todos concluídos com sucesso.
- A divergência anterior entre os eventos push e pull_request foi superada por uma execução verde posterior no HEAD atual. A CI #1004 é a evidência de validação mais recente; não há motivo para novo rerun neste momento.
- PR #25 foi atualizado para remover a afirmação antiga de runtime pendente e registrar 466/466 + compileall aprovados. Continua aberto, Draft, base `feat/damm-v2-swap-domain-adapter`, sem merge; `main` permanece intacta.
- Próxima ação de engenharia: revisar a rotina de coleta e obter a fixture RAW mainnet DAMM v2 localmente no Termux, verificar manifesto/hash e executar auditoria do pipeline contra a transação real. Não coletar fixture CPMM novamente nem repetir a suíte completa sem mudança de código.
- Limite: CI verde valida testes e compilação, não comprova que o coletor já capturou fixture DAMM v2 real, nem valida execução de ordens. Sem BUY/SELL automático.

## 180. Captura e auditoria de fixture real Meteora DAMM v2 — 18/11/2026

- No Termux, o usuário executou `tools/collect_damm_v2_fixture.py` contra o RPC público Solana Mainnet. O coletor retornou `OK` para a assinatura `1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT`, slot `451432630`, SHA-256 `5c053e372d5bb6456e154f2025ab8c51f234941b4e521c64c66f53510c5b948e`.
- Arquivos RAW e manifesto foram gravados localmente em `data/fixtures/raw/damm-v2/`; não foram enviados ao GitHub.
- A primeira chamada do auditor apontou apenas diretório incorreto: o auditor procura manifestos diretamente na pasta indicada e não percorre subpastas. Reexecutado no diretório específico `data/fixtures/raw/damm-v2`, o resultado foi `valid: true`, `errors: []`, com assinatura, slot e SHA-256 correspondentes ao coletor.
- A auditoria confirma integridade do arquivo, manifesto e coerência básica da resposta RPC; não comprova, por si só, a interpretação semântica do swap nem a reconciliação econômica pelo pipeline DAMM v2.
- Próxima etapa: inspecionar localmente a estrutura da transação (programas/instruções, CPI, signatários e proprietários dos token accounts) e então executar o pipeline contra a fixture real com uma carteira monitorada identificada por evidência, sem inventar endereço. Não publicar RAW nem manifesto no repositório público.
- PR #25 continua aberto e Draft, sem merge; `main` permanece preservada. Nenhuma ordem é enviada e a classificação BUY/SELL continua bloqueada até validação e política de ativo-base/quote.

## 181. Validação integrada DAMM v2 real e suporte a funding Wrapped SOL — 18/11/2026

- O usuário pediu que a continuação fosse feita pelo GitHub, sem nova execução manual no Termux. Foi criado `tools/validate_damm_v2_mainnet.py`, que consulta a assinatura pública diretamente no RPC Solana, identifica a única carteira em comum entre signatários e proprietários de token accounts e executa `process_damm_v2_transaction` sem persistir ou publicar o RAW.
- Criado workflow `.github/workflows/damm-v2-mainnet-validation.yml`, com execução automática na branch de trabalho e opção manual `workflow_dispatch`. O runner baixa a transação diretamente do RPC público; nenhum arquivo RAW/manifesto local foi enviado ao GitHub.
- Primeira execução real encontrou `MATCHED` e `ATTRIBUTED`, mas bloqueou a reconciliação: a conta wSOL de entrada tinha delta pre/post zero, enquanto a transferência SPL debitava 20.700 unidades. Diagnóstico confirmou a sequência externa: SystemProgram transfer (índice 5), SPL Token SyncNative (índice 6), DAMM v2 swap (índice 7). O saldo da conta wSOL começa e termina igual porque o funding nativo e o débito wSOL se compensam dentro da mesma transação.
- Implementado `solana_wrapped_sol_funding.py`: reconhece somente funding wSOL demonstrado por SystemProgram::Transfer para a token account, origem igual à carteira monitorada, quantia exatamente igual à transferência de entrada, SyncNative único posterior e anterior ao swap, e delta de lamports da conta igual a zero. Casos ambíguos ou incompletos continuam fail-closed.
- `reconcile_damm_v2_economic_batch` agora recebe o payload e a carteira monitorada do pipeline, incorpora o funding nativo comprovado no delta esperado e registra `WrappedSolFundingEvidence`. Não há bypass do delta: o débito wSOL e o crédito de funding são compensados e comparados com o delta real observado.
- Adicionado teste unitário específico para o decodificador de funding wSOL e teste de reconciliação econômica do funding + SyncNative.
- CI #1031 (run `44375923934`), HEAD `4efdb074ac5959ffb3e293fe1b76c3691376ebc3`: 471/471 testes aprovados e compileall aprovado.
- Workflow de mainnet #6 (run `44375909199`), mesmo HEAD: SUCCESS. Transação assinatura `1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT`, slot `451432630`; 1 associação `MATCHED`, 1 evidência `ATTRIBUTED`, reconciliação `RECONCILED`, 1 bundle produzido. Funding wSOL: conta `FDA2o2DWbFhRHsETEzuty7M87JRLQ9XSfMowByyJr3eX`, origem carteira monitorada, amount_raw `20700`, SystemProgram index 5, SyncNative index 6, lamports delta 0. A classificação permanece `UNKNOWN` (confidence 0); não houve BUY/SELL nem ordem.
- PR #25 continua aberto e Draft, sem merge; base `feat/damm-v2-swap-domain-adapter`; `main` preservada. A fixture RAW original e seu manifesto continuam apenas no Termux do usuário.
- Limite: esta é uma validação real de uma transação DAMM v2, não prova cobertura de todos os modos de fee, swaps múltiplos, CPI aninhado, ALT ou variantes de funding. Próxima etapa é ampliar a cobertura com outras transações reais e testes negativos, sem liberar classificação BUY/SELL nem execução.


## 182. Reforço dos testes de funding Wrapped SOL e CI #1034 — 18/11/2026

- Commit `5384b33dab4840eeb640e2bc2743388020363bcd` adicionou seis testes negativos ao decodificador de funding wSOL: origem diferente da carteira monitorada; SyncNative após o swap; SyncNative duplicado; transferências SystemProgram duplicadas/ambíguas; ausência de snapshots de lamports; ausência de funding nativo.
- CI #1034 (run `44376556474`), associado ao HEAD `5384b33dab4840eeb640e2bc2743388020363bcd`: job `test` concluiu SUCCESS; checkout, setup Python, instalação, testes unitários e compileall aprovados. O resultado confirma os testes no commit, mas o diff desse commit foi somente de testes; nenhuma lógica de produção foi alterada nele.
- Revisão da reconciliação confirmou teste unitário de dois swaps sequenciais compartilhando token accounts, com agregação dos deltas e resultado RECONCILED. Isso valida a função de reconciliação em cenário sintético, mas ainda não comprova uma transação mainnet real com múltiplos swaps nem o fluxo completo pipeline→persistência para esse cenário.
- Limite identificado: o decoder atual de funding wSOL aceita exatamente um SystemProgram::Transfer relacionado e um SyncNative único por conta, antes do swap. Mais de um funding relacionado é rejeitado como ambíguo. Não ampliar essa regra sem desenhar e testar associação inequívoca funding↔swap, especialmente quando uma conta wSOL é reutilizada.
- Estado do PR #25 verificado: aberto, Draft, mergeable, branch `feat/damm-v2-transaction-pipeline`, HEAD `5384b33dab4840eeb640e2bc2743388020363bcd`, base `feat/damm-v2-swap-domain-adapter`; sem merge e sem alteração em `main`.
- Próxima prioridade: testar integração completa com múltiplos swaps e funding wSOL, mantendo rejeição fail-closed para sequências não atribuíveis; em paralelo, revisar exposição de segredos/histórico agora que o repositório está público. Nenhuma credencial pode ser considerada segura apenas por não aparecer no HEAD: verificar histórico e revogar imediatamente qualquer segredo que tenha sido commitado. Não publicar fixtures RAW, manifestos locais, mapas de anonimização ou dados privados.
- Nenhuma ordem, classificação BUY/SELL ou alteração de checkpoint foi habilitada.


## 183. Teste de bloqueio de lote parcialmente associado — 18/11/2026

- Adicionado em `tests/test_damm_v2_transaction_pipeline.py` o teste `test_mixed_matched_and_unresolved_swaps_rejects_entire_batch`.
- O cenário injeta duas associações no pipeline: uma MATCHED e outra EVENT_MISSING. A expectativa é rejeitar o lote inteiro, preservar as duas associações para diagnóstico e não produzir contexts nem bundles. Isso protege contra processamento parcial de uma transação que contém mais de um swap candidato.
- Commit `860a8fdebe415f944c29fbf45a78dc4b8bca5525`. CI ainda não apareceu na consulta imediatamente após o commit; aprovação pendente de confirmação explícita do workflow.
- Busca de código público por padrões comuns encontrou no HEAD pesquisável apenas nomes de variáveis, placeholders documentados e chaves simuladas de teste; nenhum valor de credencial real foi identificado nesses resultados. Isso NÃO equivale a auditoria de todo o histórico Git, nem à confirmação do GitHub Secret Scanning. A conexão disponível não expõe API de alertas de segredo nem administração de segurança. Como o repositório é público, histórico completo e segredos eventualmente commitados ainda exigem auditoria dedicada; qualquer credencial real exposta deve ser revogada/rotacionada.
- PR #25 permanece Draft e aberto; nenhuma alteração em main, nenhum merge e nenhuma execução financeira.
- Próxima ação: confirmar CI do novo teste; depois priorizar integração multi-swap com funding wSOL e cobertura mainnet adicional. Não relaxar fail-closed para acelerar.


## 184. CI dos testes de lote parcial e revisão do limite atual de funding — 18/11/2026

- CI #1037 (run `44377493009`) e CI #1038 (run `44377534348`) concluíram SUCCESS. Ambas executaram checkout, setup Python, instalação, testes unitários e compileall sem falhas. #1038 validou o HEAD documental `7add283db9a0e92e66b9aee77f2987fa4cd3b9ca`, que contém o teste adicionado no commit `860a8fdebe415f944c29fbf45a78dc4b8bca5525`.
- PR #25 segue OPEN/DRAFT, sem merge. HEAD verificado: `7add283db9a0e92e66b9aee77f2987fa4cd3b9ca`.
- Revisão direta de `solana_wrapped_sol_funding.py`: decoder deliberadamente aceita exatamente um SystemProgram::Transfer de source_wallet para token_account, exatamente um SyncNative, ambos antes do swap, funded_amount igual ao amount_raw e delta de lamports da conta wSOL igual a zero. Outros transfers SystemProgram envolvendo a conta, duplicidade ou ambiguidade são rejeitados.
- Decisão de segurança: não generalizar agora para vários funding transfers por conta. A relação entre funding e cada swap precisa ser inequívoca, principalmente se houver múltiplos swaps que reutilizem a mesma conta wSOL. Manter fail-closed até existir modelo de associação e fixture mainnet que demonstre essa sequência.
- O novo teste de lote parcial comprova que uma associação MATCHED misturada com EVENT_MISSING rejeita o lote inteiro e não emite contexts/bundles. Isto é regressão sintética; não equivale a fixture mainnet multi-swap.
- Próxima frente: cobrir a associação funding↔swap para múltiplas operações sem relaxar as condições; depois adicionar fixture mainnet multi-swap obtida localmente e auditada sem enviar RAW/manifesto ao repositório público. Auditoria de histórico Git/segredos permanece pendente; buscas no código atual não substituem secret scanning do histórico completo.
- Nenhuma ordem, BUY/SELL, checkpoint ou merge foi habilitado.


## 185. Correção de rastreamento: integração wSOL já existe; limite é por operação — 18/11/2026

- Correção da observação preliminar feita durante a busca textual: `decode_wrapped_sol_funding` está integrado em `damm_v2_economic_reconciliation.py`, dentro da reconciliação do input quando o mint é NATIVE_MINT e os argumentos `raw_transaction` e `monitored_wallet` estão presentes. A busca anterior limitada aos arquivos do pipeline/adaptador não encontrou a chamada porque ela está na camada de reconciliação.
- Teste existente `test_reconciles_wrapped_sol_input_funded_and_synced_before_swap` cobre o caso wSOL de uma operação. Teste `test_aggregates_sequential_swaps_sharing_the_same_token_accounts` cobre compartilhamento de contas em swaps sequenciais sem demonstrar funding wSOL compartilhado.
- Limitação real: a reconciliação chama o decoder por operação e exige que cada input de wSOL tenha um único funding top-level cujo valor seja exatamente igual ao amount bruto daquele input. Um funding agregado ou uma conta wSOL reutilizada por várias operações não está modelado como relação de lote; o comportamento conservador atual é rejeitar divergências/ambiguidade, não repartir funding.
- Próximo passo correto: criar teste de regressão específico para duas operações DAMM v2 que reutilizam a mesma conta wSOL e provar que nenhum funding é contado duas vezes nem repartido por suposição. Depois desenhar a associação por transação e somente então alterar produção. Não afirmar que a integração está ausente.
- CI #1039 (run `44377757156`) SUCCESS. Commit de registro anterior `9968d3fac01bfcd3499946d02057262859b08c99` foi validado por essa execução.


## 186. Teste de funding wSOL compartilhado entre swaps — 18/11/2026

- Adicionado em `tests/test_damm_v2_economic_reconciliation.py` o teste `test_rejects_shared_wsol_account_with_multiple_funding_transfers_as_ambiguous`.
- Cenário: duas operações DAMM v2 sequenciais usam a mesma conta wSOL; cada uma tem transferência de funding SOL e SyncNative antes dos swaps. A reconciliação deve rejeitar o caso como INCOMPLETE/ambíguo, sem produzir WrappedSolFundingEvidence e sem repartir funding automaticamente.
- Commit do teste: `dd75e64b9bf1092af3f4e2bc76bf9cb80f177cfe`. A validação CI deste commit ainda precisa concluir.
- Interpretação: teste caracteriza o comportamento seguro atual e impede uma falsa reconciliação. Não implementa ainda associação multi-swap; a produção continua fail-closed. Próximo passo após CI: desenhar e implementar resolução em lote que associe funding top-level a cada swap/CPI de forma inequívoca, com testes positivos e negativos.
- Nenhuma ordem, BUY/SELL, checkpoint ou merge habilitado.


## 187. Funding wSOL agregado por conta em lote multi-swap — 18/11/2026

- Implementação em `solana_wrapped_sol_funding.py`: decoder agora aceita uma ou mais transferências top-level SystemProgram da mesma source_wallet para a mesma token_account, soma os valores, exige que todas ocorram antes de um único SyncNative e que esse SyncNative ocorra antes do primeiro swap. Rejeita transferências envolvendo a conta com origem/destino divergente, ausência/duplicidade de SyncNative, divergência de soma e delta de lamports não zero. Evidência preserva `system_transfer_indices` e índice do SyncNative.
- Implementação em `damm_v2_economic_reconciliation.py`: agrupa inputs NATIVE_MINT por token account, soma os valores brutos e chama o decoder uma única vez por conta, antes do primeiro swap que usa essa conta. O crédito de funding agregado é aplicado uma única vez ao delta esperado, evitando duplicação por operação.
- Teste de integração sintético atualizado: duas operações sequenciais usando a mesma conta wSOL, dois SystemProgram transfers de 100, um SyncNative antes dos swaps, total funding 200; espera RECONCILED e uma evidência com índices (0, 1). Teste unitário adicional cobre transferências múltiplas + um SyncNative. Teste de funding duplicado com soma divergente continua rejeitado.
- Commits de produção/testes: `95c16acd2ccf43213c43f6aead192690109c8b09`, `9a555c17d708402adf705da0c7fbece9731f58dd`, `ffc82421dec327dbcec634effc11fbb261bd2f1d`, `6dbb8c51ee95388e4ac2b82efe12d51870f05d25`.
- Estado: CI para os novos commits ainda não foi confirmada. A cobertura é sintética; não substitui fixture mainnet real de transação multi-swap wSOL. A regra deliberadamente suporta apenas um SyncNative único após todos os funding transfers e antes do primeiro swap; padrões diferentes permanecem rejeitados.
- Nenhuma ordem, BUY/SELL, checkpoint ou merge habilitado.

- Validação final da implementação: CI #1051 (run `44378721507`) SUCCESS no commit de código `6dbb8c51ee95388e4ac2b82efe12d51870f05d25`: 480 testes passaram e compileall passou. Os runs intermediários #1045/#1047/#1049 falharam enquanto a alteração estava incompleta (teste antigo ainda esperava rejeição de transferências duplicadas); o commit de teste #1051 atualizou a expectativa e confirmou a implementação integrada.
- HEAD atual do PR após atualização documental: `83f2db22e17df2aedb39ace867957c495d3cfc47`; o commit adicional é apenas registro. PR #25 permanece OPEN/DRAFT, sem merge.


## 188. Relatório da validação Mainnet expõe todos os funding transfers — 18/11/2026

- Atualizado `tools/validate_damm_v2_mainnet.py` para emitir `system_transfer_indices` como lista completa, além do campo legado `system_transfer_index`, permitindo auditar no relatório a evidência agregada sem guardar payload RAW.
- Commit: `848d35e123630417c8d79b5e52bb219f4495b199`. CI específico desse commit ainda não foi consultada; o núcleo de reconciliação foi validado em #1051 (480 testes + compileall) no commit `6dbb8c51ee95388e4ac2b82efe12d51870f05d25`.
- Próxima validação de maior valor: obter fixture mainnet DAMM v2 com dois swaps e wSOL compartilhado; rodar `tools/validate_damm_v2_mainnet.py` e conferir RECONCILED, dois bundles e evidência de funding agregada. Até lá, suporte validado apenas por teste sintético.

- CI #1054 (run `44378925314`) SUCCESS no commit `848d35e123630417c8d79b5e52bb219f4495b199`: 480 testes passaram e compileall passou, incluindo o relatório com a lista completa de índices de funding.


## 189. Mainnet DAMM v2 reconciliado e endurecimento de entradas do decoder — 18/11/2026

- Evidência real de Mainnet confirmada nos logs do workflow #8 (run `44378911504`, job `135065453319`) para assinatura `1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT`, slot 451432630: status `RECONCILED`, reconciliation `RECONCILED`, um bundle emitido, funding wSOL de 20.700 lamports, SystemProgram transfer no índice 5 e SyncNative no índice 6. Classificação permanece UNKNOWN. A transação tem um swap DAMM v2; isto valida o caminho Mainnet de uma operação, não o cenário multi-swap compartilhado.
- Decoder `solana_wrapped_sol_funding.py` endurecido para validar tipo/identidade de token account e source wallet, amount como unsigned 64-bit (bool, negativo e overflow rejeitados) e limite de instrução como inteiro não negativo (bool rejeitado).
- Testes adicionais cobrem amount inválido/overflow e boundary booleano.
- CI #1059 (run `44379283925`) e #1060 (run `44379296088`) SUCCESS; última execução #1060 no HEAD `226909d5213a7b355d0c185207bf23d3b7def084`: 482 testes passaram e compileall passou.
- Próximo passo: obter fixture real Mainnet com múltiplos swaps DAMM v2 que compartilhem a mesma conta wSOL. Até essa evidência existir, suporte multi-swap está comprovado apenas sinteticamente. Nenhuma ordem, BUY/SELL ou merge foi habilitado.


## 190. CI Mainnet passa a reagir ao decoder wSOL — 18/11/2026

- Identificada lacuna de automação: workflow `.github/workflows/damm-v2-mainnet-validation.yml` não era acionado quando apenas `solana_wrapped_sol_funding.py` mudava, pois o glob anterior cobria `solana_token_*.py`, mas não o decoder wSOL.
- Corrigido o gatilho adicionando o caminho explícito `src/smart_money_radar/data_sources/solana_wrapped_sol_funding.py`. Commit `b46010b3290239b757abbb898206f632529173fd`.
- A mudança disparou workflow de validação Mainnet #9 (run `44379455602`), inicialmente QUEUED. CI de testes #1061 (run `44379424567`) SUCCESS, com 482 testes e compileall aprovados (HEAD anterior documental `587bea2fb7857d94406837a6c71f38c29289475b`).
- Próxima verificação imediata: aguardar workflow #9 e confirmar novamente a transação real DAMM v2 com status RECONCILED, funding 20.700 lamports e um bundle.

- Workflow Mainnet #9 (run `44379455602`) SUCCESS após incluir o decoder wSOL nos gatilhos. Reexecutou a consulta RPC da transação real e confirmou novamente `status=RECONCILED`, `reconciliation_status=RECONCILED`, funding 20.700 lamports, índices de funding reportados e 1 bundle. Isso comprova que o workflow é disparado por mudanças no decoder e que a alteração de validação não quebrou o caminho Mainnet single-swap.


## 191. Cobertura explícita para múltiplos calls DAMM v2 `swap2` — 18/11/2026

- Revisada a cobertura do analyzer após consulta ao relatório de auditoria OtterSec para Meteora DAMM v2 (versão auditada 0.1.5; relatório publicado em 2025): o sumário registra que uma verificação de swap único podia ser contornada por chamadas `swap2`, permitindo múltiplos swaps na mesma transação. Referência pública: https://resources.cryptocompare.com/asset-management/21061/1762508237558.pdf
- O decoder já reconhecia o discriminador `SWAP2_DISCRIMINATOR`, e o analyzer trata swaps por instrução. A lacuna encontrada era de teste explícito: a cobertura sequencial existente usava apenas o discriminador legado `swap`.
- Adicionado teste `test_keeps_two_sequential_swap2_calls_as_two_matched_operations`: duas chamadas `swap2` dentro do mesmo grupo inner, cada uma seguida do seu próprio `EvtSwap2`, devem produzir duas associações MATCHED, preservando índices, nomes e amounts.
- CI #1065 (run `44379857442`) SUCCESS no commit `49395fef9adb181b16c024837e04615b7efd93e8`: 483 testes passaram e compileall passou.
- Esta evidência é sintética e cobre associação estrutural de duas instruções `swap2`; não é fixture Mainnet de dois swaps, nem valida por si só funding wSOL compartilhado em Mainnet. PR #25 permanece aberto/Draft; sem merge, BUY/SELL ou execução financeira.
- Próximo passo: localizar e validar uma transação Mainnet que contenha pelo menos duas instruções DAMM v2 `swap2` e compartilhe a conta wSOL monitorada, caso exista dentro do conjunto de transações disponíveis.


## 192. Scanner automatizado de Mainnet para múltiplos `swap2` com wSOL compartilhado — 18/11/2026

- Criado `tools/scan_damm_v2_multi_swap_mainnet.py`: consulta até 30 assinaturas finalizadas recentes do programa DAMM v2 via RPC público, busca transações com pelo menos dois `swap2` associados a eventos e executa o pipeline completo nos candidatos. Só reporta `FOUND_SHARED_WSOL_MULTI_SWAP` quando o lote está RECONCILED e uma conta wSOL de entrada é compartilhada por pelo menos duas operações com funding identificado.
- O scanner não persiste payload RAW, não envia ordens e não altera estado financeiro. Limite configurável de 1 a 100 transações; padrão 30.
- Workflow `.github/workflows/damm-v2-mainnet-validation.yml` atualizado para executar a validação single-swap conhecida e, em seguida, a busca limitada; timeout aumentado para 10 minutos. Gatilho de push inclui o scanner.
- Commits: scanner `9af21dad9644f4fd2138f9d3363737602ccbf5a7`; workflow `22dd1fb7971c6aaff378d721b6c817726163c50e`.
- CI #1068 (run `44380902804`) e workflow Mainnet #10 (run `44380915218`) iniciados no momento do registro; resultados ainda não confirmados.
- Critério de sucesso não é apenas encontrar múltiplos swaps: é necessário obter pipeline `RECONCILED` e evidência de funding wSOL compartilhado. Ausência de candidato no lote de 30 significa apenas que a busca limitada não encontrou exemplo, não que o padrão não exista.
- PR #25 permanece OPEN/DRAFT, sem merge. Nenhuma classificação BUY/SELL ou execução financeira habilitada.


## 193. Primeiras transações Mainnet com dois `swap2` identificadas — 18/11/2026

- Scanner Mainnet #18 (run `44381409652`) SUCCESS: 100 assinaturas finalizadas do programa DAMM v2 consultadas, sem falhas de RPC. Foram identificadas quatro transações com duas associações `swap2` MATCHED:
  - `3TzUJxV7tGnFHgNwRmDiSpw6jUcjZ52kA7NxH7FWezVMm3MC632tKnRPZ86jPd2oNhtPtj4vbPf4gkqQBxRGHXRx` — slot 471052307.
  - `3jYsMveuktP9k5UZ1NkyiVmQqtKs4Yfo6rGRPSc4PybzsnMdvPSZDxjwvdgjHPmbm41WDZnuqMzuXXzED99f6tyB` — slot 471052306.
  - `2yw6Lmw6V6DFDw9vvdb9vo3WhY7jyHRK5nTsitJpt6QuDx9styWVZzX7BNfabCZbHrFuwqukTVe2TFAKyQkmWuSa` — slot 471052305.
  - `4e2PXZqk2eHSdqRyYvy8472e7n12KC9of7M36tu1UcRULFZYB48xAUvhQBFqMzivWfShPLsx7fcU5vrFRRQrNqW3` — slot 471052305.
- A varredura posterior #21 (run `44381547015`) também consultou 100 assinaturas sem falhas e encontrou quatro transações multi-swap recentes, slots 471052584–471052586. Todas foram rejeitadas pelo pipeline com o mesmo motivo: `reconciliação econômica INCOMPLETE: funding SOL agregado diverge do valor bruto total das transferências wSOL`.
- A evidência comprova que transações Mainnet com múltiplos `swap2` existem, mas ainda não comprova que o padrão específico de funding compartilhado seja compatível com o decoder atual. Não relaxar validação econômica. Próximo passo: inspecionar detalhadamente uma transação candidata, incluindo instruções SystemProgram, SyncNative, transferências wSOL e deltas de saldo.
- Foi incluído diagnóstico `pipeline_reason` no scanner e uma etapa de inspeção dedicada para a primeira candidata `78AuFWUBHsF6P8XgdzFsrz7XRuErsdcMzysRxq845zjTqQ9b7jeVcLd9obwJyL8MSJMTkV9WcRrnTPfPtgTq5UK` (slot 471052586); workflow #22 (run `44381696357`) ainda em execução no momento deste registro.
- Scanner aceita transaction version 1, usa RPC PublicNode como endpoint primário configurado e Solana Labs como fallback; limite atual 100 assinaturas. O fluxo de validação conhecida single-swap segue aprovado.
- CI #1068 (run `44380902804`) SUCCESS: 483 testes e compileall aprovados. PR #25 continua OPEN/DRAFT, sem merge; BUY/SELL e execução financeira permanecem desabilitados.


## 194. Inspeção da candidata Mainnet e filtro de reutilização wSOL — 18/11/2026

- Workflow Mainnet #22 (run `44381696357`) executou a inspeção detalhada da assinatura `78AuFWUBHsF6P8XgdzFsrz7XRuErsdcMzysRxq845zjTqQ9b7jeVcLd9obwJyL8MSJMTkV9WcRrnTPfPtgTq5UK`, slot 471052586. O pipeline encontrou 2 associações MATCHED e 2 transfer evidences ATTRIBUTED, mas a reconciliação permaneceu INCOMPLETE.
- Causa observada: o primeiro swap usa a conta wSOL `GBiDcPGFHF461LfDVEDn2yX5yPVEFCi59mXdppBSME7z` como input; o segundo swap usa a conta do outro token como input e devolve wSOL à conta `GBiDc...`. Portanto, é um round-trip em sentidos opostos, não duas operações com a mesma conta wSOL como input.
- A instrução SystemProgram observada no índice 5 transfere SOL de `GEUDKx63wXKrn7ognB2gkmy8YRNkVF1hgS4sBEg9nZVm` para `FDA2o2DWbFhRHsETEzuty7M87JRLQ9XSfMowByyJr3eX`, seguida de SyncNative no índice 6. Isso não demonstra funding da conta wSOL input `GBiDc...` pela carteira monitorada `HFvU7JH5GbWSASkdjrjhtbKKyG2bpx9Rh8ZfNH8PiciX`. A divergência de funding é corretamente rejeitada; não alterar a regra econômica para aceitar esse padrão.
- Scanner atualizado no commit `56ef7d4a827c11b843a36bd633994deb01026283` para distinguir: (a) mesma conta wSOL reutilizada como input em duas ou mais operações; (b) conta wSOL com funding identificado. Só reportará FOUND quando ambas as condições estiverem comprovadas e o pipeline estiver RECONCILED.
- Workflow #22 manteve a validação conhecida single-swap e o scanner de 100 assinaturas com sucesso; a etapa dedicada de inspeção da candidata retornou REJECTED como esperado (continue-on-error).
- Próximo passo: executar a nova varredura e identificar se alguma transação Mainnet recente realmente reutiliza a mesma conta wSOL como input em múltiplos `swap2`. Não há ainda validação Mainnet desse padrão específico.


## 195. Varredura paginada Mainnet e padrão round-trip compartilhado — 18/11/2026

- Scanner Mainnet #28 (run `44382687365`, commit scanner `0c2fbfd93a50b839cdbb6cbb376e695abc1e1c69`) concluiu SUCCESS após consultar 3 páginas de 100 assinaturas: 300 transações inspecionadas, sem falhas de RPC; uma transação foi ignorada pela análise por erro de comprimento de instrução não compatível (`swap exige 24 bytes`).
- Foram encontradas 16 transações com duas chamadas `swap2` MATCHED. As 16 mostram o mesmo padrão estrutural: o swap 1 usa uma conta wSOL como input e o swap 2 usa uma conta do token adquirido como input, devolvendo wSOL à conta original. Portanto, há reutilização da conta wSOL entre operações em sentidos opostos (round-trip), mas não duas entradas wSOL pela mesma conta.
- Primeira candidata para inspeção detalhada: `4cm2yJUSTzevqYAh5N9vknk2jCmocwgbrJR2s7CiPp8DPCuBBgyMqxKU6qk7F5YSdtLDTJpneRrz4TTn7odqDy6k`, slot 471054827. O pipeline marcou REJECTED por divergência entre funding SOL agregado e valor bruto das transferências wSOL; ainda não é caso reconciliado e não autoriza alterar regras.
- Scanner passou a paginar por cursor `before`, 3 páginas × 100 (limite 1–10 páginas; 1–100 por página), aceita transaction version 1, e inclui direção de input/output por swap no relatório. As falhas dos runs #25–#27 foram erros de sintaxe/encaminhamento dos argumentos de paginação, corrigidos e verificados pelo sucesso do run #28.
- CI #1084 (run `44382709318`) SUCCESS: 483 testes e compileall aprovados.
- Workflow Mainnet #29 (run `44382931922`) está inspecionando a candidata acima com a etapa detalhada; scanner paginado também executa. O workflow foi atualizado para apontar a assinatura `4cm2y...`.
- Conclusão provisória: o padrão real observado em 16/16 candidatas é round-trip de wSOL, não funding múltiplo para mesma conta. Próximo passo é examinar instruções de funding, SyncNative, transferências SPL e deltas da candidata #29 para explicar a divergência econômica. Manter fail-closed; não ativar BUY/SELL ou execução financeira.


## 196. Candidata Mainnet revela ciclo wSOL create/fund/swap/close/recreate/swap/close — 18/11/2026

- Workflow Mainnet #29 (run `44382931922`) SUCCESS: validação conhecida single-swap, inspeção detalhada da candidata e scanner paginado concluíram. Candidata inspecionada: `4cm2yJUSTzevqYAh5N9vknk2jCmocwgbrJR2s7CiPp8DPCuBBgyMqxKU6qk7F5YSdtLDTJpneRrz4TTn7odqDy6k`, slot 471054827.
- Pipeline: 2 associações swap/`EvtSwap2` MATCHED e 2 transfer evidences ATTRIBUTED. Reconciliação permanece INCOMPLETE; bundles = 0; nenhuma classificação/execução.
- Evidência estrutural observada para a mesma ATA wSOL `6gWbcXGP9SDcFxK14T8SeCcitSqoLTir3GxoHVfqLwrs` e carteira monitorada `8mgqGQqRr75muaiSkimDAL91QcGv4dQujFfNXc3pRXdY`:
  1. ATA wSOL criada no índice externo 1.
  2. SystemProgram transfer no índice 3 da carteira monitorada para a ATA wSOL: `5,253,182,520` lamports.
  3. SyncNative no índice 4.
  4. Primeiro swap no índice 5 consome `5,092,426,526` lamports-equivalentes de wSOL da ATA.
  5. Token Program CloseAccount no índice 6 fecha a ATA e devolve o saldo restante à carteira.
  6. ATA wSOL criada novamente no índice 8.
  7. Segundo swap no índice 9 envia `5,091,426,733` wSOL para a mesma ATA.
  8. Token Program CloseAccount no índice 10 fecha novamente a ATA e devolve o saldo à carteira.
- Diferença funding menos input do primeiro swap: `160,755,994` lamports, que permanece na ATA antes do primeiro fechamento. O segundo swap devolve `5,091,426,733` wSOL antes do segundo fechamento. A conta tem pre/post lamports agregados iguais a zero porque é criada e fechada dentro da mesma transação; snapshots simples pre/post não capturam os saldos intermediários.
- Causa da rejeição atual: o decoder wSOL exige que o total de SystemProgram funding seja exatamente igual ao gross input wSOL e não modela saldos residuais devolvidos por CloseAccount nem ciclos repetidos de criação/fechamento da mesma ATA. O fail-closed atual é correto; não relaxar igualdade nem aceitar apenas pela presença de CloseAccount.
- Próximo trabalho técnico: projetar evidência de lifecycle wSOL por ciclo, reconstruindo funding, SyncNative, transferências SPL atribuídas e CloseAccount (conta, autoridade e destino), incluindo ATA recriada na mesma transação. Exigir fechamento para a carteira monitorada e balanço completo de cada ciclo; criar fixtures sintéticas antes de validar qualquer novo padrão Mainnet.
- Scanner paginado #28 confirmou 16 transações multi-swap entre 300 inspecionadas; as 16 candidatas exibem round-trip da mesma conta wSOL (input no primeiro swap, output no segundo), não duas entradas wSOL independentes. CI #1084 SUCCESS: 483 testes e compileall.
- PR #25 continua OPEN/DRAFT e sem merge. Não habilitar BUY/SELL, ordens ou execução financeira.


## 197. Primeiro round-trip wSOL multi-swap real totalmente reconciliado — 18/11/2026

- Mainnet workflow #40 (run `44386175898`, commit `eb1d7562ebab4a70a064f776464f8ae6fbc12925`) SUCCESS em todas as etapas: validação conhecida, inspeção dedicada da candidata real e scanner paginado.
- Transação real `4cm2yJUSTzevqYAh5N9vknk2jCmocwgbrJR2s7CiPp8DPCuBBgyMqxKU6qk7F5YSdtLDTJpneRrz4TTn7odqDy6k`, slot 471054827: pipeline `RECONCILED`, 2 associações MATCHED, 2 transferências ATTRIBUTED, 1 evidência lifecycle wSOL e 2 bundles de domínio gerados. Classificações permanecem `UNKNOWN` nas duas operações.
- Lifecycle Mainnet comprovado para ATA `6gWbcXGP9SDcFxK14T8SeCcitSqoLTir3GxoHVfqLwrs`, carteira `8mgqGQqRr75muaiSkimDAL91QcGv4dQujFfNXc3pRXdY`: create [1,8], SystemProgram funding [3], SyncNative [4], transferências SPL [(5,0),(9,1)], CloseAccount [6,10], funding total 5,253,182,520 lamports, saldos reconstruídos antes dos closes [160,755,994; 5,091,426,733], delta agregado de lamports 0.
- O adaptador de domínio foi ajustado para aceitar a propriedade da token account wSOL comprovada por ATA create + CloseAccount (destino e autoridade = carteira monitorada), quando a conta efêmera não possui delta pre/post. Contas não-wSOL continuam exigindo snapshots/owner; sem lifecycle comprovado, a ausência de delta continua bloqueando.
- O scanner passou a reconhecer compartilhamento wSOL entre operações por qualquer papel input/output e só reporta sucesso quando o pipeline está RECONCILED e a conta tem funding/lifecycle comprovado.
- Na mesma execução #40, o scanner encontrou outra transação real: `634xz2RekctQ8hSoe7h3YF5jugtNy9ADeR7c5xJCZjKNvkwoBcBKX2euswtzVLo2hzpcmPEFsRyD5NQuKw1huiPk`, slot 471060124. Após 23 transações inspecionadas, sem falhas de RPC, encontrou 2 swaps MATCHED, pipeline RECONCILED, e a mesma conta wSOL `GqKhpve2sYDBjEhZQGttGUGrYf621gNrXmGv4oEZ9Cf6` usada como input na operação 0 e output na operação 1; lifecycle reconhecido e funding reconciliado.
- Teste end-to-end sintético novo confirma que duas operações round-trip com a ATA wSOL fechada/recriada reconciliam, excluindo apenas a conta efêmera do delta pre/post depois de reconstruir ambos os ciclos. Testes diretos também rejeitam saldo negativo, CloseAccount para outra carteira e transferências não atribuídas.
- CI #1113 (run `44386188482`) SUCCESS: 488 testes e compileall. CI #1116 (commit `5fadcd54807699f798f0ef930b8069eb0e7a7cc9`) está validando o teste adicional de ownership lifecycle; o run #1115 teve apenas uma falha de texto na asserção do teste, corrigida no commit #1116.
- PR #25 permanece OPEN/DRAFT e sem merge. Nenhuma ordem financeira é executada; BUY/SELL continua `UNKNOWN`.


## 198. Duas validações Mainnet dedicadas + terceira candidata reconciliada — 18/11/2026

- CI #1116 (run `44386374012`) SUCCESS: 489 testes aprovados em 4,181s e compileall aprovado. CI #1118 (run `44386493363`) SUCCESS: 489 testes e compileall novamente aprovados.
- Mainnet workflow #41 (run `44386586818`, commit workflow `5076bf42f52d6d8ce6dc126945ff88674b46a5f0`) SUCCESS em todas as quatro etapas: transação conhecida single-swap, primeira candidata multi-swap, segunda candidata multi-swap e scanner paginado.
- A etapa dedicada para a primeira candidata `4cm2yJUSTzevqYAh5N9vknk2jCmocwgbrJR2s7CiPp8DPCuBBgyMqxKU6qk7F5YSdtLDTJpneRrz4TTn7odqDy6k` (slot 471054827) retornou `RECONCILED`, 2 bundles, classificação `UNKNOWN` para ambas.
- A etapa dedicada para a segunda candidata `634xz2RekctQ8hSoe7h3YF5jugtNy9ADeR7c5xJCZjKNvkwoBcBKX2euswtzVLo2hzpcmPEFsRyD5NQuKw1huiPk` (slot 471060124) também retornou `RECONCILED`, 2 swaps e 2 bundles; carteira monitorada `EpKbgf77ZKP44uxhFe8t3PiMDAmY1ap7qSaigRjWyW8k`.
- O scanner da mesma execução encontrou terceira transação `4WpBm6HHVpUv6hXGZgf4meZ2HrAu4pUBC9ufREVvqf2y4X6eiGGdKT9gu8uZaNUPwVdVPX3AHBxaeJ23bftpGMGq`, slot 471060788, após 6 transações inspecionadas e zero falhas RPC. Resultado: 2 `swap2` MATCHED, pipeline `RECONCILED`, mesma ATA wSOL `9v94Hevy89f57EY4LEPWVE843mvgkMbRTgZxhhJ5SFqo` usada como input na operação 0 e output na operação 1, lifecycle reconhecido.
- O scanner interrompe a busca após encontrar uma candidata totalmente reconciliada; por isso `inspected=6` não representa varredura integral de 300 nesse run.
- Conclusão técnica: lifecycle wSOL create/fund/SyncNative/swap/CloseAccount/recreate/swap/CloseAccount agora tem (a) teste unitário direto, (b) teste de reconciliação econômica em lote, (c) teste do adaptador de domínio com prova de propriedade lifecycle e (d) validação real Mainnet em duas transações dedicadas, além de terceira candidata confirmada pelo scanner.
- PR #25 continua OPEN/DRAFT, sem merge. Classificação BUY/SELL segue `UNKNOWN`; nenhum sinal, ordem ou execução financeira foi habilitado.


## 199. Confirmação final após ajuste de evidência e reconciliação — 18/11/2026

- Mainnet workflow #42 (run `44386963957`, commit de workflow `63f3b66bc8c1715fb110bb58cf8f4d5441683d34`) SUCCESS em todas as etapas: transação single-swap conhecida, duas transações multi-swap dedicadas e scanner paginado.
- CI #1121 (run `44386963977`) SUCCESS: 489 testes aprovados em 3,900s e compileall aprovado.
- Texto de evidência do domínio e motivo de reconciliação agora descrevem corretamente snapshots pre/post **e** lifecycle wSOL quando aplicável, sem sugerir que toda conta efêmera tem delta observável.
- PR #25 permanece OPEN/DRAFT, sem merge; head atualizado pelos commits desta etapa. BUY/SELL permanece UNKNOWN e execução financeira desabilitada.


## 200. Retry idempotente após falha parcial de múltiplos bundles — 18/11/2026

- Na branch da PR #25 foi adicionado o teste `test_partial_multi_bundle_write_retries_idempotently_after_second_bundle_failure` em `tests/test_damm_v2_persistence_pipeline.py`.
- O teste usa `SQLiteEventStore` real e injeta uma falha única na segunda chamada de `save_swap_bundle`: comprova que o primeiro bundle permanece persistido, o segundo não é gravado, a assinatura continua pendente e o checkpoint não avança.
- No replay, a reconciliação retorna os mesmos dois bundles; o primeiro é tratado idempotentemente (sem duplicação) e o segundo é persistido. O resultado final fica `reconciled`, com dois bundles disponíveis e sem avanço indevido de checkpoint.
- A primeira execução do teste falhou porque o replay de fixture vazia retornou `no_damm_v2_swaps`; a simulação foi corrigida para devolver novamente o resultado reconciliado, mantendo a falha de persistência real na primeira tentativa.
- Commit final: `45ab617686d663bbd653b99f697cec21d3811b34`.
- CI #44410732347 SUCCESS no commit final: 490 testes aprovados em 3,901s; `compileall -q src tests` aprovado. O log identifica explicitamente o novo teste como `ok`.
- Limite da evidência: esta cobertura exercita a orquestração de persistência/retry com contratos de bundle sintéticos e SQLite real; não substitui teste Mainnet nem fixture de dois swaps decodificados/reconciliados ponta a ponta.
- PR #25 permanece OPEN/DRAFT, sem merge. A `main` não foi alterada. BUY/SELL continua `UNKNOWN`; execução financeira permanece desabilitada.
- Próxima ação: ampliar a integração DAMM v2 multi-swap entre analyzer, reconciliação econômica, adapter de domínio e persistência, mantendo identidade individual por instrução/CPI e fail-closed.


## 201. Persistência independente de dois bundles DAMM v2 no mesmo lote — 18/11/2026

- Adicionado em `tests/test_damm_v2_swap_domain_adapter.py` o teste `test_builds_and_persists_two_distinct_swap2_bundles_from_one_reconciled_batch`.
- O teste entrega ao adapter dois contextos de swap distintos (instruções 2 e 3, caminhos CPI independentes), evidências de transferências atribuídas, deltas agregados completos e lote econômico `RECONCILED` com duas operações.
- O adapter deve gerar dois operation IDs distintos, preservar a identidade de cada instrução e manter classificação `UNKNOWN`; ambos os bundles são persistidos e lidos de volta pelo SQLiteEventStore real. Regravar cada bundle idêntico deve retornar idempotentemente `False`, sem duplicação.
- CI #44411090198 SUCCESS no commit `d5f8df8a8f3bc9061aba3cab72c07e1e8efe35d9`: 491 testes aprovados em 4,213s; compileall aprovado. O log identifica o novo teste como `ok`.
- Limite da evidência: contextos/evidências/deltas do teste são construídos em fixture sintética. A associação real de duas chamadas `swap2` já possui teste separado no analyzer, e Mainnet já validou transações multi-swap; ainda falta um teste único de integração que atravesse analyzer, decodificação de contas/transferências, reconciliação, adapter e persistência usando o mesmo payload.
- PR #25 permanece OPEN/DRAFT, sem merge; `main` não foi alterada. BUY/SELL continua `UNKNOWN`; execução financeira permanece desabilitada.
- Próxima ação: fechar a lacuna com integração de ponta a ponta DAMM v2 multi-swap em fixture RPC determinística, mantendo bloqueio integral quando qualquer swap do lote não reconciliar.


## 202. Integração fail-closed de duas chamadas swap2 até a persistência — 18/11/2026

- Adicionado em `tests/test_damm_v2_persistence_pipeline.py` o teste `test_two_real_swap2_associations_block_entire_batch_when_second_account_decode_fails`.
- O teste constrói um payload RPC sintético realista com duas chamadas DAMM v2 `swap2` sequenciais e dois eventos `EvtSwap2`; o analyzer associa ambas como operações distintas.
- A primeira instrução possui inventário de contas válido e a segunda é deliberadamente incompleta. O pipeline real percorre associação e início da resolução de contas, rejeita o lote inteiro e não produz bundle parcial.
- A camada de persistência registra as duas operações como `INCOMPLETE`, mantém a assinatura pendente, não avança checkpoint e não persiste bundles.
- A primeira execução PR no commit intermediário `2ac0d546986ffe19b69efa4329433a4665d28c3d` falhou somente porque o teste chamou um método inexistente `list_swap_bundles`. A asserção foi corrigida para consultar `get_swap_bundle` por operation ID; a execução push no commit `edd74ca385c7e294635351ec0a79249205fbd49a` passou.
- CI push #44411418961 SUCCESS: 492 testes aprovados em 3,899s e compileall concluído. O log identifica o novo teste como `ok`.
- Limite da evidência: o cenário de duas operações usa payload sintético e interrompe deliberadamente na resolução de contas da segunda operação. Não demonstra ainda o caminho de sucesso completo com duas operações passando por transferências, reconciliação econômica, adapter e SQLite no mesmo payload.
- PR #25 permanece OPEN/DRAFT e sem merge; `main` não foi alterada. BUY/SELL continua `UNKNOWN`; execução financeira permanece desabilitada.
- Próxima ação: completar o fixture sintético de sucesso multi-swap com contas, transferências, snapshots/deltas e lifecycle quando aplicável, e passar o payload completo pelo pipeline de ponta a ponta.


## 203. Integração ponta a ponta de duas operações DAMM v2 — 18/11/2026

- Adicionada a fixture RPC sintética `_damm_two_swap2_reconciled_raw` em `tests/test_damm_v2_persistence_pipeline.py`, contendo duas chamadas `swap2` sequenciais, dois eventos `EvtSwap2`, listas de contas completas e independentes, quatro transferências `TransferChecked` (input/output por operação) e snapshots pre/post completos para as oito token accounts.
- O teste `test_two_swap2_payload_runs_full_pipeline_and_persists_both_bundles` chama diretamente `process_damm_v2_observation`, sem mocks nas etapas internas. Portanto percorre o analyzer, associação evento/instrução, decoder de contas, decoder de transferências, atribuição CPI, decoder de deltas, reconciliação econômica do lote, adapter de domínio e persistência SQLite.
- Resultado comprovado: `reconciled`; 2 swaps decodificados; 2 reconciliados; 0 unresolved; 2 bundles persistidos; 2 tentativas `MATCHED`; IDs de operação distintos; ambos os bundles recuperados do SQLite e classificados `UNKNOWN`; lote liberado para a próxima venue.
- Durante a construção, a primeira fixture falhou porque os campos `included_transfer_fee_amount_in/out` do evento estavam zerados, apesar dos valores de swap serem 100/90. O log expôs a divergência; a fixture foi corrigida para codificar 100/90/90, conforme o layout do decoder. A execução final não usa mocks para mascarar a reconciliação.
- CI push #44411969562 SUCCESS no commit `1ffb850856328835903371165e8bcb739bbac28d`: 493 testes aprovados em 4,176s; `compileall` concluído. O log identifica o novo teste como `ok`.
- O cenário de sucesso é uma fixture RPC sintética determinística, não uma captura Mainnet integral. As evidências Mainnet existentes continuam documentadas nas seções anteriores; não confundir os dois níveis de validação.
- PR #25 permanece OPEN/DRAFT e sem merge. A `main` não foi alterada. BUY/SELL continua `UNKNOWN`; execução financeira permanece desabilitada.
- Próxima ação: acrescentar o teste negativo complementar com duas operações em que ambas as contas/transferências são decodificáveis, mas a reconciliação econômica de apenas uma falha; comprovar que nenhum bundle do lote é persistido e que a venue seguinte/checkpoint continuam bloqueados.


## 204. Falha econômica isolada bloqueia os dois swaps do lote — 18/11/2026

- Adicionado `test_two_swap2_economic_mismatch_blocks_both_bundles_and_next_venue`, reutilizando a fixture RPC ponta a ponta de duas operações já validada na seção 203.
- A segunda operação mantém analyzer, contas e transferências decodificáveis; apenas o snapshot post da token account de saída da segunda operação é alterado em uma unidade mínima (delta esperado 90, observado 89).
- O pipeline executa as etapas reais e a reconciliação econômica rejeita o lote completo: `pending_reconciliation`, 2 swaps decodificados, 0 reconciliados, 2 unresolved, 0 bundles salvos e `ready_for_next_venue=False`.
- O teste confirma duas tentativas `INCOMPLETE`, ausência de bundle para ambos os operation IDs, assinatura não processada e checkpoint inexistente. Assim, uma divergência econômica em apenas uma das operações impede que qualquer operação do lote seja liberada.
- CI push #44412231534 SUCCESS e CI PR #44412243276 SUCCESS no commit `a3a40ddb3cb45dbd0e3986986ce98e058c792e2c`: 494 testes aprovados em 3,902s e `compileall` concluído. Ambos os novos testes (sucesso completo e falha econômica) aparecem como `ok`.
- Evidência permanece em fixture RPC sintética determinística; não equivale a captura Mainnet completa.
- PR #25 permanece OPEN/DRAFT, sem merge; `main` não foi alterada. BUY/SELL permanece `UNKNOWN`; execução financeira desabilitada.
- Próxima ação: reforçar a fronteira de coordenação do WalletMonitor em teste de integração, provando que `ready_for_next_venue=False` impede execução da venue CPMM e preserva checkpoint quando a reconciliação multi-swap DAMM v2 falha.


## 205. WalletMonitor integrado ao lote multi-swap com falha econômica — 18/11/2026

- Adicionado `test_wallet_monitor_blocks_cpmm_on_real_two_swap_economic_mismatch` em `tests/test_damm_v2_persistence_pipeline.py`.
- O teste usa o payload RPC sintético completo de duas operações e o SQLiteEventStore real; o snapshot de saída da segunda operação contém divergência de uma unidade mínima.
- Executa `WalletMonitor._collect_transaction` de verdade. A chamada DAMM v2 percorre analyzer, contas, transferências, snapshots e reconciliação; a falha econômica do lote retorna `ready_for_next_venue=False`.
- CPMM é substituído apenas por um spy para comprovar a fronteira de coordenação: `process_raydium_cpmm_observation` não é chamado.
- Verificações aprovadas: método retorna False; duas tentativas permanecem INCOMPLETE; assinatura não é marcada como processada; checkpoint continua inexistente; assinatura permanece na fila pendente.
- CI push #44412408828 SUCCESS no commit `1b97635b615753f32614deeeb7ccf4d132fdb776`: 495 testes aprovados em 3,905s e `compileall` concluído. Log registra a mensagem de bloqueio do monitor: 0/2 swaps reconciliados, 2 pendências, checkpoint preservado.
- PR #25 permanece OPEN/DRAFT e sem merge; `main` não foi alterada. BUY/SELL permanece `UNKNOWN`; execução financeira desabilitada.
- Próxima ação: validar também o fluxo positivo no WalletMonitor com dois swaps reconciliados, comprovando que CPMM só é chamado depois da persistência bem-sucedida de ambos os bundles; depois revisar os checks da PR no head atual.


## 206. WalletMonitor libera CPMM somente após persistir os dois bundles DAMM v2 — 18/11/2026

- Adicionado `test_wallet_monitor_calls_cpmm_only_after_both_damm_bundles_persist`, usando o payload RPC sintético completo de duas operações da seção 203 e SQLiteEventStore real.
- O teste executa `WalletMonitor._collect_transaction` sem mockar o processamento DAMM v2. O CPMM é substituído por um spy com retorno controlado apenas para observar a fronteira e permitir concluir o fluxo.
- Dentro do spy, o teste consulta o SQLite e exige duas tentativas de reconciliação e dois bundles já persistidos antes da chamada CPMM. A verificação passou.
- Resultado: WalletMonitor retorna sucesso; CPMM chamado exatamente uma vez; ambos os bundles continuam recuperáveis no SQLite. O teste negativo da seção 205 continua provando que, diante de divergência econômica, CPMM não é chamado.
- CI push #44412568453 SUCCESS no commit `8f32b2323f52a7c9c81c7e3d72a58df3d31c371f`: 496 testes aprovados em 5,487s; `compileall` concluído. O novo teste positivo aparece como `ok`.
- O fluxo de CPMM neste teste é um spy, não uma execução real do parser CPMM; a prova cobre a ordem e a condição de entrada na próxima venue.
- PR #25 permanece OPEN/DRAFT, sem merge; `main` não foi alterada. BUY/SELL permanece `UNKNOWN`; execução financeira desabilitada.
- Próxima ação: auditar os checks associados ao head da PR, consolidar a documentação de continuidade e então avançar para cobertura de replay/idempotência do lote completo após falha transitória de persistência.


## 207. Replay ponta a ponta após falha transitória no segundo bundle — 18/11/2026

- Adicionado `test_full_two_swap_pipeline_retries_after_transient_second_bundle_write_failure`, usando a fixture de sucesso multi-swap e o pipeline real sem mocks nas etapas de análise, transferência, reconciliação ou adapter.
- O SQLiteEventStore real grava o primeiro bundle e recebe uma falha transitória injetada somente na segunda chamada de `save_swap_bundle`.
- Após a falha, o teste comprova: primeiro bundle presente; segundo ausente; duas tentativas de reconciliação registradas; assinatura não processada; checkpoint inexistente; assinatura pendente para replay.
- O retry reexecuta o pipeline real. O primeiro bundle idêntico é reconhecido como idempotente; o segundo é gravado. Resultado final `reconciled`, 2 operações reconciliadas, 1 novo bundle salvo no retry e ambos recuperáveis no SQLite.
- O histórico append-only contém quatro tentativas (duas por execução), mantendo os mesmos dois operation IDs. Nenhuma etapa depende de mock de `process_damm_v2_transaction`.
- CI push #44412697052 SUCCESS e CI PR #44412708214 SUCCESS no commit `e0957323fcd3c22aef94d7ead1e1e1c03676caed`: 497 testes aprovados em 4,421s e `compileall` concluído. O novo teste aparece como `ok`.
- PR #25 permanece OPEN/DRAFT e sem merge; `main` não foi alterada. BUY/SELL permanece `UNKNOWN`; execução financeira desabilitada.
- Próxima ação: verificar os checks exigidos e a descrição da PR sem alterar seu estado, depois avançar para a próxima venue/integração somente após revisão de eventuais lacunas remanescentes.


## 208. Coerência estrutural da fixture multi-swap: pools distintos — 18/11/2026

- Durante a revisão crítica da fixture de sucesso multi-swap, foi identificado que as duas operações usavam a mesma chave de pool, embora tivessem vaults e mints diferentes. Isso era estruturalmente incoerente para duas instruções de pool.
- A fixture `_damm_two_swap2_reconciled_raw` foi corrigida para gerar duas chaves de pool distintas a partir de bytes determinísticos e codificar exatamente os mesmos bytes no campo `pool` de cada evento `EvtSwap2`.
- As contas de cada swap continuam independentes; agora cada conjunto de vaults/mints está associado ao seu próprio pool e a associação evento/conta é validada pelo decoder real.
- CI push #44412971060 SUCCESS no commit `21a775a415fca2f75d98e6bb3bf2188c9dfafd80`: 497 testes aprovados em 4,233s; `compileall` concluído. Os testes de pipeline completo e replay idempotente continuam aprovados.
- A mudança é exclusivamente de fixture/teste; não altera lógica de produção. PR #25 segue Draft e sem merge; `main` permanece intacta.
- Próxima ação: confirmar o check PR no HEAD atualizado e concluir revisão de escopo/base da PR sem mudar seu estado nem reescrever a descrição sem autorização.


## 209. Evento EvtSwap2 com pool divergente bloqueia o lote multi-swap — 18/11/2026

- Adicionado `test_multi_swap_event_pool_mismatch_blocks_entire_batch` à integração ponta a ponta.
- O teste parte do payload RPC determinístico de duas operações e altera exclusivamente os 32 bytes do campo `pool` do primeiro evento EvtSwap2, no offset correto do layout Borsh (bytes 16–48 após wrapper Event CPI + discriminator).
- A associação estrutural swap/Event continua presente; a divergência só é detectada na resolução real das contas, que exige igualdade entre `event.pool` e a conta pool da instrução DAMM v2.
- O pipeline rejeita o lote inteiro: 2 swaps decodificados, 0 reconciliados, 2 unresolved, 0 bundles persistidos e `ready_for_next_venue=False`. O teste confirma tentativas INCOMPLETE, ausência dos dois bundles, assinatura não processada e checkpoint inexistente.
- Primeira execução do teste falhou porque o teste alterava bytes 8–40, que pertencem ao discriminator/wrapper, e não ao campo pool. A inspeção do decoder confirmou o offset correto 16–48; a fixture foi corrigida e a nova execução passou.
- CI push #44413649563 SUCCESS no commit `943a18f2208d5fba123207c7012d83a53a227175`: 498 testes aprovados em 4,147s; `compileall` concluído. O novo teste aparece como `ok`.
- PR #25 segue OPEN/DRAFT e sem merge; `main` intacta. BUY/SELL permanece `UNKNOWN`; execução financeira desabilitada.
- Próxima ação: verificar o check de PR no HEAD atual e aprofundar auditoria de evidências Mainnet, especialmente a correspondência de pool e contas para operações múltiplas reais.


## 210. Auditoria das PRs empilhadas #23–#25 e correção dos testes da PR #24 — 18/11/2026

- Confirmada a cadeia de dependências: PR #23 (`feat/damm-v2-economic-reconciliation`) → PR #24 (`feat/damm-v2-swap-domain-adapter`) → PR #25 (`feat/damm-v2-transaction-pipeline`). As 383 commits inicialmente exibidas na PR #25 são cumulativas em relação à base empilhada; a PR #25 altera 41 arquivos e não representa 383 commits exclusivos da etapa final.
- PR #23 tinha um check antigo FAILURE. O job foi reexecutado sem alterar código e passou: run `44308645725`, tentativa 2, 374 testes aprovados em 3,995s e `compileall` concluído.
- A reexecução da PR #24 revelou dois defeitos reais em `tests/test_damm_v2_swap_domain_adapter.py`: (1) import multilinha escrito literalmente com `\n`, causando SyntaxError; (2) ausência do import de `SQLiteEventStore`, causando NameError no teste de round-trip.
- Corrigidos os dois defeitos diretamente na branch da PR #24. Commits: `d3f4b50710734e366c2afeb86374103aade81007` (import multilinha) e `58a19750672851a79e59d4cdfc953a37870e7769` (SQLiteEventStore).
- CI push #44413972426 SUCCESS no commit `58a19750672851a79e59d4cdfc953a37870e7769`: 380 testes aprovados em 3,798s e `compileall` concluído.
- PR #25 permanece OPEN/DRAFT, sem merge. Check PR no HEAD `7010960b0461bdf4d282df5c625ea6bf88b70717` passou com 498 testes em 4,179s e `compileall`. O teste novo de divergência de pool também aparece como `ok`.
- As três PRs continuam Draft e nenhuma foi integrada à `main`. A PR #25 depende da atualização/integração ordenada das PRs anteriores; não executar merge fora da sequência aprovada.
- Próxima ação: revisar se o head da PR #25 já contém integralmente os dois reparos da PR #24 e validar novamente o estado de mergeability/checks após a atualização da cadeia, sem alterar o estado Draft.


## 211. Mainnet: scanner encontra lote DAMM v2 de dois swaps com wSOL compartilhado — 18/11/2026

- Reauditado o workflow Mainnet #43, run `44386973078`, SUCCESS, commit executado `62952962818ebcbcb6c7ca36de3905c21a505d95`.
- As três validações explícitas do workflow foram concluídas: transação conhecida, primeiro candidato real de round-trip wSOL e segundo candidato real de round-trip wSOL. Os dois candidatos de round-trip produziram duas associações `MATCHED`, status `RECONCILED` e 2 bundles cada.
- O scanner consultou até 100 transações recentes, inspecionou 8 candidatas e reportou `failures: {}`. Encontrou `FOUND_SHARED_WSOL_MULTI_SWAP` na assinatura `3mJobQ63JnNPcHDXmrKypgZLJwXzNNQW1h9Ly7uP5wqkHMKb29BTMEGDq6w4nMe1GH32ZhhQdi9aEbzm5ktXFSNS`, slot 471061330.
- Resultado Mainnet do scanner: `matched_swap2_count=2`, `pipeline_status=RECONCILED`; a operação 0 consome wSOL e produz o outro mint; a operação 1 consome esse mint e retorna wSOL.
- A mesma token account wSOL `GYNxJEfFcqCz7t17b7fvJbcKbj1aBpka2LaqwNBguXaS` é usada como input da operação 0 e output da operação 1. O scanner a identifica como `reconciled_shared_wsol_accounts`, comprovando o round-trip compartilhado na mesma transação.
- Essa validação percorre a resolução de contas por instrução/evento; a rotina `decode_damm_v2_swap_accounts` exige que o pool codificado em cada EvtSwap2 seja idêntico à conta pool da instrução correspondente. Portanto o status RECONCILED inclui a checagem de identidade de pool por operação, além da atribuição e reconciliação econômica.
- O scanner Mainnet não encontrou input wSOL com funding externo nessa transação (`funded_shared_wsol_input_accounts=0`); trata-se de uma conta compartilhada no ciclo de duas operações, não de prova de um novo funding nativo.
- As classificações de domínio permanecem `UNKNOWN`; essa validação não gera BUY/SELL nem ordens.
- Evidência é Mainnet real e distinta das fixtures sintéticas da seção 203. PR #25 continua OPEN/DRAFT e sem merge; execução financeira desabilitada.
- Próxima ação: aguardar e validar o CI da PR #25 no HEAD documental atualizado, depois revisar o próximo modo de transação real (multi-swap sem round-trip wSOL ou CPI aninhado) sem relaxar os critérios fail-closed.


## 212. Cadeia empilhada #21–#25 com checks verdes — 18/11/2026

- Revisados os checks dos cinco PRs abertos que formam a cadeia de transferências/fees → atribuição referral → reconciliação econômica → contratos de domínio → pipeline transacional.
- PR #21, HEAD `62b3f54b717cf0e6675610b8b88bdfd8c542581d`: check `test` SUCCESS.
- PR #22, HEAD `b350dca26a5bf0729f58b0770f07b85f5375b9e4`: check `test` SUCCESS.
- PR #23, HEAD `947c056e01bfc7b22037e19e3600a5248a29e281`: reexecução de CI, run `44308645725`, tentativa 2 SUCCESS, 374 testes e compileall.
- PR #24, HEAD `58a19750672851a79e59d4cdfc953a37870e7769`: CI push `44413972426` e CI PR `44413981201` SUCCESS, 380 testes e compileall. Os dois defeitos de import identificados na auditoria foram corrigidos.
- PR #25, HEAD `558006c778d290d73463398a726e037e8535adcc`: CI PR `44414226876` SUCCESS, 498 testes em 3,916s e compileall; o novo teste de divergência do pool está aprovado.
- Todas as cinco PRs permanecem OPEN/DRAFT e com mergeability disponível na última leitura. A cadeia ainda não foi integrada; nenhuma alteração foi feita na `main`.
- A PR #25 contém os dois imports corrigidos do arquivo de teste da PR #24; foi verificado diretamente nos arquivos das duas branches.
- Próxima ação: mapear o próximo nível de dependência da PR #21 e verificar se a branch-base Token-2022 está coberta por PR aberto/fechado e CI verde, para definir a sequência integral de integração sem saltar dependências.


## 213. Mapeamento das dependências anteriores da cadeia CPMM → DAMM v2 — 18/11/2026

- A auditoria foi estendida até as PRs que fornecem a base do pipeline atual. A cadeia de branches relevante é: #5 → #6 → #7 → #8 → #9 → #10 → #12 → #13 → #14 → #15 → #16 → #17 → #18 → #21 → #22 → #23 → #24 → #25.
- PRs #5, #6, #7 e #8 estão abertas, não Draft, com mergeability limpa e checks SUCCESS nos respectivos HEADs.
- PR #9 está aberta, não Draft e mergeable; não há check-run nem status associado ao HEAD `dfac8ce8734808f0a4cbe817b49c47ee7058bd80`. A PR #10, cuja base é exatamente a branch/HEAD da PR #9, possui CI SUCCESS; isso valida o conjunto integrado a jusante, mas não substitui um check direto registrado na PR #9.
- PR #10 e #12 estão abertas, não Draft, mergeable e com checks SUCCESS.
- PR #13 está aberta, não Draft, mergeable e com check SUCCESS. PRs #14–#18 estão abertas como Draft, mergeable e com checks SUCCESS.
- PR #20 foi encerrada deliberadamente sem merge porque duplicava o decoder DAMM v2. A implementação canônica `damm_v2_decoder.py` já está presente na branch base da PR #18; o encerramento não removeu o decoder usado pelo pipeline atual.
- PR #11 é uma linha independente baseada diretamente em `main`; não integra a cadeia de dependências da PR #25 e deve ser auditada separadamente.
- As PRs #21–#25 permanecem como documentado na seção 212. Nenhuma integração foi realizada na `main`.
- Próxima ação: consolidar uma tabela de prontidão por PR e apontar o único elo sem check direto (#9), sem disparar mudanças em branches antigas quando a validação downstream já cobre o código.


## 214. Validação final da revisão de dependências e CI do HEAD atual — 18/11/2026

- A cadeia da PR #25 foi mapeada até a raiz na `main`: #5 → #6 → #7 → #8 → #9 → #10 → #12 → #13 → #14 → #15 → #16 → #17 → #18 → #21 → #22 → #23 → #24 → #25. PR #11 é independente; PR #20 foi encerrada sem merge por duplicação do decoder.
- Os checks dos HEADs #5–#8 e #10, #12–#18 e #21–#25 estão SUCCESS na última leitura. PR #9 não possui check-run próprio; o código está incluído na base da PR #10, cujo check está SUCCESS. Nenhuma dessas informações autoriza merge automático.
- PR #23 recuperou o check com rerun (374 testes); PR #24 teve os dois defeitos de import corrigidos e agora passa (380 testes). PR #25 confirma diretamente os mesmos imports corrigidos em sua própria branch.
- HEAD atual PR #25: `2457846846e37a77b6a4dcae3bed8d8187e7643c`. CI PR #44414530825 SUCCESS: 498 testes em 4,247s; `compileall` concluído.
- PR #25 permanece OPEN/DRAFT, mergeable e sem merge. PRs anteriores continuam abertas conforme o estado individual; `main` permanece intacta.
- O scanner Mainnet #43 identificou uma transação real de duas instruções `swap2` reconciliadas com uma conta wSOL compartilhada entre input da operação 0 e output da operação 1 (seção 211).
- Próxima ação de engenharia: iniciar a cobertura de multi-swap DAMM v2 sem round-trip wSOL, separando o critério de descoberta do critério específico de wSOL; preservar a validação atual como regressão e não alterar o estado das PRs.


## 215. Scanner Mainnet separado por padrão de wSOL e diagnóstico por assinatura — 18/11/2026

- O scanner `tools/scan_damm_v2_multi_swap_mainnet.py` agora aceita `--target shared-wsol` (padrão anterior, mantido) e `--target non-shared-wsol`. Ambos só retornam FOUND quando o lote tem ao menos dois `swap2` MATCHED e o pipeline econômico retorna `RECONCILED`.
- O workflow Mainnet agora executa as duas buscas: shared-wSOL com até 3 páginas de 100 assinaturas; non-shared-wSOL com 1 página de 100. A busca não compartilhada é limitada à amostra recente consultada; resultado vazio não prova inexistência global.
- Adicionados testes unitários para: descoberta de multi-swap reconciliado sem wSOL compartilhado; preservação do comportamento padrão shared-wSOL; e retenção de assinatura/slot dos erros de análise enquanto o scanner continua para a próxima transação.
- Run Mainnet #44415303991 SUCCESS no commit `22acf19ac86ab27db9f6223e33f4995bbffb4ba1`. As três validações de transações conhecidas passaram; a busca shared-wSOL inspecionou 98 transações, sem falhas, e encontrou `4dmHfTNPmK3qYmPSqwkcDhrK6rvGhmWNcRopWjEauif9v41j9aHfg1gFi9T6TkqiU84NzFGoKwE9rMRyt7bqLENt`, slot 471107678, com 2 swaps MATCHED e pipeline `RECONCILED`. A conta wSOL `Cj3i3MYyH7LSGmF377mpTFBuRKhJfkU3Lqc6rcV59BbM` é input da operação 0 e output da operação 1.
- A busca non-shared-wSOL inspecionou 100 transações, sem falhas, e não encontrou candidato nessa amostra (`NO_NON_SHARED_WSOL_MULTI_SWAP_FOUND`, lista de candidatos vazia).
- CI PR #44415313819 SUCCESS no commit `22acf19ac86ab27db9f6223e33f4995bbffb4ba1`: 501 testes aprovados em 3,897s e `compileall` concluído. O teste de captura de assinatura/slot de falhas está aprovado.
- Uma execução intermediária no commit `9b90bb4e5e3057512f36cd67cea7a1d8e9fc9b86` falhou porque o retorno antecipado non-shared não incluía `failure_samples`; corrigido em `22acf19` e validado no CI atual.
- Próxima ação: investigar as três assinaturas Mainnet anteriormente registradas com erro `swap exige 24 bytes` (slots 471107341–471107342), capturando o comprimento real e a instrução específica antes de decidir se são variantes legítimas, payloads malformados ou incompatibilidades do decoder. Não relaxar o fail-closed sem evidência do IDL/programa.


## 216. Legacy swap com padding zero e referral self-account — Mainnet — 18/11/2026

- O inspector confirmou três transações on-chain com discriminator legacy `swap` e dados maiores que 24 bytes: 25 bytes com trailing `00` em duas transações e 32 bytes com trailing oito zeros em uma. O source pinado do programa define `SwapParameters` como dois u64 (24 bytes incluindo discriminator); as transações Mainnet, porém, foram executadas com sucesso pelo programa.
- O decoder agora aceita somente o comprimento base de 24 bytes ou até 8 bytes extras, desde que todos os bytes extras sejam zero. Os bytes de padding são preservados em `DammV2SwapInstruction.trailing_padding`. Padding não nulo ou maior que 8 bytes continua rejeitado. Isso não altera o decoder `swap2`, que mantém comprimento exato.
- A validação Mainnet da assinatura `5ujkLBVBSF8EcQxKAnv3ie4hc5adBUBr8GYCRdfwYcdAank2dbcoA9ustGoUKUwrDDixrkrEVTBSwHFRfET8QtQT`, slot 471107342, passou a retornar `RECONCILED`, 1 bundle e classificação `UNKNOWN`.
- A assinatura `4xYWgBV34xYGfm6KxRRsUKikqQoY596w9yx8S946XNLuixcYvaH3bS3wsLZpmJGaC7aQr6dpW8uirfDfXmV63aKt`, slot 471107342, agora é decodificada e atribuída, mas permanece `REJECTED` porque falta um lado de snapshot econômico. Nenhum bundle é persistido.
- A assinatura mista `2ZgHqn1dExm4TtxFg8ADdj8QTqRHCWodiBHE15me2TkX1JMu6oxZgmtwWcmwCKyP8mmpmbwt2KCLfvRDTUs4B1Z9`, slot 471107341, contém uma instrução `swap2` externa e uma instrução legacy `swap` via CPI. O validator agora aceita transações Solana versionadas até v1; as duas associações ficaram `MATCHED` e as duas evidências de transferência `ATTRIBUTED`.
- A segunda operação da assinatura mista usa o mesmo token account para output e referral. Foram identificadas duas transferências do mesmo vault para a mesma conta: output principal de 84,396,359,546 unidades e referral de 71,448,140, exatamente o `referral_fee` do evento. O transfer analyzer agora usa o valor explícito do evento para selecionar a perna de referral e impede que a mesma transferência seja contada simultaneamente como output.
- Teste unitário `test_referral_transfer_to_output_account_is_not_double_counted_as_output` aprovado. CI push #44417554448 SUCCESS: 504 testes em 4,134s e `compileall` concluído.
- Mesmo após a atribuição correta, a assinatura mista permanece `REJECTED` com motivo explícito: `transfer fee Token-2022 de referral não está explícita nem no evento`. O RPC informa `fee_raw=null` para a transferência; sem prova da taxa Token-2022 histórica, a reconciliação econômica não é liberada e nenhum bundle é persistido. O bloqueio é intencional e fail-closed.
- Mainnet workflow #44417554432 SUCCESS no commit `cde9893bf4714670eae7465008272dc3f780d465`. Check da PR #25 no mesmo HEAD: SUCCESS. PR permanece OPEN/DRAFT, sem merge; `main` intacta.
- Próxima ação: investigar a taxa Token-2022 da transferência de referral sem inferir zero. Precisamos obter evidência histórica da configuração TransferFeeConfig/epoch ou uma fonte on-chain equivalente; até lá, manter o lote INCOMPLETE.


## 217. Fonte histórica para TransferFeeConfig e cliente Helius Historical Accounts — 18/11/2026

- A investigação identificou uma fonte capaz de resolver a lacuna sem reconstruir manualmente todas as instruções de alteração: Helius Historical Accounts API, método proprietário `getHistoricalAccountInfo`. A documentação oficial confirma leitura de estado de conta em slot e imediatamente após uma transação específica (`slot` + `transactionIndex`), com `lastUpdatedAt` indicando a escrita que produziu o estado.
- A cobertura beta começa no slot `444959999` (07/09/2026); portanto, a transação bloqueada na seção 216, slot `471107341`, está dentro da janela publicada. A API é Mainnet-only e exige plano Business ou superior durante o beta; custo de créditos está anunciado como zero durante beta, sujeito a mudança. Não há chave/API key adicionada ao repositório.
- Regra de consulta definida: buscar o estado do mint imediatamente **antes** da transação (mesmo slot e `transactionIndex - 1`; se índice zero, slot anterior) e, para auditoria, também o estado imediatamente depois. Decodificar `TransferFeeConfig` com o decoder offline já existente e selecionar `older_transfer_fee`/`newer_transfer_fee` pelo epoch comprovado. O `context.slot` da resposta não é usado como posição consultada; validar `lastUpdatedAt` para impedir aceitar estado posterior. Escritas fora de transação (`transactionIndex=null`) são ordenadas no fim do slot.
- Implementado `src/smart_money_radar/data_sources/helius_historical_account.py`: cliente HTTPS somente leitura, valida envelope JSON-RPC, resposta, owner/dados base64 e posição `lastUpdatedAt`; trata conta ausente e erros sem ecoar detalhes do endpoint; oferece leitura antes da transação incluindo o caso de índice zero.
- Implementados testes em `tests/test_helius_historical_account.py` para leitura em posição exata, leitura anterior com índice maior que zero, índice zero no slot anterior, rejeição de estado posterior, escrita não transacional no fim do mesmo slot, conta ausente, erro RPC e validações de entrada.
- Commits na branch da PR #25: `5cd0643689d081e8c7eb3013de58c1f73c77f69c` (cliente), `464c2f19c61ab289d497bd7afcaff3653a4e82de` (testes), `83ea7010ed36bf19d16cdd5b53636c94de1c9b82` (ordenação de writes fora de transação) e `1350235a079c4f6a5d6f5db5aa9bee15270352fe` (teste de regressão).
- CI `SMR tests` #1219, run `44419102189`, está em execução no HEAD `1350235a079c4f6a5d6f5db5aa9bee15270352fe`; aprovação ainda não confirmada. Execuções intermediárias #1215–#1218 também foram iniciadas por commits sequenciais e não substituem o resultado do HEAD final.
- **Ainda não houve consulta histórica real**: faltam identificar o mint exato da transferência de referral e o `transactionIndex` da assinatura `2ZgHqn1dExm4TtxFg8ADdj8QTqRHCWodiBHE15me2TkX1JMu6oxZgmtwWcmwCKyP8mmpmbwt2KCLfvRDTUs4B1Z9`, além de endpoint Helius com acesso ao beta. O cliente implementado ainda não está integrado ao pipeline econômico.
- Nenhuma reconciliação foi liberada; o caso da seção 216 permanece bloqueado, sem bundle e sem checkpoint. PR #25 segue OPEN/DRAFT e sem merge; `main` intacta.
- Próxima ação: validar CI #1219; em seguida obter `transactionIndex` e mint da transferência na transação bloqueada, executar a leitura histórica antes/depois e integrar o estado histórico ao cálculo de taxa sem aceitar configuração atual como prova.


## 218. Localização determinística do transactionIndex — 18/11/2026

- Criado `src/smart_money_radar/data_sources/solana_transaction_position.py` para consultar `getBlock` finalized e localizar a assinatura primária dentro da lista ordenada de transações, retornando índice zero-based do bloco.
- O helper valida endpoint HTTPS, slot, assinatura, envelope JSON-RPC, lista de transações, assinatura primária e ausência de duplicidade. Suporta transações versionadas até v1.
- Criado `tests/test_solana_transaction_position.py`, cobrindo índice zero-based, configuração da requisição, assinatura ausente/duplicada, resposta malformada, erro RPC e entradas inválidas.
- CI #1224 (run `44419445767`) SUCCESS no commit `82215266ab171de5956fbc6223407ca5c6ed2217`; CI #1225 e #1226 foram disparados em commits subsequentes e seus estados devem ser consultados separadamente.
- A descoberta do índice resolve uma entrada necessária para consultar o estado histórico imediatamente antes/depois da transação; ainda não foi obtida posição real da assinatura-alvo via RPC neste ambiente.


## 219. Auditor histórico de TransferFeeConfig e withheld referral — 18/11/2026

- Criado `tools/audit_token2022_referral_fee_historically.py`, ferramenta somente leitura que combina `getBlock`/transactionIndex, `getEpochSchedule`, Helius `getHistoricalAccountInfo`, decoder offline `TransferFeeConfig`/`TransferFeeAmount` e aritmética inteira de taxa.
- A ferramenta consulta mint e referral token account antes e depois da transação, seleciona older/newer fee pelo epoch do slot, calcula a taxa esperada sobre o bruto e compara com o delta histórico de `withheld_amount` da conta referral. Se a configuração do mint mudar dentro da transação, se owners forem diferentes de Token-2022, se withheld diminuir ou se a taxa não coincidir, não reporta match.
- A saída `HISTORICAL_FEE_MATCH` é apenas evidência de auditoria: `reconciliation_released` permanece false. A ferramenta não persiste bundles nem avança checkpoint.
- Criados `tests/test_audit_token2022_referral_fee_historically.py` com cenários de epoch, match de withheld delta e mudança de configuração durante a transação.
- A ferramenta exige `SMR_HELIUS_HISTORICAL_RPC_URL` ou `--historical-rpc-url`, além do RPC Solana padrão. Não há API key/segredo gravado no repositório.
- CI #1227 (run `44419493138`) foi iniciado no HEAD `edf191f5a625ff0741577fcea1d7f13e7c91053e`; resultado ainda não confirmado no momento desta atualização.
- **Pendência real:** executar a auditoria com a assinatura da seção 216, slot `471107341`, após obter mint, referral token account e bruto da transferência nos dados do validador, e dispor de endpoint Helius com acesso beta. Nenhum caso real foi reconciliado ainda; o bloqueio fail-closed continua.
- PR #25 continua OPEN/DRAFT e sem merge; `main` intacta.


## 220. Diagnóstico de conta referral compartilhada e auditoria agregada — 18/11/2026

- A leitura dos logs Mainnet workflow #59 (`44417476130`) confirmou que a transação `2ZgHqn1dExm4TtxFg8ADdj8QTqRHCWodiBHE15me2TkX1JMu6oxZgmtwWcmwCKyP8mmpmbwt2KCLfvRDTUs4B1Z9`, slot `471107341`, tem dois swaps, e o segundo tem `has_referral=true`, `referral_fee=71,448,140` raw. O pipeline retorna `REJECTED`, `INCOMPLETE`, sem bundles, por taxa Token-2022 de referral não explícita.
- O diagnóstico Mainnet mostra que output e referral da segunda operação são transferências separadas, ambas do mint `GgGQzgwUBcPZddt4UFULRLeJK2WFhSyFY1VavYK4MCCc`, ambas com destino `DKfXG1ojeZzCgLuMiYJq7LD1RDVgeu7NHPLmsjgTjiRF`: output bruto `84,396,359,546` e referral bruto `71,448,140`. Esse é um caso de conta de destino compartilhada (self-referral).
- Consequência importante: o delta histórico de `TransferFeeAmount.withheld_amount` nessa conta é agregado por conta/transação; não pode ser comparado somente com a taxa calculada sobre o valor referral. O auditor foi corrigido para aceitar múltiplos `--gross-amount-raw`, calcular a taxa de cada perna e comparar a soma com o delta withheld. Para este caso, o workflow passa ambos os valores.
- Criado `tools/inspect_solana_transaction_position.py` para imprimir o transactionIndex zero-based. O workflow Mainnet foi atualizado para localizar esse índice no bloco finalized e para executar opcionalmente o auditor histórico quando o secret `SMR_HELIUS_HISTORICAL_RPC_URL` estiver configurado.
- Workflow Mainnet #64 (run `44419766877`) foi iniciado para validar a nova etapa de posição e, se houver secret configurado, a consulta histórica. O índice real ainda aguarda saída do job.
- CI de PR #25 #1229 (run `44419527316`) SUCCESS no HEAD `a79fb6941f5b06d101d64984d0cbb92ec0b7d6bb`: 521 testes em 3,907s e `compileall` concluído. O CI #1233 (run `44419758247`) está validando a alteração de agregação de taxas no commit `d8a7159ce9dbf4d62eda2c246e4a9b810c63f301`; resultado ainda não confirmado.
- Nenhuma consulta histórica Helius foi comprovada até aqui. Sem secret de acesso beta, a etapa histórica será ignorada; o caso permanece bloqueado e não pode ser liberado.
- PR #25 permanece OPEN/DRAFT e sem merge; `main` intacta.


## 221. Robustez do workflow Mainnet e validação de testes após auditoria agregada — 18/11/2026

- CI #1233 (run `44419758247`) SUCCESS no commit `d8a7159ce9dbf4d62eda2c246e4a9b810c63f301`: 521 testes em 3,994s e `compileall` concluído. CI #1235 (run `44419841383`) SUCCESS no commit `f06cfea906fe1d9cf86ee23d5f1ef49b32047a4c`; CI #1236 (run `44419861136`) SUCCESS no commit `5c2c0e21468a1239baaf690fc11b07f14f71d0d1`.
- Mainnet #64 e #65 falharam antes das etapas de diagnóstico: primeiro o RPC público retornou HTTPError; após trocar para PublicNode, o endpoint não encontrou a transação baseline `1z8...`. Não é falha dos testes do cliente histórico; é limitação/indisponibilidade de dados no endpoint usado para a transação baseline.
- Para que uma assinatura baseline indisponível não impeça os diagnósticos seguintes, a etapa `Validate known real Mainnet transaction` agora usa `continue-on-error: true`. O RPC padrão do workflow foi trocado para PublicNode, mantendo a mesma URL como fonte alternativa da coleta.
- Mainnet #66 (run `44419926312`) foi disparado no commit `3b4065664949700ac8a137a1523c178b7068537a`; aguardando execução da etapa de posição transacional do caso bloqueado.
- O secret `SMR_HELIUS_HISTORICAL_RPC_URL` não está configurado no ambiente GitHub (valor vazio confirmado nos logs). Portanto, a etapa de auditoria histórica fica condicionalmente ignorada até que o endpoint beta seja fornecido. Nenhuma chave foi publicada ou gravada no repositório.
- Estado econômico do caso `2Zg...`: 2 swaps reconhecidos, segunda operação com referral bruto `71,448,140`; transferência de output `84,396,359,546` e referral são para a mesma conta/mint. A auditoria deve comparar o delta withheld agregado com as taxas calculadas de ambas as pernas. Sem consulta histórica real, permanece `INCOMPLETE`, sem bundles e sem avanço de checkpoint.
- PR #25 permanece OPEN/DRAFT e sem merge; `main` intacta.


## 222. Posição Mainnet real resolvida e auditoria pronta para execução — 18/11/2026

- Mainnet workflow #66 (run `44419926312`) SUCCESS no commit `3b4065664949700ac8a137a1523c178b7068537a`. As validações baseline e dos dois candidatos wSOL passaram; as duas buscas de multi-swap terminaram; os três inspectors de instruções passaram; validação e diagnósticos legacy passaram; inspeção do mint atual terminou. A etapa opcional de histórico foi SKIPPED porque `SMR_HELIUS_HISTORICAL_RPC_URL` está vazio.
- A etapa `Resolve exact transaction index for blocked Token-2022 referral case` localizou de forma independente no bloco finalized a posição da assinatura `2ZgHqn1dExm4TtxFg8ADdj8QTqRHCWodiBHE15me2TkX1JMu6oxZgmtwWcmwCKyP8mmpmbwt2KCLfvRDTUs4B1Z9`: slot `471107341`, `transaction_index=144`.
- Com a evidência já registrada na seção 220, os parâmetros exatos do auditor histórico são: mint `GgGQzgwUBcPZddt4UFULRLeJK2WFhSyFY1VavYK4MCCc`; conta referral/destino compartilhado `DKfXG1ojeZzCgLuMiYJq7LD1RDVgeu7NHPLmsjgTjiRF`; transferências brutas para essa conta `84,396,359,546` e `71,448,140`.
- CI #1240 (run `44420031113`) SUCCESS no commit `06bd9ebfc04c7ebb45e53b3c1a1bcbf34727c86e`: 521 testes em 3,919s e `compileall` concluído. O teste de agregação agora usa duas transferências e confere o total de taxas retidas.
- A lacuna restante deixou de ser desconhecimento de assinatura, slot, índice, mint ou conta: é exclusivamente acesso ao endpoint Helius Historical Accounts beta. Sem esse endpoint, não é possível obter os snapshots históricos pré/pós-transação e a taxa permanece sem comprovação.
- Nenhuma reconciliação foi liberada para a assinatura bloqueada; continua sem bundles e sem avanço de checkpoint. PR #25 OPEN/DRAFT e sem merge; `main` intacta.
- Próxima ação: configurar `SMR_HELIUS_HISTORICAL_RPC_URL` como secret do repositório com endpoint Helius Mainnet Business habilitado e executar a etapa opcional. Se não houver esse acesso, planejar fonte histórica alternativa sem substituir evidência histórica por estado atual.


## 223. Prova automática de taxa Token-2022 zero e novo bloqueio cross-venue — 18/11/2026

- A inspeção Mainnet do mint `GgGQzgwUBcPZddt4UFULRLeJK2WFhSyFY1VavYK4MCCc` confirmou owner Token-2022, snapshot finalized posterior ao slot alvo e `TransferFeeConfig` ausente. O source fixado do Token-2022 (`875693f53c77534b46f0d06bdf781430870f8177`) exige `unpack_uninitialized` para inicializar `TransferFeeConfig`; portanto, a extensão precisa ser inicializada antes de `InitializeMint` e não pode ser adicionada após a inicialização.
- Criados `token2022_fee_absence_proof.py` e `token2022_fee_proof_resolver.py`. O resolver identifica referrals Token-2022 sem fee explícita, consulta o transactionIndex e o estado finalized atual do mint, exige transação bem-sucedida e transferência executada do mint, e só emite proof se a configuração estiver validamente ausente. Configuração presente, RPC indisponível, owner divergente ou snapshot anterior mantêm fail-closed.
- A prova zero-fee foi integrada à reconciliação econômica, ao pipeline DAMM v2, à fronteira de persistência e ao `SwapEvidence`. O `WalletMonitor` recebe o resolver por injeção; o CLI de produção o habilita. A consulta de rede do resolver ocorre em thread separada, mas a persistência SQLite continua na thread proprietária da conexão.
- Mainnet workflow #74 (run `44420976969`) SUCCESS no commit `e2157efe9e53dd44b5a4a00e00ca48864a273c85`. Para a transação `2ZgHqn1dExm4TtxFg8ADdj8QTqRHCWodiBHE15me2TkX1JMu6oxZgmtwWcmwCKyP8mmpmbwt2KCLfvRDTUs4B1Z9`, slot `471107341`, índice `144`, o resolver gerou prova de taxa zero para o mint `GgGQ...`, snapshot slot `471118276`, fee `0` raw.
- **O bloqueio Token-2022 foi resolvido para este mint.** A transação inteira ainda permanece `INCOMPLETE` por transferências não atribuídas que afetam contas do swap: (a) ix 4/inner 2, `DKfX...` → `69z...`, mint `GgGQ...`, `84,467,807,686` raw; (b) ix 5/inner 3, `99Ha...` → `6mc...`, mint wSOL, `696,189` raw. Nenhum bundle foi persistido para a transação mista.
- O programa externo `4X3dGCFh63SyE2bNZdGUV7Rj5ukK1XgrxesoxyKQNiRN` aparece nas instruções posteriores, mas sua identificação como venue ainda não está comprovada. A saída da conta DKfX é uma perna downstream de outro fluxo de execução, não uma transferência DAMM v2 isolada. Próximo módulo: identificar o programa CPI/venue exato e construir reconciliação cross-venue para transferências entre swaps na mesma transação.
- CI #1281 (run `44420976898`) SUCCESS no commit `e2157efe9e53dd44b5a4a00e00ca48864a273c85`: 529 testes em 3,923s e `compileall` concluído. O erro intermediário de SQLite thread-affinity foi corrigido mantendo a escrita SQLite na thread original e executando somente o resolver RPC em worker thread.
- PR #25 permanece OPEN/DRAFT, sem merge; `main` intacta.


## 224. Reconciliação cross-venue de rota CPI (PumpSwap + Meteora DLMM) — Mainnet — 18/11/2026

- O decoder de transferências agora preserva `cpi_program_path` por instrução interna, reconstruído com `stackHeight` e a árvore de invocações; caminhos inválidos permanecem vazios/fail-closed. Teste dedicado cobre a cadeia router → programa de venue → Token program.
- Identificada na transação real `2ZgHqn...` a rota de execução: programa externo `4X3d...`; CPI PumpSwap `pAMM...` / `6EF8...` (outer instruction 4); CPI Meteora DLMM `LBUZ...` (outer instruction 5); duas operações DAMM v2 (uma top-level e outra dentro da rota).
- O resolver agora busca proofs de ausência de TransferFeeConfig para todos os mints Token-2022 envolvidos em referrals e transferências de venues roteadas, não apenas para o mint de referral. Foram comprovadas taxas zero para `C5xph...pump`, `GWKw...` e `GgGQ...`, todas com snapshots finalized posteriores ao slot `471107341` e transactionIndex `144`.
- A reconciliação inclui seis transferências cross-venue verificadas por CPI path e deltas de conta: DKfX→69z (GgGQ, 84,467,807,686); 5nK→CSR5 (GWKw, 752,182,085); 48pY→CLN4 (C5xph, 41,295,643); 48pY→DgWan (C5xph, 10,329); CLN4→6r (C5xph, 41,295,643); 99Ha→6mc (wSOL, 696,189). Cada transferência entra uma única vez no ledger esperado; evidências são anexadas ao `SwapEvidence` dos bundles DAMM.
- Mainnet workflow #84 (run `44422687863`) SUCCESS no commit `16acabcd0d72ff12d0f43ea75ebc2b1cc799a2d8`: a transação mista passou a `RECONCILED`, com 2 bundles DAMM v2 e lados de classificação `UNKNOWN`. O caso deixou de ficar bloqueado por taxa Token-2022 ou transferências cross-venue não atribuídas.
- CI #1315 (run `44422696901`) SUCCESS no commit `16acabcd0d72ff12d0f43ea75ebc2b1cc799a2d8`: 532 testes em 3,934s e `compileall` concluído.
- Mainnet workflow #85 (run `44422939879`) SUCCESS no commit `2048b06a82538da2365d476b3c21c6481d9d016d`: a fronteira `process_damm_v2_observation` persistiu em SQLite em memória 2/2 bundles, `persistence_status=reconciled`, `ready_for_next_venue=True`, `checkpoint_after_persistence=None`; ambos os lados de classificação permanecem `UNKNOWN`. Isso valida a fronteira de persistência sem alterar checkpoint nem banco de produção.
- PR #25 permanece OPEN/DRAFT e sem merge; `main` intacta. Próxima ação: fechar a validação de persistência em #85 e, depois, executar o mesmo caminho pelo `WalletMonitor` com resolver injetado.


### Verificação adicional de evidência persistida — 18/11/2026

- A adapter agora inclui em cada `SwapEvidence` todas as provas Token-2022 usadas na transação e todas as transferências cross-venue reconciliadas, não apenas a prova do referral daquele swap.
- O validador Mainnet foi ampliado para reler cada bundle do SQLite em memória e comparar as quantidades de provas e transferências persistidas com a reconciliação em memória. Próximo run #86 valida esse requisito antes de avançar.


### Persistência da evidência cross-venue confirmada — Mainnet #87 — 18/11/2026

- Mainnet workflow #87 (run `44423115845`) SUCCESS no commit `ca3aa1c671092bd0126eada021e368d5e9fa6787`. Além de reconciliar e salvar 2/2 bundles em SQLite em memória, o validador recuperou ambos pelo `operation_id` e confirmou que cada bundle contém exatamente 6 evidências de transferência cross-venue e 3 proofs de taxa Token-2022; ambos mantêm classificação `UNKNOWN`.
- Resultado comprovado: `reconciliation_status=RECONCILED`; `persistence_status=reconciled`; `persistence_saved_bundles=2`; `persistence_ready_for_next_venue=true`; `checkpoint_after_persistence=null`. Não houve avanço de checkpoint.
- CI #1320 (run `44423124451`) SUCCESS no commit `ca3aa1c671092bd0126eada021e368d5e9fa6787`: 532 testes em 3,935s e `compileall` concluído.
- O módulo de prova Token-2022 + contabilidade de transferências cross-venue está validado para a transação Mainnet alvo. Próximo módulo: transformar as pernas externas PumpSwap/Meteora DLMM em operações de swap independentes, com decoders/eventos próprios, em vez de registrá-las somente como transferências de rota anexadas aos bundles DAMM v2.

## 225. Orquestração DAMM v2 + Raydium CPMM validada pelo WalletMonitor — 19/11/2026

- Adicionado teste de integração test_wallet_monitor_runs_real_damm_and_cpmm_pipelines_with_injected_fee_resolver em tests/test_damm_v2_persistence_pipeline.py. O teste executa o pipeline DAMM v2 real com dois swaps sintéticos reconciliados, injeta um resolver de taxa controlado, deixa o adaptador Raydium CPMM real analisar a mesma transação (sem swap CPMM) e confirma persistência dos dois bundles, processamento e checkpoint pelo coordenador.
- CI #1337 (run 44426237583) SUCCESS no commit 58fe20fcb03febabac9e0d7c144a26a3be62889a: 534 testes em 3,934s e compileall concluído. O teste novo aparece explicitamente como aprovado.
- O validador tools/validate_damm_v2_mainnet.py agora executa também o payload Mainnet real pelo WalletMonitor, usando SQLiteEventStore em memória, fonte de replay local e resolver injetado com as provas já obtidas. A validação verifica processed=true, checkpoint igual à assinatura e recuperação de todos os bundles DAMM. Não inicia WebSocket, não grava banco de produção e não executa ordens.
- Mainnet workflow #89 (run 44426405005) SUCCESS no commit 217aff9f0612d14b4e3c206c9c50d3a33f34dad5. Os logs confirmam o caminho WalletMonitor concluído em quatro payloads Mainnet. Para a transação mista 2ZgHqn1dExm4TtxFg8ADdj8QTqRHCWodiBHE15me2TkX1JMu6oxZgmtwWcmwCKyP8mmpmbwt2KCLfvRDTUs4B1Z9, slot 471107341, o coordenador persistiu 2 bundles DAMM v2; cada bundle recuperado contém 6 evidências cross-venue e 3 provas Token-2022; ambos mantêm classificação UNKNOWN. O registro de validação confirma completed=true, processed=true, checkpoint igual à assinatura, SQLite em memória e orders_executed=false.
- CI #1338 (run 44426413104) SUCCESS no commit 217aff9f0612d14b4e3c206c9c50d3a33f34dad5: 534 testes em 3,935s e compileall concluído.
- Commits desta etapa: 58fe20fcb03febabac9e0d7c144a26a3be62889a (teste WalletMonitor com pipelines reais e resolver injetado) e 217aff9f0612d14b4e3c206c9c50d3a33f34dad5 (validação Mainnet pelo coordenador).
- Estado de integração: DAMM v2 e Raydium CPMM executam sequencialmente pelo mesmo WalletMonitor; DAMM v2 não avança checkpoint; CPMM conclui a transação apenas quando os adaptadores anteriores liberam o fluxo. Falhas/pendências mantêm o checkpoint bloqueado.
- PR #25 continua OPEN/DRAFT, base feat/damm-v2-swap-domain-adapter (head da PR #24), mergeable, sem reviews e sem merge. A main permanece intacta; a integração foi validada na cadeia de branches empilhadas, não incorporada à main.
- Próxima ação deste módulo: revisão final da cadeia empilhada e integração controlada das PRs dependentes, sem iniciar o módulo seguinte. A expansão para transformar PumpSwap/Meteora DLMM em operações independentes continua sendo módulo posterior e não deve ser iniciada antes do fechamento desta integração.

### Complemento de validação: caminho positivo Raydium CPMM pelo mesmo WalletMonitor — 19/11/2026

- Adicionado test_real_mainnet_cpmm_fixture_runs_through_shared_wallet_monitor em tests/test_real_mainnet_raydium_cpmm_multivenue.py. Usa fixture pseudonimizada de transação real Mainnet com swap Raydium CPMM MATCHED, passa pelo WalletMonitor completo: adaptador DAMM v2 identifica ausência de swap e libera o seguinte; adaptador Raydium CPMM real reconcilia e persiste 1 bundle; o coordenador marca a transação e avança o checkpoint em SQLite em memória.
- CI #1341 (run 44426812812) SUCCESS no commit be76e5a1cd0cf2e7b61672d2bc4b637bdb891860: 535 testes em 3,937s; o teste novo está aprovado e compileall concluído.
- Combinando esta evidência com Mainnet workflow #89, há validação do caminho positivo de ambos os adaptadores no mesmo WalletMonitor: DAMM v2 com dois bundles reais Mainnet e provas cross-venue; Raydium CPMM com fixture Mainnet pseudonimizada e bundle MATCHED. O teste DAMM + CPMM em uma mesma transação com swaps simultâneos de ambos os programas ainda não foi demonstrado por fixture única; a coordenação sequencial, o bloqueio e cada caminho positivo foram testados separadamente.
- Head atual PR #25: be76e5a1cd0cf2e7b61672d2bc4b637bdb891860. PR segue OPEN/DRAFT, base feat/damm-v2-swap-domain-adapter; nenhuma alteração na main.


## 227. Sincronização da ancestralidade da PR #25 — 19/11/2026

- Auditoria dos dois commits que estavam ausentes na ancestralidade da PR #25: d3f4b50710734e366c2afeb86374103aade81007 (restauração do import multilinha do decoder nos testes) e 58a19750672851a79e59d4cdfc953a37870e7769 (importação de SQLiteEventStore no teste do adaptador). A árvore da PR #25 já continha ambos os ajustes funcionais; a divergência era histórica/ancestral.
- Criado commit de merge explícito 1f2167162a1f61cf35b817f12678fda90273e0fd, com pais 40f0aa1d488c08819e8d3158f81557adf037c279 e 58a19750672851a79e59d4cdfc953a37870e7769. Atualização da branch feat/damm-v2-transaction-pipeline feita como fast-forward do novo commit, usando expected head 40f0aa1d; sem force push e sem alteração na main.
- Comparação posterior: feat/damm-v2-swap-domain-adapter...feat/damm-v2-transaction-pipeline = ahead 502, behind 0. A divergência de 2 commits foi eliminada.
- PR #25 permanece OPEN/DRAFT e não mergeada. No momento da atualização, o campo mergeable retornou false (estado transitório após mudança do head); verificar novamente após os checks. Não houve reviews registradas nas PRs #21–#25.
- CI #1343 (run 44428050448) disparado automaticamente para o novo HEAD 1f2167162a1f61cf35b817f12678fda90273e0fd; no momento deste registro, estava IN_PROGRESS, com instalação concluída e suíte de testes em execução. Resultado ainda não conhecido; não declarar validação pós-sincronização até conclusão SUCCESS.
- A main continua intacta em 5060bc65ddf181a4736fdb662c44c3fec0dd7259. Nenhuma ordem, assinatura de transação ou gravação em banco de produção foi executada.
- Próxima ação: aguardar e inspecionar CI #1343; se SUCCESS, atualizar a descrição da PR e prosseguir com revisão final da cadeia. Se falhar, diagnosticar apenas a falha nova, sem repetir validações anteriores sem necessidade.


### Resultado da validação pós-sincronização — CI #1343 — 19/11/2026

- CI #1343 (run 44428050448) SUCCESS no commit de sincronização 1f2167162a1f61cf35b817f12678fda90273e0fd. Logs confirmam 535 testes executados em 4,262s, todos OK, e etapa compileall concluída com sucesso.
- Comparação da PR #25 com a base após sincronização: 503 commits à frente, 0 atrás. A PR continua OPEN/DRAFT e mergeable=true; não foi mergeada.
- O Registro Mestre foi atualizado depois da execução do CI, gerando o commit 14728293ff2785d6e2fd422b603b6d482647538b. Esse commit contém apenas esta atualização documental; o resultado CI #1343 corresponde ao commit de sincronização 1f2167162a1f61cf35b817f12678fda90273e0fd.
- Estado atual da branch feat/damm-v2-transaction-pipeline: 14728293ff2785d6e2fd422b603b6d482647538b. Main permanece em 5060bc65ddf181a4736fdb662c44c3fec0dd7259.
- Próxima ação: revisão final dos diffs e checks da cadeia #21–#25, sem merge até que a revisão esteja concluída. A fixture única com swaps positivos simultâneos DAMM v2 + Raydium CPMM continua sendo uma cobertura adicional desejável, não um resultado já comprovado.


## 228. Revisão técnica do pipeline Raydium CPMM e contratos compartilhados — 19/11/2026

Escopo revisado em modo somente leitura na branch `feat/damm-v2-transaction-pipeline`, HEAD de referência `552978f9d6a11b8d20e674aae8cdc608d875ae7f`:

- `src/smart_money_radar/domain/raydium_cpmm_persistence_pipeline.py`
- `src/smart_money_radar/domain/swap_bundle_builder.py`
- `src/smart_money_radar/domain/models.py`
- `src/smart_money_radar/data_sources/damm_v2_swap_domain_adapter.py`
- `src/smart_money_radar/domain/damm_v2_persistence_pipeline.py`
- `src/smart_money_radar/services/wallet_monitor.py`
- `tests/test_raydium_cpmm_persistence_pipeline.py`
- `tests/test_real_mainnet_raydium_cpmm_multivenue.py`
- `tests/test_wallet_monitor.py`

Conclusões verificadas no código:

1. O pipeline CPMM valida que a assinatura informada é a primeira assinatura única do payload antes de persistir.
2. A observação bruta/normalizada é persistida sem avançar checkpoint; transação on-chain falha ou ausência de swaps CPMM são estados terminais tratados explicitamente.
3. Para swaps encontrados, a identidade da reconciliação compara o conjunto de (instrução externa, índice inner, caminho CPI), detecta duplicatas e registra explicitamente como `UNRESOLVED` qualquer swap sem resultado do reconciliador.
4. Somente reconciliações `MATCHED` geram bundles. O pipeline confere conjunto/cardinalidade dos operation_ids e alinhamento entre observation, classification e evidence antes de marcar a assinatura processada.
5. Falhas, divergências e exceções deixam a transação replayável e o checkpoint intacto. Bundles positivos podem ser persistidos de forma idempotente enquanto outros swaps permanecem pendentes.
6. O builder CPMM valida transferências executadas, contas, programa SPL, mint, decimals, quantidades, posição na instrução e descendência CPI; gera evidência com programa, venue, caminho CPI, transferências e deltas de token accounts/vaults.
7. Os contratos compartilhados mantêm `SwapObservation`, `SwapClassification` e `SwapEvidence` separados e vinculados pelo mesmo `operation_id`. BUY/SELL exige exatamente um mint explicitamente configurado como referência; caso contrário, classificação UNKNOWN com confiança zero.
8. O adaptador DAMM v2 usa os mesmos contratos, exige reconciliação de lote, associação evento/instrução e evidências de transferência, e não avança checkpoint. O WalletMonitor chama DAMM v2 antes do CPMM e só o CPMM conclui/avança o checkpoint.
9. Os testes de pipeline cobrem reconciliação positiva, pendência, ausência de resultado, duplicidade de reconciliação, divergência de identidade de bundle, replay e checkpoint. A fixture Mainnet CPMM pseudonimizada valida caminho positivo pelo WalletMonitor. Os testes do monitor cobrem bloqueio DAMM e ordenação DAMM→CPMM.

Resultado da revisão desta parte: **nenhum defeito confirmado** nos arquivos examinados. Nenhum código funcional foi alterado.

Lacuna de cobertura mantida explicitamente: ainda não foi demonstrada, por uma fixture única, uma transação com pelo menos um swap DAMM v2 positivo e um swap Raydium CPMM positivo, ambos reconciliados e persistidos pelo mesmo WalletMonitor. A validação Mainnet #89 cobre a transação mista com dois bundles DAMM v2 e evidências cross-venue; o teste CPMM Mainnet cobre uma transação separada em que DAMM v2 libera por ausência de swap. A coordenação sequencial está coberta, mas isso não substitui a fixture simultânea. Não afirmar que a cobertura simultânea já existe.

Progresso da revisão técnica: estimativa atualizada de **75%** (antes 65%), pois o pipeline CPMM, o builder e a compatibilidade estrutural dos contratos foram examinados. O progresso geral do módulo permanece **92%**. Esses percentuais são estimativas de revisão/conclusão, não métricas de testes.

Próxima ação: revisar os detalhes restantes da compatibilidade e da cadeia de PRs #21–#25; decidir se a lacuna de fixture simultânea pode ser coberta com payload Mainnet adequado ou se deve permanecer como critério explícito antes do fechamento. PR #25 permanece OPEN/DRAFT e não mergeada; nenhuma alteração na `main`. Não iniciar PumpSwap/Meteora DLMM como módulo novo antes do fechamento desta integração.


## 229. Correção de compatibilidade Token-2022 no builder CPMM — 19/11/2026

Durante a revisão da cadeia empilhada, foi identificado defeito confirmado entre a PR #21 e o builder de domínio incluído na PR #25:

- PR #21 introduziu `TRANSFER_CHECKED_WITH_FEE` e o reconciliador CPMM passou a retornar `output_amount_raw` líquido (bruto menos fee).
- `domain/swap_bundle_builder.py` ainda rejeitava esse tipo de transferência e comparava a saída reconciliada líquida diretamente com o valor bruto da transferência.
- Consequência anterior à correção: reconciliação podia resultar em `MATCHED`, mas a criação do bundle falhava; o pipeline CPMM permanecia pendente e não avançava checkpoint.

Correção aplicada na branch `feat/damm-v2-transaction-pipeline`:

- `_validate_transfer_evidence` agora aceita `TRANSFER_CHECKED_WITH_FEE` e valida defensivamente fee como inteiro não booleano, não negativo e não superior ao valor bruto.
- A comparação da saída do bundle agora usa crédito spendable: `amount_raw - fee_amount_raw` para TransferCheckedWithFee; transferências comuns mantêm o valor integral.
- Adicionado teste de regressão `test_builds_domain_bundle_for_transfer_checked_with_fee_using_net_output` em `tests/test_raydium_cpmm_transfer_reconciliation.py`, cobrindo reconciliação MATCHED e geração do bundle com entrada bruta 100 e saída líquida 95 unidades mínimas.

Commits:
- Código: `88210dfeb673bd3028a1181c9e9286f8d8094852`.
- Teste: `1ed91c5d51d537ce812d62267387454b40a74a11` (HEAD após a correção).

Validação:
- CI #1349, run `44429585134`, SUCCESS no commit `1ed91c5d51d537ce812d62267387454b40a74a11`.
- Suíte: 536 testes executados, todos aprovados; o teste novo aparece explicitamente como `ok`.
- `python -m compileall -q src tests`: aprovado.
- Não houve alteração na `main`, execução de ordens ou gravação em banco de produção.

Estado de revisão:
- PRs #21, #22, #23, #24 e #25 permanecem OPEN/DRAFT, mergeable, sem reviews e sem threads de revisão registrados na consulta de 19/11/2026.
- A cadeia de dependências permanece #21 → #22 → #23 → #24 → #25; PR #25 tem base #24. Nenhuma foi mergeada.
- A revisão técnica geral fica estimada em **80%**; a conclusão estimada do módulo permanece **92%**. A lacuna de fixture única com swaps positivos simultâneos DAMM v2 + CPMM permanece aberta.
- Próxima ação: continuar a revisão de compatibilidade da cadeia, verificando se existem outros contratos/tipos adicionados em PRs ancestrais que não foram propagados até os adaptadores e builders posteriores. Não fazer merge sem revisão final e autorização.


## 230. Preservação da evidência de referral no contrato SwapEvidence — 19/11/2026

Na revisão da PR #24, foi identificada uma lacuna de proveniência: a camada de atribuição e a reconciliação econômica DAMM v2 validavam a transferência de referral, mas o adaptador de domínio não a propagava para `SwapEvidence`. O bundle persistido registrava genericamente input/output, sem preservar a instrução, contas, mint, valor bruto e fee da perna referral.

Correção aplicada na branch `feat/damm-v2-transaction-pipeline`:

- O adaptador agora exige a transferência referral quando `EvtSwap2.has_referral=True` e `referral_fee>0`.
- Revalida o papel econômico pelo `FeeMode`: vault de origem, conta referral de destino, mint, Token Program, valor bruto igual ao `referral_fee` e execução.
- Inclui a transferência referral na validação da proveniência CPI e valida defensivamente a fee explícita de `TransferCheckedWithFee`.
- Persiste em `SwapEvidence.evidence` os índices da instrução, contas origem/destino, mint, valor bruto e fee da transferência referral.
- Adicionados dois testes: preservação/validação da evidência referral e rejeição de bundle com referral obrigatório ausente.

Commits:
- Código: `4d238ca7215a8e2016b5feddf409cf143486d173`.
- Testes: `328223324b1505dfef2df02a055165ba09ef4dcb` (HEAD após a correção).

Validação:
- CI #1353, run `44429930506`, SUCCESS no commit `328223324b1505dfef2df02a055165ba09ef4dcb`.
- Suíte: 538 testes executados, todos aprovados; os dois testes novos aparecem explicitamente como `ok`.
- `python -m compileall -q src tests`: aprovado.
- Nenhuma alteração na `main`, execução de ordens ou gravação em banco de produção.

Revisão das dependências:
- PR #22: leitura do analisador de transferências/referral e testes; nenhum defeito adicional confirmado.
- PR #23: leitura da reconciliação econômica em lote e testes; nenhum defeito adicional confirmado.
- PR #24: lacuna de proveniência referral identificada e corrigida conforme acima.
- PRs #21–#25 continuam OPEN/DRAFT, mergeable, sem reviews/threads registrados e sem merge. A cadeia continua empilhada em ordem #21 → #22 → #23 → #24 → #25.

Progresso estimado da revisão técnica: **85%**. Conclusão estimada do módulo: **92%**. A fixture única com swaps positivos simultâneos DAMM v2 + Raydium CPMM continua como lacuna explícita. Próxima ação: fechar a revisão técnica da PR #25 e da cadeia, incluindo compatibilidade dos contratos e revisão final dos checks; não fazer merge sem autorização.


## 231. Delimitação de escopo e validação após remoção do decoder roteado experimental — 19/11/2026

Na revisão final dos arquivos da PR #25, foi encontrado `data_sources/routed_venue_swap_decoder.py`, um decoder experimental de PumpSwap/Meteora DLMM que:
- não possuía teste dedicado no PR;
- não tinha referência nos pontos de entrada revisados (`cli.py`, `WalletMonitor`, pipeline DAMM v2, resolver Token-2022 e validador Mainnet);
- podia construir bundle DLMM mesmo sem associação única de `Swap2Evt`, usando transferência como evidência alternativa;
- não integrava o fluxo coordenado/persistido desta PR e ampliava o escopo para o módulo seguinte.

Para preservar a regra de fechar DAMM v2 + Raydium CPMM antes de iniciar PumpSwap/DLMM, o arquivo foi removido da branch atual. Nenhuma dependência do pipeline corrente foi encontrada nos pontos de entrada revisados. O trabalho futuro de PumpSwap/DLMM permanece adiado e deve ter módulo, contratos, fixtures e testes próprios.

Commit de remoção: `74ba9146797f93af52939ff669fa4a07d03b9070`.

Validação após remoção:
- CI #1356, run `44430148964`, SUCCESS no commit `74ba9146797f93af52939ff669fa4a07d03b9070`.
- Suíte: 538 testes executados, todos aprovados.
- `python -m compileall -q src tests`: aprovado.
- A lista de arquivos da PR #25 foi conferida novamente; `routed_venue_swap_decoder.py` não consta mais.
- PR #25 continua OPEN/DRAFT, mergeable=true, base #24, head `74ba9146797f93af52939ff669fa4a07d03b9070`; nenhuma alteração na `main`.

Progresso estimado: módulo **92%**, revisão técnica **90%**. Permanecem: revisão final de detalhes não centrais da PR #25, avaliação/decisão sobre fixture única com swaps positivos simultâneos DAMM v2 + CPMM e revisão da cadeia de merge em ordem. Nenhuma PR foi mergeada; não fazer merge sem autorização explícita.


## 232. CI de conferência após atualização do Registro Mestre — 19/11/2026

- A atualização documental da seção 231 gerou o commit `6b79175951c6e20e3d1546667e22e812c0f85099`.
- CI #1357, run `44430303073`, SUCCESS nesse commit.
- Suíte: 538 testes aprovados; `python -m compileall -q src tests` aprovado.
- PR #25 foi consultada após a atualização: OPEN/DRAFT, mergeable=true, head `6b79175951c6e20e3d1546667e22e812c0f85099`, base `feat/damm-v2-swap-domain-adapter`. Não mergeada.
- A branch main continua sem alteração por esta sequência de commits.
- Estado estimado mantido: módulo **92%**; revisão técnica **90%**. Não elevar o percentual até fechar a revisão final dos arquivos remanescentes e decidir explicitamente a lacuna de fixture simultânea DAMM v2 + CPMM.


## 233. Teste integrado com swaps positivos DAMM v2 + Raydium CPMM no mesmo payload — 19/11/2026

Para cobrir a lacuna de coordenação entre venues, foi adicionado em `tests/test_damm_v2_persistence_pipeline.py` o teste:

`test_wallet_monitor_persists_positive_damm_and_cpmm_swaps_in_one_payload`

Construção da fixture:
- Parte da fixture CPMM Mainnet anonimizada já versionada em `data/fixtures/mainnet/anonymized/raydium-cpmm-route-multivenue.json`.
- Acrescenta ao payload duas operações DAMM v2 sintéticas e reconciliáveis, com remapeamento de accountKeys, programIdIndex, contas e token balance snapshots.
- A fixture é composta para teste de integração; **não representa uma transação Mainnet original contendo simultaneamente as duas venues**.

Comportamento comprovado pelo teste:
- Um único `WalletMonitor` recebe o payload composto.
- Pipeline DAMM v2 processa e persiste dois bundles positivos.
- Pipeline Raydium CPMM processa e persiste um bundle positivo no mesmo payload.
- As três tentativas de reconciliação têm status MATCHED e operation_id distintos.
- Evidências persistidas contabilizam dois bundles `Meteora DAMM v2` e um `Raydium CPMM`.
- A assinatura termina processada, checkpoint avança uma única vez para a assinatura e não restam pendências.

Commit: `6803906f395f87467120409d4562554206f037da`.

Validação:
- CI push #1359, run `44431591042`, SUCCESS.
- CI pull_request #1360, run `44431599422`, SUCCESS.
- 539 testes executados, todos aprovados; o novo teste aparece explicitamente como `ok`.
- `python -m compileall -q src tests` aprovado em ambos os workflows.

Limite de evidência que permanece:
- O teste fecha a cobertura de integração/coordenador com ambos os pipelines positivos num mesmo payload composto.
- Ainda não há uma assinatura/fixture Mainnet original demonstrando coocorrência real de swap DAMM v2 e swap Raydium CPMM na mesma transação. Não confundir fixture composta com evidência on-chain simultânea.
- Progresso estimado: conclusão do módulo permanece **92%**; revisão técnica estimada **93%**. A pendência final é a revisão da cadeia de merge e decidir se a evidência Mainnet simultânea será requisito de fechamento ou validação posterior controlada. PR #25 segue OPEN/DRAFT, sem merge e sem alteração na main.


## 234. Auditoria de ancestralidade das PRs empilhadas — 19/11/2026

Foi investigada a diferença entre os \`base_sha\` registrados nas PRs #8, #10, #15 e #18 e os HEADs atuais das respectivas branches-base.

### Resultado das comparações de branches atuais

1. **#7 → #8**
   - Base atual \`feat/raydium-cpmm-economic-reconciliation\`: \`e72f893b0c717f4d353d18f765d26f22de516b0e\`.
   - \`base_sha\` registrado na #8: \`d2ac22625556303d22031435abd55b7b6cc06776\`.
   - O SHA antigo é ancestral do atual; a branch-base avançou um commit.
   - Comparação da base atual com a head atual da #8: base à frente em 1 commit e head à frente em 5 commits, com merge-base no SHA antigo.

2. **#9 → #10**
   - Base atual \`feat/raydium-cpmm-transfer-reconciliation\`: \`dfac8ce8734808f0a4cbe817b49c47ee7058bd80\`.
   - \`base_sha\` registrado na #10: \`5b57955fa843e4880bb6b8099cb455c160da83e4\`.
   - O SHA antigo é ancestral do atual; a branch-base avançou um commit.
   - Comparação da base atual com a head atual da #10: base à frente em 1 commit e head à frente em 7 commits, com merge-base no SHA antigo.

3. **#14 → #15**
   - Base atual \`integration/pr13-sqlite-persistence\`: \`633dc7b6830672ec1aff61f2dd071c73a5dc31fe\`.
   - \`base_sha\` registrado na #15: \`894b1b0db413f10a456a63f22d2d715e2c6c4cc1\`.
   - O SHA antigo é ancestral do atual; a branch-base avançou um commit.
   - Comparação da base atual com a head atual da #15: base à frente em 1 commit e head à frente em 54 commits, com merge-base no SHA antigo.

4. **#17 → #18**
   - Base atual \`feat/damm-v2-economic-fee-math\`: \`fd0f73284039bacc4ec4e6b6a88def21f813ce0d\`.
   - \`base_sha\` registrado na #18: \`58606137e3d096e19b34eb84bae604101c07fef3\`.
   - A base avançou sete commits depois do SHA registrado na PR.
   - A comparação das branches atuais confirma que a head da #18 contém a base atual como ancestral; head está 24 commits à frente e não está atrás. Esta transição está alinhada.

### Interpretação e estado de mergeabilidade

- As quatro diferenças são explicadas por atualizações posteriores das branches-base; não foi encontrada evidência de perda de ancestralidade.
- Nas três primeiras transições (#7→#8, #9→#10 e #14→#15), a branch filha está um commit atrás da branch-base atual. Isso deve ser levado em conta na atualização/integração da PR filha, com CI posterior; não presumir que o snapshot antigo da base representa o estado atual.
- PRs #8, #10, #15 e #18 foram consultadas novamente: todas OPEN e \`mergeable=true\`. Isso é apenas a avaliação atual do GitHub, não substitui validação de CI após integração.
- PR #20 continua CLOSED sem merge. Sua própria descrição registra encerramento deliberado porque o decoder isolado duplicava o decoder DAMM v2 existente. O arquivo exclusivo da #20 não está na \`main\` nem na branch-base da #21; isso é coerente com a decisão de descartar a implementação redundante.
- A cadeia #21→#25 continua alinhada por SHA entre PRs consecutivas. PR #21 parte da head da #18; PR #25 permanece OPEN/DRAFT e não mergeada.
- \`main\` permanece no SHA conhecido \`5060bc65ddf181a4736fdb662c44c3fec0dd7259\`; nenhuma alteração foi feita nela.

### CI dos commits relevantes examinados

- #7 head \`e72f893b...\`: workflow #105 SUCCESS.
- #8 head \`a6a75128...\`: workflow #99 SUCCESS.
- #9 head \`dfac8ce8...\`: workflow #145 terminou com conclusão \`action_required\`, sem jobs executados. **Não é falha de teste, mas também não é CI aprovado**; requer esclarecimento/aprovação ou nova execução válida antes de considerar esta etapa validada.
- #10 head \`e7c02adb...\`: workflow #115 SUCCESS.
- #14 head \`633dc7b6...\`: workflow #300 SUCCESS.
- #15 head \`ebac8180...\`: workflow #349 SUCCESS.
- #17 head \`fd0f7328...\`: workflow #514 SUCCESS.
- #18 head \`079a7dd6...\`: workflow #528 SUCCESS.
- A PR #25 mantém a validação já registrada na seção 233 e no CI #1361: 539 testes e compileall aprovados.

### Conclusão e próxima ação

A auditoria de ancestralidade esclareceu as diferenças dos quatro pontos. A cadeia não deve ser reordenada por causa dessas diferenças. A sequência de dependências continua de baixo para cima, começando pelas PRs ancestrais; porém, antes de autorizar qualquer merge, deve-se resolver o estado \`action_required\` da CI da head da #9 e confirmar os checks das PRs no momento da integração. Não fazer merge, atualizar branches, alterar bases ou executar reruns sem a etapa de autorização correspondente.

Progresso estimado mantido: módulo **92%**; revisão técnica **93%**. A fixture Mainnet original com swaps positivos DAMM v2 e CPMM simultâneos continua como lacuna distinta da fixture composta de integração. Nenhuma PR foi mergeada e nenhuma alteração funcional foi feita nesta auditoria.


## 235. Investigação do CI action_required e auditoria da nova fixture CPMM da PR #9 — 19/11/2026

### Estado do workflow #145

Foi inspecionado o workflow \`SMR tests\` associado à PR #9:

- Run: \`44226350561\`, número #145.
- Commit: \`dfac8ce8734808f0a4cbe817b49c47ee7058bd80\`.
- Evento: \`pull_request\`.
- Actor e triggering_actor: \`github-actions[bot]\`.
- Conclusão: \`action_required\`.
- Jobs retornados pelo endpoint de jobs: lista vazia; nenhum job foi iniciado.

A execução anterior bem-sucedida da mesma PR foi:
- Run: \`44223562333\`.
- Commit: \`449129f9114420e4f136c0ad081c7820d2d0e399\`.
- Actor: \`Zapatta22\`.
- Conclusão: SUCCESS.
- Job \`test\`: instalação, 169 testes e compileall concluídos com sucesso.

A comparação entre os commits mostra que, após o commit validado, foram adicionados somente:
- \`data/fixtures/mainnet/anonymized/raydium-cpmm-jupiter-multiswap.json\`;
- \`data/fixtures/mainnet/anonymized/raydium-cpmm-jupiter-multiswap.json.manifest.json\`;
- quatro linhas documentais no Registro Mestre.

Portanto, a implementação do correlator da PR #9 tem uma execução anterior aprovada (169 testes), mas o HEAD atual não possui CI aprovado. A nova fixture não foi submetida a testes na execução #145. O actor bot é uma pista compatível com uma exigência de aprovação/política para workflow iniciado por automação; a configuração exata de aprovação do repositório não foi consultada e a causa administrativa específica permanece não confirmada. Não tratar \`action_required\` como falha de teste nem como aprovação.

### Auditoria da fixture adicionada após o CI aprovado

O manifesto \`raydium-cpmm-jupiter-multiswap.json.manifest.json\` declara:
- \`projection_file\`: \`39BtokfG1qiCfmZJJLJzU9nyzHtqQqpXXZCJFFuoutyiHUmSbzi5dmFwCLb8zsH885i1vQgc9N9UfF3wYrgybtz6.json\`;
- \`provenance_manifest\`: \`39BtokfG1qiCfmZJJLJzU9nyzHtqQqpXXZCJFFuoutyiHUmSbzi5dmFwCLb8zsH885i1vQgc9N9UfF3wYrgybtz6.manifest.json\`.

A árvore Git da head \`dfac8ce8...\` contém somente os dois arquivos nomeados \`raydium-cpmm-jupiter-multiswap.json\` e seu manifesto. Os dois caminhos declarados dentro do manifesto não existem nessa árvore. Isso deixa referências de proveniência pendentes/inconsistentes.

Também foi verificado que \`tests/test_raydium_cpmm_transfer_reconciliation.py\` não referencia o nome \`raydium-cpmm-jupiter-multiswap\`. A fixture nova, portanto, não tem cobertura de consumo explícita no teste dedicado consultado. O payload contém uma rota Jupiter com duas instruções CPMM, incluindo movimentação Token-2022, mas não afirmar validação econômica real desta fixture enquanto ela não for carregada e testada por um caso dedicado.

### Conclusão e ação necessária

A PR #9 não está bloqueada por falha de teste demonstrada. Está sem validação de CI para o HEAD atual porque o workflow #145 foi interrompido antes de iniciar jobs; a execução anterior no HEAD antigo passou com 169 testes.

Há uma lacuna concreta adicional: o manifesto da nova fixture aponta para dois arquivos de projeção/proveniência ausentes e a fixture não é referenciada pelo teste dedicado verificado. Antes de considerar a PR #9 plenamente validada para integração, corrigir a proveniência/manifesto de forma compatível com o formato adotado no projeto, criar teste que consuma a fixture e obter CI aprovado no HEAD final. Não alterar o manifesto por suposição: primeiro confirmar o contrato de fixture e o procedimento de anonimização.

Nenhum rerun, aprovação de workflow, alteração funcional, merge ou mudança na \`main\` foi executado nesta investigação. PR #9 permanece aberta; PR #25 permanece aberta/Draft, sem merge. Progresso mantido: módulo **92%**, revisão técnica **93%**.


## 236. Confirmação do contrato do anonimizador para a fixture da PR #9 — 19/11/2026

A revisão foi aprofundada usando \`fixture_anonymizer.py\`, \`fixture_audit.py\`, os testes correspondentes e a documentação da Etapa 13.

Confirmações:
- O anonimizador gera um manifesto de projeção \`smr.anonymized-fixture.v1\` com \`projection_file\` igual ao nome real do arquivo de saída e \`provenance_manifest\` igual ao nome do manifesto bruto de origem quando este é fornecido; quando não há manifesto de origem, o campo fica \`null\`.
- O manifesto bruto coletado pelo \`RpcFixtureCollector\` é um formato diferente, contendo \`raw_file\`, \`sha256\`, \`encoding\`, \`commitment\` e \`anonymized=false\`.
- \`fixture_audit.audit_fixture\` valida pares de manifesto bruto + payload bruto; ele não é um validador do manifesto de projeção anonimizada.
- Na fixture da PR #9, \`projection_file\` aponta para um nome de arquivo que não existe na árvore e não corresponde ao arquivo de projeção efetivamente versionado (\`raydium-cpmm-jupiter-multiswap.json\`).
- \`provenance_manifest\` aponta para \`<signature>.manifest.json\`, também ausente da árvore da PR.
- O manifesto de projeção presente não contém os campos obrigatórios do auditor de manifesto bruto; portanto, não deve ser passado diretamente a \`audit_fixture\`.

Conclusão: a inconsistência não é apenas ausência de teste. O manifesto não descreve corretamente o arquivo de projeção versionado e a trilha declarada para o manifesto de origem não está presente. O bruto original pode permanecer fora do repositório por política de privacidade, mas a proveniência precisa ser representada corretamente: nome da projeção exato e manifesto de origem incluído ou referência nula/externa documentada, conforme política do projeto. Não inventar SHA ou manifesto de origem.

Nenhum arquivo funcional ou fixture foi modificado nesta inspeção. A correção da fixture e um teste de consumo continuam pendentes na PR #9; o HEAD atual segue sem CI aprovado após a adição da fixture. Progresso mantido: módulo **92%**, revisão técnica **93%**.


## 237. CI de confirmação após auditoria da PR #9 — 19/11/2026

Após as seções 235 e 236, o commit documental 28c30c3c6c07cb30eed354b7198838f868db18b1 foi validado pelo workflow da PR #25:

- Run #1364, ID 44433622092, evento pull_request, actor Zapatta22.
- Conclusão: SUCCESS.
- Job test: instalação concluída; **539 testes executados, todos aprovados** (Ran 539 tests in 3.951s, OK).
- python -m compileall -q src tests: aprovado.
- PR #25 continua OPEN/DRAFT, não mergeada, mergeable=true na consulta posterior.

A confirmação CI #1364 valida o conteúdo da branch de integração/Registro Mestre até este commit; não altera o estado da PR #9. A PR #9 continua com head dfac8ce8734808f0a4cbe817b49c47ee7058bd80 e run #145 action_required, sem jobs. A execução anterior #44223562333 aprovou 169 testes no head antigo 449129f9114420e4f136c0ad081c7820d2d0e399. A fixture CPMM/Jupiter recém-adicionada continua sem teste consumidor e com manifesto de projeção/proveniência inconsistente, conforme seções 235–236.

Progresso mantido: módulo **92%**, revisão técnica **93%**. Nenhuma PR foi mergeada; main permanece intacta. Próxima ação: decidir e executar, em branch/PR apropriada, a correção de proveniência e teste dedicado da fixture da PR #9, ou obter uma validação CI aprovada para seu HEAD atual. Não considerar a PR #9 totalmente validada até ambas as lacunas serem resolvidas.


## 238. CI de confirmação do Registro Mestre — 19/11/2026

O commit documental 501a2ae61bc9ee1b1ec240ba92262bb446cdc3b6 (seção 237) foi validado pelo workflow #1365, run ID 44433759007:

- Evento pull_request; actor Zapatta22.
- Conclusão SUCCESS.
- 539 testes executados em 4.684s, todos aprovados.
- python -m compileall -q src tests aprovado.
- Nenhuma alteração funcional foi incluída nesta atualização documental.

Estado confirmado após a execução:
- PR #25 OPEN/DRAFT, não mergeada, head 501a2ae61bc9ee1b1ec240ba92262bb446cdc3b6.
- PR #9 OPEN, head dfac8ce8734808f0a4cbe817b49c47ee7058bd80, run #145 action_required sem jobs; CI anterior no head antigo aprovou 169 testes.
- A fixture CPMM/Jupiter da PR #9 ainda tem manifesto com projection_file divergente do nome do arquivo e provenance_manifest ausente, e não possui teste consumidor dedicado.
- Módulo 92%; revisão técnica 93%; main sem alteração.

Próxima ação técnica recomendada: corrigir a proveniência/manifesto da fixture da PR #9 e adicionar teste que efetivamente a consuma; depois obter CI aprovado no HEAD atualizado. Não mergear a cadeia até essa pendência ser resolvida e os checks finais serem confirmados.


## 239. Correção do manifesto e teste consumidor da fixture CPMM/Jupiter da PR #9 — 19/11/2026

### Alterações efetivamente realizadas na branch da PR #9

- Corrigido \`projection_file\` no manifesto \`raydium-cpmm-jupiter-multiswap.json.manifest.json\`: agora aponta para o nome real versionado \`raydium-cpmm-jupiter-multiswap.json\`. Os hashes existentes não foram alterados.
- Adicionado teste consumidor em \`tests/test_raydium_cpmm_transfer_reconciliation.py\`: carrega a fixture Mainnet anonimizada do disco e executa os decoders reais de swaps CPMM e transferências SPL/Token-2022.
- O teste confirma dois swaps CPMM na instrução externa 0, posições internas 0 e 6, caminhos CPI distintos e stackHeight 2; confirma também as contas de entrada/saída esperadas e sete transferências executadas nas posições internas 1, 2, 4, 5, 7, 8 e 10, incluindo ambos os programas token.
- Escopo do teste é estrutural/decodificação da fixture. Ele não declara reconciliação econômica MATCHED dos dois swaps nem classificação BUY/SELL; isso continua sujeito aos limites do reconciliador e à evidência de saldo.

### CI no HEAD atualizado

- PR #9 HEAD: \`d91f0c277c1daf1f5fff102f85fc55a1c3b07676\`.
- Workflow #1368, run ID \`44434394914\`, evento push.
- Resultado SUCCESS: **170 testes aprovados** e \`python -m compileall -q src tests\` aprovado.
- PR #9 permanece OPEN, não Draft e mergeable=true; não foi mergeada.

### Proveniência remanescente

O campo \`provenance_manifest\` ainda nomeia \`39BtokfG1qiCfmZJJLJzU9nyzHtqQqpXXZCJFFuoutyiHUmSbzi5dmFwCLb8zsH885i1vQgc9N9UfF3wYrgybtz6.manifest.json\`, mas esse manifesto de origem não está versionado na árvore da PR. O bruto original também não está versionado. Não inventamos manifesto bruto, encoding, caminho ou SHA. A referência de proveniência externa precisa ser confirmada/arquivada conforme a política de fixtures antes de declarar a trilha documental integralmente fechada.

Nenhum merge, rebase, aprovação manual de workflow, ordem financeira ou alteração na main foi executado. PR #25 segue OPEN/DRAFT; módulo permanece **92%** e revisão técnica **93%** até a revisão final da proveniência e da cadeia empilhada.


## 240. Integridade criptográfica do manifesto da fixture CPMM/Jupiter — 19/11/2026

Foi ampliado o teste consumidor da PR #9 para validar também o manifesto da projeção:
- schema \`smr.anonymized-fixture.v1\`;
- \`projection_file\` igual ao nome real do JSON;
- SHA-256 do arquivo de projeção recalculado em runtime e comparado com \`projection_sha256\`;
- assinatura e slot do manifesto iguais aos valores do payload;
- \`anonymized=true\`.

Commit da PR #9: \`b9dfe8f2869cec7e14ee20caa091431f2c2a4c1a\`.
CI #1370 (push, run \`44434546829\`) e CI #1371 (pull_request, run \`44434553632\`) concluídos com SUCCESS. Ambos executaram **170 testes aprovados** e \`python -m compileall -q src tests\` aprovado. O workflow #1371 corresponde ao HEAD atual da PR #9 e não está em \`action_required\`.

A trilha de proveniência externa permanece a única lacuna específica da fixture: o manifesto de origem indicado em \`provenance_manifest\` e o payload bruto não estão versionados, portanto não foi possível revalidar o \`raw_sha256\` a partir do artefato bruto. Não foi fabricada evidência ausente. PR #9 segue OPEN, mergeable=true, não mergeada; PR #25 segue OPEN/DRAFT. Main continua no SHA \`5060bc65ddf181a4736fdb662c44c3fec0dd7259\`.


## 241. Fechamento da rodada de teste da fixture CPMM/Jupiter — 19/11/2026

A segunda revisão do teste consumidor confirmou a integridade criptográfica da projeção: o teste recalcula SHA-256 dos bytes de \`raydium-cpmm-jupiter-multiswap.json\` e compara com \`projection_sha256\` do manifesto, além de conferir schema, nome do arquivo, assinatura, slot e \`anonymized=true\`.

Evidências:
- PR #9 HEAD final desta rodada: \`b9dfe8f2869cec7e14ee20caa091431f2c2a4c1a\`.
- CI #1370, run \`44434546829\`, evento push: SUCCESS, 170 testes, compileall SUCCESS.
- CI #1371, run \`44434553632\`, evento pull_request: SUCCESS, 170 testes, compileall SUCCESS.
- PR #9 OPEN, não Draft, mergeable=true; base \`feat/solana-token-account-deltas\`.
- PR #25 OPEN/DRAFT, mergeable=true; head documental \`94a3fa39a32849d427477db44c594fa127370c23\`.
- \`main\` permanece em \`5060bc65ddf181a4736fdb662c44c3fec0dd7259\`.

A única lacuna documental remanescente da fixture é a disponibilidade verificável do artefato bruto e do manifesto original apontado por \`provenance_manifest\`. O campo foi preservado para não apagar a referência histórica; não criamos substituto sintético nem declaramos o SHA bruto auditado. A fixture anonimizada, sua integridade SHA-256, seu consumo pelos decoders e o CI no HEAD atual estão validados.

O commit desta atualização altera apenas este Registro Mestre em Markdown; o workflow \`smr-tests.yml\` filtra paths de código/testes/configuração e, portanto, não se espera CI para este commit documental isolado. Não houve merge, rebase, alteração na main ou execução financeira.


## 242. Reauditoria da ancestralidade da PR #10 após atualização da PR #9 — 19/11/2026

A PR #9 avançou até \`b9dfe8f2869cec7e14ee20caa091431f2c2a4c1a\`. A PR #10 continua baseada na branch \`feat/raydium-cpmm-transfer-reconciliation\`, mas seu head não incorporou esses quatro commits posteriores da base.

Comparação atual:
- PR #10 base atual: branch \`feat/raydium-cpmm-transfer-reconciliation\`, SHA \`b9dfe8f2869cec7e14ee20caa091431f2c2a4c1a\`.
- PR #10 head: \`e7c02adb3564fefb3a8c734098f5c92603eb4a7b\`.
- Merge-base: \`5b57955fa843e4880bb6b8099cb455c160da83e4\`.
- Base: 4 commits à frente do merge-base; head #10: 7 commits à frente; comparação divergente, sem evidência de perda do ancestral comum.
- GitHub informa \`mergeable=true\`; PR #10 OPEN, não Draft, não mergeada.
- Os arquivos funcionais da PR #9 (fixture e teste de reconciliação) não se sobrepõem aos arquivos funcionais próprios da PR #10 (builder de contratos de domínio e seus testes). Ambas alteram o Registro Mestre/documentação; GitHub não reporta conflito no estado atual.

CI conhecido da PR #10:
- Run \`44223834918\`, workflow #115, SUCCESS no head antigo \`e7c02adb...\`.
- 181 testes aprovados e compileall aprovado.
- Esse CI não valida a combinação com os quatro commits novos da base #9. A validação do merge resultante deve ocorrer quando a integração bottom-up for autorizada/realizada.

Não atualizar branch, rebasear ou mergear PR #10 nesta auditoria. A cadeia permanece empilhada; a atualização da base é uma diferença explicada, não uma razão para reordenar PRs.
