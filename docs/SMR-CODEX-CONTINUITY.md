# SMR — Registro de continuidade para Codex

Atualizado em 2026-11-20 (UTC). **Este documento é um ponto de partida, não substitui a auditoria do GitHub.**

## Onde retomar

- Repositório: `Zapatta22/SMART-MONEY-RADAR`.
- PR de trabalho: **#64**, Draft, branch `feat/cpmm-reserve-estimator-audit`.
- Base conhecida da PR #64: `codex/smr-paper-pool-scope` (PR #63).
- Último commit de código desta sequência: `39ce9f8c061570e0190f7889105adf2fe964ebc9`.
- **Não presumir que a PR, a branch, o SHA ou o CI permanecem iguais. Consultar o estado atual antes de editar.**

## O que foi acrescentado nesta sequência

1. `cpmm_reserve_estimator.py`: estimativa matemática CPMM genérica, não quote executável.
2. `cpmm_reserve_snapshot.py`: validação de campos declarados e hashes RAW; origem RPC ainda não autenticada.
3. `cpmm_vault_account_check.py`: verificações de contas vault SPL legadas no mesmo slot, com IDs fornecidos pelo chamador.
4. `cpmm_pool_config_envelope.py`: envelope RPC base64 para PoolState/AmmConfig; não prova ordem dos pubkeys.
5. `cpmm_binary_state.py`: decodificador binário **NÃO VALIDADO contra layout oficial e contas reais**; offsets/comprimentos possivelmente incorretos.
6. `paper_evidence_gate.py`: bloqueio por disponibilidade temporal e distinção entre estimativa e quote observada.
7. `paper_evidence_replay.py`: filtro de ticks sem evidência; cutoff `as_of`; dois modos; avaliação de risco; entrada estrita `replay_with_required_risk`.
8. `paper_entry_risk_policy.py`: limites de exposição, perda diária, slippage, liquidez e emergência.
9. `cli.py`: opção experimental `smr paper-replay --strict-evidence evidence.json` apenas para ticks locais, incompatível com `--archive` até validação.
10. Testes unitários novos e documentação, inclusive `docs/SMR-CPMM-DEFERRED-VALIDATION.md` e `docs/SMR-PAPER-STRICT-EVIDENCE-CLI.md`.

## Situação da validação

**Nenhuma execução de GitHub Actions foi encontrada para os últimos commits durante esta sessão.**
Não afirmar que testes passaram. Inspecionar workflows, executar suíte completa e testes de integração no SHA efetivo.

## Prioridade de retomada para Codex

1. Inspecionar `git status`, branch, commits, diff da PR #64, workflows, dependências e testes; não sobrescrever mudanças existentes.
2. Auditar **primeiro** `cpmm_binary_state.py` contra fonte oficial versionada Raydium CPMM e fixtures mainnet. Os offsets anteriores podem estar errados; testes sintéticos não comprovam correção.
3. Executar `python -m compileall src tests` e suíte de testes; corrigir regressões.
4. Criar testes end-to-end do CLI `--strict-evidence`, cobrindo entrada aprovada, falta de evidência, perda diária, emergência, estimativa não observada e incompatibilidade com `--archive`.
5. Revisar segurança do wrapper: verificação declarativa não é prova criptográfica; não confiar em `evidence_verified` fornecido por operador; vincular quotes e snapshots ao RAW.
6. Conferir riscos de lookahead, precificação de posições, saídas e comparação dos modos.
7. Atualizar documentos de pendências com evidências reais (SHA e URLs do CI); não marcar bloqueios como resolvidos sem comprovação.
8. Planejar integração do fluxo de arquivos históricos somente após contrato de evidência autenticada.

## Regras de execução

- Não alterar `main` nem fazer merge sem revisão e autorização.
- Não enviar ordens financeiras reais.
- Manter duas modalidades: entrada imediata e entrada confirmada, ambas sob os mesmos bloqueios de segurança.
- Fechar um módulo por vez; separar implementado, testado e aprovado.
- Registrar no GitHub decisões, pendências, SHA, PR e resultados reproduzíveis.
- Não prometer execução contínua/autônoma sem um agente de nuvem efetivamente configurado.

