# Estado de desenvolvimento do Smart Money Radar

Auditoria de 19/11/2026. A referência de integração é a `main` em `5060bc6`. O histórico de PRs abaixo distingue merges em branches intermediárias de integração na `main`.

## Critérios de conclusão

Os percentuais medem três marcos binários de aceitação por módulo, de peso igual. **B** exige uma base funcional na `main` com teste automatizado aprovado. **I** exige o escopo completo integrado à `main` no caminho de uso, com testes de aceitação. **O** exige validação operacional reproduzível. O percentual global dá peso igual aos nove módulos enquanto não houver pesos aprovados. São **5/27 marcos (18,5%)**. As entregas em Draft aparecem como evidência adicional e entram no índice após integração. Nenhum módulo atingiu o marco operacional.

| Módulo | B/I/O | Marcos | Evidência disponível | Critério para fechar o módulo |
|---|---|---:|---|---|
| A. Infraestrutura e persistência | 1/0/0 | 33,3% | Na main há SQLite, checkpoints, backup/replay e CI. As PRs #40 e #42 revisam persistência de swaps, concorrência, migração e replay. | Integrar persistência de swaps no caminho normal. Validar migração e recuperação no ambiente operacional e observabilidade estruturada. |
| B. Monitoramento Solana | 1/0/0 | 33,3% | Na main há RPC e WebSocket para monitoramento e coleta. As PRs #43–#56 integram captura TLS, auditoria, replay, projeção SQLite, evidência Yellowstone, reconciliação DAMM v2 e comprovação de índice no bloco. | Validar receptor, sequência compartilhada, persistência, reconexão, lacunas, duplicatas e replay com eventos do provider. |
| C. Interpretação econômica | 1/0/0 | 33,3% | Na main há contratos de swap e parser conservador. As branches CPMM/DAMM v2 têm decodificadores, reconciliação e fixtures. | Integrar CPI, CPMM, DAMM v2, Token-2022 e wSOL. Validar evidência de BUY/SELL e rejeição da ambiguidade. |
| D. Launch Radar | 0/0/0 | 0% | Catálogo de programas na main. | Integrar detecção de mints e pools, liquidez, permissões, concentração, volume, preço e sinais de fraude. |
| E. Smart Money Radar | 1/0/0 | 33,3% | Monitor de carteiras com backfill e testes na main. | Validar histórico, acumulação, atividade coordenada e classificação de sinais com evidência. |
| F. Motor de decisão | 0/0/0 | 0% | Contratos de observação e classificação na main. | Testar entrada imediata e confirmação por preço/volume com os mesmos bloqueios. Demonstrar pontuação, exposição, slippage, deduplicação, kill switch e saídas. |
| G. Simulação | 0/0/0 | 0% | Há replay de ingestão na main. | Validar paper trading, custos, backtest sem dados futuros, comparação dos modos, drawdown e latência. |
| H. Interface | 0/0/0 | 0% | Serviço de dashboard somente leitura e testes em branches avançadas. | Integrar e testar em desktop e celular monitoramento, configurações, modos, sinais, alertas e relatórios. |
| I. Preparação operacional | 1/0/0 | 33,3% | CI, configuração local testada e documentação de coleta e execução Android. | Exercitar implantação, segredos, disponibilidade, recuperação, integração, carga e checklist de segurança. |

## Dependências verificadas no Git

