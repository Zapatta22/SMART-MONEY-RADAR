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