## Instrução de retomada

> Leia este registro, o Registro Mestre do SMR e o registro de pendências CPMM. Compare com o estado atual das PRs e do GitHub Actions. Não presuma que commits recentes estão testados. Faça uma auditoria técnica do código novo, priorize correções de segurança e execute testes. Trabalhe em branch/PR, sem merge e sem operações financeiras reais. Atualize este registro ao final de cada etapa com SHA, evidência e próxima tarefa.

## Atualização posterior — 2026-11-20

- Commit `39ce9f8`: CLI strict replay agora preserva `market_at`, `bid`, `ask`, `bid_size` e `ask_size` do cenário, antes descartados na reconstrução de ticks.
- Tentativa de clone/testes em ambiente separado falhou por DNS (`Could not resolve host: github.com`). **Não representa falha dos testes de código e não valida a suíte.**
- Próxima ação: executar CI real e testes ponta a ponta do CLI, conferir `quote_id`/identidade de preço e risco de execução sobre dados declarativos não autenticados.

- Commit `02bd1b6`: acrescentados testes de integração CLI em `tests/test_paper_strict_cli.py` para ausência de evidência, ausência de risco e rejeição de `--archive`. **Ainda não executados**. Antes de encerrar este módulo, rodar suíte e corrigir regressões.

- Commits `2c7303b` e `289610a`: o caminho `replay_with_required_risk` agora rejeita histórico com `quote_id` ausente, lacuna de evidência ou ausência de snapshot de risco para tick elegível; testes CLI atualizados para esperar erro. O caminho opt-in `replay_with_evidence` permanece permissivo para testes exploratórios. **Pendente executar testes reais.**
- Atenção: rejeitar somente lacunas de presença não prova autenticidade do conteúdo nem rejeita toda evidência inválida antes do replay; avaliar preflight integral e vínculo RAW.

- Commits `a15fe34`, `5700d45`, `5212981`: o replay estrito executa preflight de todas as evidências antes dos modos imediato/confirmado; recusa histórico inteiro diante de evidência inválida, tardia ou estimativa não observada. Testes novos e teste anterior ajustado. **Não executar negociação real; CI pendente.**
- Lacuna crítica ainda aberta: metadados declarativos podem ser falsificados e o preço do tick não está criptograficamente vinculado à evidência RAW. Também falta garantir que validações de risco cobrem o notional real no momento do fill.

- Commit `bffcd34`: workflow `.github/workflows/smr-strict-paper.yml` criado para Python 3.12, compileall, testes de risco, replay de evidência e CLI protegido. **Não marcar como aprovado até confirmar execução e logs do Actions no SHA exato.**

- Commit `b6a5934`: novos testes end-to-end do CLI protegido cobrem entrada imediata aceita com metadados válidos e bloqueio por `emergency_halt`. **Ainda não executados.**
- Antes de usar em produção, revisar comportamento no instante do fill e autenticar origem/preço dos quotes. Não interpretar `evidence_verified` do operador como prova de origem.


### Comando Mestre 9 — motor de oportunidades (2026-11-20)