- A PR #4 está aberta contra `main`. A correção SQLite desta etapa parte dela. A PR #5 também parte de `main`. A pilha CPMM passa por #6–#8 e pelos merges em branches intermediárias #9, #10 e #12–#16. A persistência usada nessa pilha chegou pelo merge da #14 e terá de ser reconciliada com a revisão da #4.
- A PR #23 foi mesclada em `feat/damm-v2-referral-transfer-attribution` e sua branch de origem inclui o trabalho das PRs #34–#36. A trilha de adaptação e pipeline DAMM v2 continua nas PRs abertas #24 e #25.
- A PR #26 está aberta contra `feat/damm-v2-economic-reconciliation`. O histórico de #26 já contém #27 (rebuild com memória limitada) e #28 (elegibilidade de entregas) por meio da #30. A PR #29 segue aberta, mas sua árvore difere da #26 apenas nos registros e na documentação da política RAW. Conferir o delta residual antes de promover.
- A PR #31 trata sequências anômalas e a #33, conflitos de linhagem. Ambas apontam para `feat/damm-v2-economic-reconciliation`. A #32 exclui sequências historicamente comprometidas e aponta para a branch da #26. Os três heads estão fora da história da #39.
- A PR #39 está em Draft sobre `feat/token2022-transfer-checked-with-fee`; sua história já alcança `main` e `d08c146` (#23). A suíte offline da #39 tem 617 testes. Os campos de fonte, stream, domínio e sequência são declarados pelo chamador. A correção de proveniência verifica conteúdo protobuf, enquanto autenticação da origem e continuidade exigem o receptor compartilhado. Índice da transação no bloco e sequência de transporte têm finalidades distintas. A presença de meta, inclusive protobuf vazio, significa presença do campo. A evidência para classificação requer verificações adicionais.
- A revisão do Yellowstone parte da #39. A #44 adiciona schema SQLite v3 e armazenamento dos envelopes por entrega com verificação de SHA-256 no replay. A #45 reconstrói a timeline em memória a partir da sequência compartilhada entre conta, transação, slot e controle, preservando o baseline por conexão. A #46 materializa a timeline de contas e seu checkpoint atomicamente no SQLite, preservando a referência ao frame de origem. A #47 reutiliza os decodificadores Solana para derivar evidência do replay. A #48 vincula transições elegíveis no mesmo snapshot. A #49 expõe a inspeção local em modo somente leitura. A #50 implementa captura TLS com reconexão limitada e foi exercitada em loopback. A #51 usa o reconciliador econômico existente após verificar finalidade reportada pelo banco. A #52 comprova o índice da transação com um bloco íntegro da mesma captura. A #53 verifica o withheld Token-2022 por estados adjacentes no mesmo banco e pela conferência dos saldos disponíveis. As PRs #54 e #55 verificam a configuração histórica do mint no epoch informado e entregam os snapshots ao cálculo de referral. A #56 persiste o resultado de captura por sessão. A validação com provider externo segue pendente.

## Verificações executadas localmente

