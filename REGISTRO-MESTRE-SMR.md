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
- Raw RPC SHA-256: `12e48f9cb3082355756b1bd96bbbb68f2561f3bae82191585c818a089f4c0e00`.
- Projeção anonimizada: `data/fixtures/mainnet/anonymized/raydium-cpmm-token2022-fee.json`; SHA-256 `0f400421d25dd40ca65d13216543d292be1b8aa1a61c5b57550220f019c0556c`. Manifesto adjacente registra proveniência, hash, slot e anonimização.
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
- **39Btokf…** — run `44225638797`, artifact `14391914482`, slot `469955314`, version `1`, raw SHA-256 `b0088af96188b178ade106476b831f7ccd85fea3b8b26abb7fb39ab6d4cee96b`. Uma instrução externa agregadora contém dois swaps CPMM CPI no mesmo grupo, com múltiplas token accounts, vaults e owners. Candidato para análise posterior de múltiplas operações; não foi anonimizado nem commitado e não deve ser tratado como fixture aprovada.
- **Zai2u…** — run `44225724731`, artifact `14393250687`, slot `469895550`, version `legacy`, raw SHA-256 `1bad458bd1252288b16083f52327d91659ed2d663a570e061601bc39a1d5a033`. CPMM externo no índice 4; a conta de entrada do usuário aparece apenas em `preTokenBalances`, sem par completo em `postTokenBalances`; não é fixture positiva.
- Todos os artefatos acima são privados, somente leitura, com retenção de 7 dias. Nenhum raw adicional ou mapa de anonimização foi commitado.

### CI e branch de coleta
- PR #11 head atual `7159e5f07549cb31bfe5b6558abfcf9fff0303c4`, base `main`, aberto, mergeable/clean, não merged.
- PR CI run `44225733787`: success; `Ran 99 tests`, `OK`; compileall aprovado. Inclui suporte a `maxSupportedTransactionVersion=1`.
- A busca já inspecionou transações CPMM externas, CPMM CPI via Jupiter/Axiom, versões legacy/v0/v1, Token-2022 e contas criadas/fechadas. A maioria dos candidatos SOL/WSOL fecha uma das token accounts na mesma transação; outros apresentam divergência de vault ou múltiplos swaps complexos.

### Estado e próxima ação
- Ainda não há fixture mainnet que passe MATCHED. Isso é uma lacuna real de validação, não motivo para enfraquecer as regras.
- Próximo passo: localizar swap token-token com contas de usuário persistentes e deltas de ambos os lados, ou analisar cuidadosamente o candidato multi-swap `39Btokf…` sem presumir atribuição de owner/transferências.
- Não integrar persistência nem ativar execução financeira até existir caminho positivo comprovado por fixture real.


## 24. Atualização 2026-11-18 — fixture real Jupiter com dois swaps CPMM

### Coleta e anonimização
- Transação finalized, slot `469955314`, version `1`, `meta.err=null`.
- Assinatura e payload bruto permanecem documentados em manifesto privado/artefato de coleta; raw artifact run `44226316427`, retenção 7 dias. O bruto e o mapa reversível não foram commitados.
- Projeção anonimizada commitada: `data/fixtures/mainnet/anonymized/raydium-cpmm-jupiter-multiswap.json`; manifesto adjacente. Raw SHA-256 `b0088af96188b178ade106476b831f7ccd85fea3b8b26abb7fb39ab6d4cee96b`; projeção SHA-256 `dd00ef311cf9d18d2bf249eb6e287e22dade132c6c586abb69bd5cda16a2408d`; 10 endereços substituídos, 16 endereços protegidos. Program IDs e mints foram preservados; contas pessoais foram pseudonimizadas.

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
- O workflow de coleta foi atualizado para o candidato `3DNxx…DK4t`; a coleta executou automaticamente após o commit, sem ação manual do usuário.
- Run de coleta `44228609083`: sucesso. Job de RPC e upload de artefato concluídos.
- Artefato bruto privado `14394540849`, ZIP `smr-mainnet-candidate-raw-44228609083.zip`; expira em 7 dias. Contém payload RPC e manifesto.
- Slot `388739013`, versão `0`, commitment `finalized`, `meta.err=null`; raw SHA-256 `89dbe2cb81c8995206c541b410660c81f493a571141e61e1b3074c6c90e9e082`.
- Projeção mínima anonimizada adicionada em `data/fixtures/mainnet/anonymized/raydium-cpmm-route-multivenue.json`, manifesto adjacente. Projection SHA-256 validado pelo CI: `7cb198239b5f1c7e83e9b80d3191c8f402db91da87930471349349d32b4e8233`. Vinte endereços foram pseudonimizados; mapa reversível permanece fora do repositório.
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
- Novo CI após a correção ainda precisa ser confirmado. Não registrar a suíte como aprovada até o run atualizado concluir com sucesso.
- PR #13 permanece aberto, sem merge. Nenhuma ordem, assinatura ou submissão financeira foi criada.

### Estado consolidado e próxima ação
- Agora há duas fixtures mainnet positivas independentes para o caminho CPMM `MATCHED`: (1) rota Jupiter com duas operações CPMM, sendo a primeira MATCHED e a segunda INCOMPLETE; (2) rota multi-venue com uma operação CPMM MATCHED e contas intermediárias reconciliadas por todas as transferências.
- As fixtures fail-closed anteriores permanecem intactas: conta temporária sem delta, divergência Token-2022 gross/net, e swaps em rota sem prova completa.
- Próxima ação: confirmar CI da correção do manifesto. Se passar, revisar o diff agregado do PR #13 e a integridade das projeções antes de propor qualquer merge. Não fazer merge sem aprovação explícita do usuário.