- Retomada verificada: PR #80 Draft em `8aaa7f2f168aee47957b87d9f88324596bb6511f`, base #66; PR #81 Draft em `f78c46b587f7edc49237a0ff8e7db52d45549161`, base #79; `main` preservada `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Criadas duas frentes isoladas no GitHub, sem agentes Codex independentes: PR #82 classificador explicável; PR #83 testes adversariais. Integração provisória em PR #84, branch `codex/smr-opportunity-classifier-integration`, base `codex/smr-wallet-consensus` (PR #80). **Não realizar merge na main**.
- Implementado `src/smart_money_radar/services/opportunity_classifier.py`: contratos `OpportunityEvidence` e `OpportunityClassification`, score heurístico discriminado, classificação `REJECTED/UNKNOWN/WATCH/PRIORITY` e ranking determinístico priorizando a classe antes do score. Bloqueios obrigatórios, manipulação, conflitos de sinais, cobertura/proveniência desconhecidas e liquidez/volume não positivos ficam fail-closed.
- Modos `immediate` e `confirmed` modelados somente como sinal informacional para simulação. `operational_authorized=False` em todas as saídas. As flags `VERIFIED` do chamador **não equivalem a autenticação independente**. Consenso da PR #80 segue `independence_verified=False`, portanto produção real do classificador permanece `UNKNOWN` até auditoria de controle conjunto de carteiras.
- Testes integrados: **749 aprovados, zero falhas e compileall** no código `4f55650cbdd9e116ee6a342f3edf9ba75304a700` (https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44773372107). Regressões cobrem risco alto com score alto, dados UNKNOWN, liquidez/volume zero, sinais MIXED, independência Sybil, determinismo, deduplicação e limites dos modos.
- Contrato do motor e limitações no documento `docs/SMR-OPPORTUNITY-CLASSIFICATION.md`.
- Solana Live real com Helius: **PENDENTE**, sem credenciais configuradas ou coleta real. Não contratar serviço nem operar fundos reais.
- Próximo módulo crítico: fornecer evidências temporalmente consistentes e autenticadas de segurança de token, liquidez/volume e controle conjunto de carteiras; conectar ao Launch Radar em pipeline offline sem look-ahead e testar dois modos no paper replay. A estimativa de conclusão global ainda é **não mensurável** sem pesos e gates aceitos.


### Comando Mestre 10 — evidências de segurança/liquidez e volume (2026-11-20)

- Estado inicial confirmado: PR #84 Draft, head `aeafa87d16e883e16a1a53abfcec40d391a1362c`, base #80; `main` preservada em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.
- Frentes isoladas, **0 agentes Codex independentes**: PR #85 para segurança de tokens e liquidez usando `validate_snapshot` CPMM; PR #86 para auditoria de volume por assinatura, tempos e SHA. Integração conjunta Draft **PR #87** em `codex/smr-market-evidence-integration`, base #84.
- Arquivos: `services/market_safety_liquidity.py`, `services/market_volume_audit.py`, `services/market_opportunity_bridge.py` e testes respectivos. Cada evidência carrega ID/fonte/slot/tempos/RAW/SHA, valida presença, hash, escopo e informação disponível antes do instante de classificação. Direitos mint/freeze, concentração e risco de retirada podem bloquear. Volume deduplicado por assinatura; contradições e concentração são risco explícito.
- Adaptador reconcilia os resultados conservadores com `OpportunityEvidence`, eliminando as flags de liquidez/volume/segurança pré-aprovadas do chamador. Ele não atesta de maneira independente RPC ou risco de tokens. `operational_authorized=False` permanece em ambos os modos. Regressões contra fonte divergente e ausência de provas.
- **CI validado**: commit de código `2295f583d15001a21e7275c39e006aaa32f240cc`, **777 testes aprovados, zero falhas, compileall**: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44775208257. Houve testes isolados nas PRs #85/#86, mas totais não devem ser somados. As integrações não estão na `main`.
- Detalhamento: `docs/SMR-MARKET-EVIDENCE.md`. Limitações honestas: RPC e relógio não autenticados externamente, distribuição real dos holders/Token-2022 e capacidade de retirada de liquidez não auditadas na rede; volume real e replay histórico ainda não validados. Solana Live real/Helius pendente, sem credenciais neste ambiente.
- **Próximo bloqueio técnico desbloqueado**: conector offline entre os recibos arquivados e o `market_volume_audit` com identidade de pool/fonte e first-publication, seguido de replays imediatos vs confirmados no mesmo cutoff. Não habilitar executor financeiro, não contratar Helius e não fazer merge em `main`.
- Percentual global ainda **não mensurável** até haver pesos e critérios de aceitação fim-a-fim.