| Referência | Evidência |
|---|---|
| `main@5060bc6` | 98 testes aprovados. |
| `817069c` + correção SQLite `0a13a77` | 109 testes aprovados, incluindo concorrência, colisão entre carteiras e rollback. `compileall` e `git diff --check` aprovados. |
| `51ea578` (PR #39) | 617 testes aprovados. |
| `bcd647a` (#41) | 617 testes aprovados. `compileall` e `git diff --check` aprovados. Os testes protobuf são offline. |
| `08e1bf5` (#42) | 252 testes aprovados. Uma verificação separada abriu um banco de `main@5060bc6`, preservou payload e checkpoint, processou a projeção multivenue e repetiu sem duplicar. `integrity_check` e `foreign_key_check` passaram. |
| `1e9c1ba` (#43) | 639 testes aprovados após combinar #26, #31, #32 e #33. `compileall` e `git diff --check` aprovados. |
| `abf3ac0` (#44) | 643 testes aprovados. Migração, replay após reinício, lacunas, duplicatas, colisões e hash verificados. |
| `d51cfe2` (#45) | 645 testes aprovados, incluindo a continuidade da timeline e o decoder por descriptor. `compileall` e `git diff --check` aprovados. A verificação offline adicional com o schema upstream usou uma fixture de conta, uma transação sintética e um ping. |
| `ddf5dbf` (#46) | 646 testes aprovados. Falhas de SQL, chegada de frame durante rebuild e colisão posterior cobertas. `compileall` e `git diff --check` aprovados. |
| `a7be4e9` (#47) | 647 testes aprovados. Replay de CPI, transferências, saldos, falha on-chain e metadados ausentes. |
| `631bad4` (#48) | 648 testes aprovados. Transição compatível, finalidade reportada, banco zero ou divergente, outra conexão e assinatura duplicada. |
| `80fd4f6` (#49) | 649 testes aprovados. CLI sem configuração Helius, arquivo SQLite preservado e teste adicional com descriptor oficial e frame sintético. |
| `bca6838` (#50) | 651 testes aprovados. Teste local gRPC TLS com descriptor oficial verificou Subscribe, ping, preservação dos bytes e limite de frames. Teste automatizado verificou o orçamento compartilhado entre tentativas e interrupção em erro de permissão. |
| `9b863e5` (#51) | 652 testes aprovados. Reconciliação DAMM v2 após finalidade reportada, bloqueio em banco morto e taxas históricas ainda sem verificação. |
| `e62fa2c` (#52) | 653 testes aprovados. Índice comprovado no bloco completo e rejeição de bloco filtrado, meta incompatível e hash divergente. |
| `a026a11` (#53) | 653 testes aprovados. Withheld verificado em estados de transações adjacentes, ausência de prova conserva a marcação anterior e delta divergente bloqueia. |
| `62af8dd` (#54) | 655 testes aprovados. Verificação de taxa conforme prestate adjacente e epoch derivado; outro epoch com taxa divergente bloqueia. |
| `7e051fe` (#55) | 656 testes aprovados. Replay de referral com frames arquivados exige prestate e epoch, calcula uma unidade de taxa e verifica a configuração. |
| `db52904` (#56) | 657 testes aprovados. Schema 3 legível, migração preservada e resultados gRPC persistidos com contagem de frames. |

Validação operacional pendente. Permanecem pendentes a captura de eventos Yellowstone, recuperação ponta a ponta com provider, carga em volume representativo e implantação.

## Próxima tarefa prioritária

Validar as PRs #50–#56 com um endpoint Yellowstone autorizado e um getEpochSchedule arquivado da mesma rede. Capturar transações, contas, slots, metadados e blocos completos da mesma sessão. Exercitar um swap DAMM v2, preferencialmente com referral, e registrar a cobertura real dos estados adjacentes exigidos pelos verificadores de taxa.

A trilha CPMM pode avançar em paralelo com a revisão das PRs #40 e #42, seguida da aplicação das correções nas branches descendentes da integração #14.

## Retomada

| PR | Branch | Commit de código | Base |
|---|---|---|---|
| [#40](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/40) | `codex/smr-sqlite-readiness` | `0a13a77` | `817069c` (#4) |
| [#41](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/41) | `codex/smr-yellowstone-wire-integrity` | `bcd647a` | `51ea578` (#39) |
| [#42](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/42) | `codex/smr-cpmm-sqlite-regression` | `08e1bf5` | `4951eaf` (pilha CPMM de #14) |
| [#43](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/43) | `codex/smr-geyser-stack-integration` | `1e9c1ba` | `bcd647a` (#41) |
| [#44](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/44) | `codex/smr-yellowstone-frame-journal` | `abf3ac0` | `1e9c1ba` (#43) |
| [#45](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/45) | `codex/smr-yellowstone-timeline-replay` | `d51cfe2` | `abf3ac0` (#44) |
| [#46](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/46) | `codex/smr-wire-projection` | `ddf5dbf` | `d51cfe2` (#45) |
| [#47](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/47) | `codex/smr-yellowstone-transaction-evidence` | `a7be4e9` | `ddf5dbf` (#46) |
| [#48](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/48) | `codex/smr-yellowstone-account-evidence` | `631bad4` | `a7be4e9` (#47) |
| [#49](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/49) | `codex/smr-yellowstone-evidence-cli` | `80fd4f6` | `631bad4` (#48) |
| [#50](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/50) | `codex/smr-yellowstone-grpc-capture` | `bca6838` | `80fd4f6` (#49) |
| [#51](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/51) | `codex/smr-yellowstone-damm-reconciliation` | `9b863e5` | `bca6838` (#50) |
| [#52](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/52) | `codex/smr-yellowstone-block-order` | `e62fa2c` | `9b863e5` (#51) |
| [#53](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/53) | `codex/smr-yellowstone-withheld-history` | `a026a11` | `e62fa2c` (#52) |
| [#54](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/54) | `codex/smr-yellowstone-mint-history` | `62af8dd` | `a026a11` (#53) |
| [#55](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/55) | `codex/smr-yellowstone-referral-history` | `7e051fe` | `62af8dd` (#54) |
| [#56](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/56) | `codex/smr-yellowstone-capture-audit` | `db52904` | `7e051fe` (#55) |

Use o SHA exibido no resumo do GitHub Actions para vincular a validação ao commit. Inicie a retomada pela tarefa prioritária acima.

Para reproduzir localmente:

```sh
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -q
python -m compileall -q src tests
git diff --check
```

O workflow SMR tests executa verificações de código no push, em PRs direcionadas às bases cobertas ou por disparo manual no ref selecionado. Ele registra o SHA, os resultados e a tarefa prioritária no resumo do GitHub. Cada job tem limite de 10 minutos. Para o mesmo ref e tipo de evento, uma execução nova cancela a anterior, com uma tentativa por disparo e sem retry automático. Falha de instalação, testes ou compilação bloqueia a promoção da etapa. A proteção de branch depende da configuração do repositório.

A ação oficial `openai/codex-action` inicia Codex CLI via API e depende de credencial e orçamento. A sessão atual não confirmou uma integração autorizada para disparar novas sessões do Codex Cloud. A retomada do agente permanece manual. O workflow usa runner padrão e não provisiona serviços pagos nem agenda consumo recorrente. [Documentação da Codex GitHub Action](https://github.com/openai/codex-action)

Execução financeira real permanece desabilitada. Antes de qualquer alteração desse limite, são necessárias autorização específica e validação operacional independente.