### Comando Mestre 11 — replay point-in-time SQLite (2026-11-20)

- Estado inspecionado: PR #87 Draft em `a9e825df87b2ea10715100617fa89708fc87c761`, base #84; `main` imutável `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Documento de mercado na PR #87 consultado.
- Zero agentes Codex independentes; duas frentes isoladas: PR #88 (`codex/smr-sqlite-point-in-time-bridge`) e PR #89 (`codex/smr-replay-modes-tests`). Integração PR #90 em `codex/smr-sqlite-replay-integration`, base #87. Nenhum merge na main.
- Frente A: `services/sqlite_market_history.py` reutiliza `SQLiteEventStore.list_wallet_signal_receipts` e `integrity_check`; scoping carteira/programa/pool/mints, dedup e filtragem de `available_at <= cutoff`. `services/historical_opportunity_replay.py` reconstrói `HistoricalOpportunityFrame` no mesmo cutoff, preservando lacunas e classificação UNKNOWN, sem simular liquidez/volume/finalidade inexistentes na tabela.
- Frente B: `services/replay_mode_comparator.py` chama o motor `paper_replay.replay_paper` existente para os modos imediato e confirmado com mesmos ticks elegíveis e `PaperConfig` (fee/slippage/exposição). Testes de falta de quote, bloqueio de segurança, cutoff futuro, ordenação e determinismo. **Comparação exploratória** com quotes fornecidos pelo chamador, não prova de market quote observada.
- CI integrada **791 testes, zero falhas e compileall**, SHA de código `f6dfa66b10f7feef803d600e57f4b2c2309494e7`: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44776739674. Testes SQLite com `read_only=True` após reinício e `mark_processed` idempotente passaram. Não somar suítes de branches.
- Runbook `docs/SMR-SQLITE-HISTORICAL-REPLAY.md`. `swap_replay_archive` não atesta slot, finalized, fonte RPC RAW nem quote econômico; estes campos e PnL permanecem UNKNOWN. Helius real pendente; sem gastos ou operações reais.
- **Próximo trabalho desbloqueado:** integrar prova RAW signature/slot/tempo aos recibos imutáveis e quote observado com `replay_with_required_risk` já existente; comparar modos sem inventar preço/resultado. Progresso global não mensurável.


### Comando Mestre 12 — RAW e preços verificáveis (2026-11-20)

- Estado inicial inspecionado: PR #90 Draft, head `7527075d41dc46f8373525c4e192ae23dea0b09d`, base #87; `main` mantida `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Documento de continuidade lido.
- Zero agentes Codex independentes; duas frentes em branches isoladas: #91 (`codex/smr-raw-receipt-provenance`) para vínculo de recibo SQLite a transação local; #92 (`codex/smr-observed-quote-gate`) para preflight de quote. PR #93 é a integração em `codex/smr-raw-quote-evidence-integration`, base PR #90, sem merge da main.
- `receipt_raw_link.py` inspeciona `get_swap_bundle`, `get_raw_transaction`, `get_observation_metadata`, assinatura, programa, pool, slot, horário e hash canônico SHA-256; todas as evidências continuam UNKNOWN para autenticidade RPC/finalized. Não confundir JSON persistido com RAW bytes da rede.
- `observed_quote_gate.py` exige escopo pool, slot, fonte declarada, horários, hash, bid/ask, profundidade, volume, tarifas e slippage; retorna UNKNOWN/REJECTED diante de lacunas. Mesmo quote de teste com flags atestadas mantém `economics_supported=False` e `entry_allowed=False`, sem autorização de operação financeira.
- GitHub Actions comprovado no SHA de código `e4a2e1b20159473e74c8fe092323bc39d949bfb6`: **809 testes aprovados, zero falhas e compileall**, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44779992846. Não somar totais das branches.
- Especificação em `docs/SMR-RAW-QUOTES-REPLAY.md`. Solana Live real e Helius permanecem pendentes. Métricas PnL/ROI/drawdown confiáveis continuam indisponíveis. Progresso global não mensurável.
- Próxima tarefa crítica: ligação verificável de RAW original/finalized e cotação com origem autenticada, slot, pool, `quote_id`, first-publication e preflight estrito `replay_with_required_risk` já existente; comparar modos só depois de evidências suficientes.


### Comando Mestre 13 — cadeia de evidências e replay econômico estrito (2026-11-20)

- PR #93 conferida Draft, head `6919173a0a29ea010492d933f42efce560eb13e6`; `main` verificada sem mudanças no commit `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Continuidade anterior lida.
- Duas frentes em branches isoladas e **0 agentes Codex independentes**: PR #94 `codex/smr-evidence-chain-authentication` cria `services/evidence_chain.py` e testes para cadeia receipt RAW → assinatura/slot/pool/source → cotação/quote_id → cutoff, sem presumir autenticação. PR #95 `codex/smr-strict-economic-replay` cria `services/strict_economic_replay.py`, com gates de preço, quote_id, pool, duplicações, classification/risk/temporality e negação de PnL quando houver evidência não comprovada.
- Integração conjunta em **PR #96 Draft**, branch `codex/smr-evidence-economic-integration`, base PR #93; **CI integrada 827 testes aprovados, zero falhas e compileall** no commit `14fc06024669729fcd9c4a1358e84276c5338f03`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44784616016.
- A frente #95 isolada apresentou erro de importação `ModuleNotFoundError: ...evidence_chain` (CI isolada **não** aprovada): dependência entre contratos ficou resolvida na integração e os 827 testes integrados passaram. Não somar testes de branches distintas.
- Estado conservador: mesmo `LOCALLY_LINKED_UNATTESTED` deixa `provider_authenticated=False`, `finalized_attested=False`, `executable_price_verified=False`; até existir fonte externa adequada, `strict_economic_replay` resulta `BLOCKED`, não calcula PnL/drawdown com preços inventados, não autoriza operações.
- Próximo desbloqueio: fonte independente imutável de RAW/finalized, prova de quote vinculada a slot/pool/quote_id/time available, avaliação econômica de preço executável com taxas/slippage e integração com replay protegido preexistente. Sem rede Helius autorizada, Solana Live real permanece pendente. `main` não foi alterada; nada pago ou negociado.
- Progresso global não mensurável sem critérios e pesos de aceitação acordados.


### Comando Mestre 14 — RPC público Solana e cotações CPMM (2026-11-20)

- Inspeção confirmou PR #96 Draft, head `0aab5ca1bceff41b774f7f6ceb99fd41f3c88caf`; `main` preservada em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Continuidade e contratos preexistentes inspecionados.
- Duas frentes isoladas, **0 agentes Codex independentes**: PR #97 (`codex/smr-public-rpc-verification`) e PR #98 (`codex/smr-cpmm-quote-evidence`). Integração Draft **PR #99** em `codex/smr-onchain-cpmm-verification-integration`, base PR #96.
- Frente A criou `services/solana_rpc_verification.py` e `services/solana_public_rpc_read.py`. Reutiliza validação Base58 do `RpcFixtureCollector`. Apenas consulta `getTransaction` com compromisso `finalized` solicitado, mediante opt-in `enabled=True`, com limite de uma requisição por chamada e timeout. Preserva RAW, SHA-256, slot, fonte, hostname, observed_at e available_at. Detecta respostas nulas, conflitos de assinatura/slot/fonte, RPC indisponível. `RPC_CONSISTENT_UNATTESTED` nunca equivale a finalized criptograficamente atestado.
- Frente B criou `services/cpmm_theoretical_quote.py`. Reutiliza `cpmm_reserve_snapshot.validate_snapshot` e `cpmm_reserve_estimator.estimate_exact_input`; recebe snapshot, pool, slot, mints, valor de entrada, `quote_id`, cutoff, e checagem de proveniência de fee. Saída `THEORETICAL_ONLY` / `BLOCKED`, sempre `observed_market_quote=False`, `executable_price_verified=False`, nunca liberada como resultado econômico.
- **CI integrada aprovada** no commit de código `e9f9f4c82527d88a751d0be0e751d428bc660915`: **849 testes, zero falhas, compileall**, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44786874691. Testes HTTP foram simulados com mocks, não evidenciam execução RPC ao vivo.
- **Transações efetivamente verificadas na rede neste ciclo: 0**. Nenhuma coleta real de rede executada. Helius/Solana Live real pendente. Nenhum serviço pago, nenhuma carteira criada, nenhum trade, `main` imutável.
- Próximo passo desbloqueado: obter uma pequena transação finalized em RPC público com captura persistente de RAW, vincular identidade e slot contra RPC separado quando autorizado; preparar snapshot real de PoolState/AmmConfig/vault no mesmo slot com taxa verificada, conservando estimativa não executável. Replay econômico estrito permanece bloqueado sem proveniência suficiente. Progresso global ainda não mensurável.


### Comando Mestre 15 — primeira captura real Solana CPMM (2026-11-20)

- Estado inicial verificado: PR #99 Draft, head `31973c3d015b376ab1759486fe1046d95b349c16`, base PR #96; continuidade lida e `main` sem mudanças `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Uma frente executora; sem agentes Codex independentes.
- **Primeira consulta real**: workflow isolado https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44792506494 realizou **uma requisição `getTransaction`** no endpoint gratuito `https://api.mainnet-beta.solana.com` solicitando `finalized` para assinatura `23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM`. Recebeu slot **471039497**, com `meta.err=null`, em 2026-11-20 **18:24:54.797654 UTC**; `available_at` **18:24:55.131940 UTC**. Evento `blockTime` 2026-11-18 18:45:26 UTC.
- RAW original (7083 bytes) e manifesto preservados inicialmente em Actions artifact #14657530899, SHA-256 `3325222e2c33f6735432f12065b348b4657ae9cfc2c1141061c7c78639724dad`. Segundo workflow https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44793176514 **não fez novas requisições RPC**; baixou o mesmo artifact, checou SHA/assinatura/slot/pool/programa/vaults e gravou os bytes originais em `data/evidence/mainnet/2026-11-20/` na branch `codex/smr-first-solana-proof` (PR **#100 Draft**, base PR #99).
- Instrução CPMM #3 decodificada: programa `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`, PoolState `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`, config `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`, vault HIGH `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`, vault WSOL `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`. Deltas dos vaults em meta pre/post: +19.727,477255 HIGH e -0,098099917 WSOL; taxa de rede `meta.fee=27000` lamports, **não taxa CPMM verificada**.
- Regressão com RAW observado (não fixture sintetizada): **859 testes aprovados, zero falhas, compileall** no commit `2690625d1ade59abff4e07e884aca7d41e2a6cbf`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44793416811. Não somar com 849 anteriores. 10 novos testes fixam RAW hash/identidades/tempos/deltas/bloqueios. Documento completo: `docs/SMR-FIRST-SOLANA-MAINNET-PROOF.md`.
- **Limites:** `RPC_CONSISTENT_UNATTESTED` — finalized solicitado ao único RPC e corroborado por explorador público, não autenticado independentemente; presença dos vaults na instrução e saldos pre/post não provam PoolState/AmmConfig/vault ownership nem **reservas efetivas** no slot. Não há snapshot histórico completo de taxas e reservas. `strict_economic_replay`, cotações executáveis e retornos permanecem bloqueados. **Não usar um evento de 18/11 como informação disponível em 18/11:** somente observação em 20/11 foi comprovada.
- Próxima prioridade: conferir a mesma assinatura e slot por segundo RPC público com 1 requisição limitada (se autorizado/viável) e obter PoolState/AmmConfig/vault no slot histórico antes de estimar quote e integrar replay. Não consultar reservas atuais como históricas, não contratar serviço, não executar trade, não fazer merge na main. Progresso global não mensurável.
