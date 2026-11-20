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

## Retomada e validação da PR #64

A revisão começou na branch `feat/cpmm-reserve-estimator-audit`, commit
`1ded0b5`, baseada em `codex/smr-paper-pool-scope@7599bcd` (PR #63).
O workflow estrito passou no head remoto e a suíte local teve 725 testes.
O workflow geral também passou no commit de código imediatamente anterior.
[CI estrito](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44654045991) ·
[CI geral](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44654024991)

A branch `codex/smr-pr64-validation` reúne a revisão da PR #64. A análise
binária confere o layout CPMM com código upstream fixado e uma captura
mainnet finalizada. O replay protegido verifica o SHA-256 e os campos da
cotação original, respeita o cutoff antes de processar os dados posteriores
e reavalia a entrada no fill dos dois modos. A validação usa bytes de
fixture e mantém como pendente a autenticação externa da origem e do
relógio. O commit de código validado é `072d0920f534d586ccec47c3c6010359ce89b712`.
Passaram 743 testes locais, `compileall` e `git diff --check`. O comando
`smr cpmm-snapshot-audit` também foi executado na captura do slot
`471539976`. O workflow geral e o estrito passaram no mesmo commit.
[PR #67](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/67) ·
[CI geral](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674207937) ·
[CI estrito](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674215591)

Duas frentes independentes partiram do head original da #64. A PR #65
mostra checkpoints e pendências no painel local, com 727 testes locais.
A PR #66 agrega evidências direcionais por carteira, pool e assinaturas
distintas, com 728 testes locais. Ranking, concentração, alertas de
lançamentos e uso ao vivo ainda precisam de implementação e validação.
[Painel #65](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/65) ·
[Smart Money #66](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/66)

### Próxima etapa da cadeia crítica

Integrar a captura de cotações com proveniência externa verificável ao
replay protegido e comparar dados contemporâneos do mesmo pool CPMM.
É necessário um intervalo com swaps finalizados, cotações bid/ask,
profundidade e horários de disponibilidade. Os snapshots de reserva
continuam classificados como estimativas. A validação prospectiva e a aceitação operacional seguem pendentes.
A execução financeira permanece desabilitada. A `main` segue em
`5060bc65ddf181a4736fdb662c44c3fec0dd7259`.


### Marco verificável — cursor durável do Launch Radar (PR #70, 2026-11-20)

- Branch de trabalho: `codex/smr-launch-stream-cursor`, derivada de `codex/smr-launch-journal@493e7b4` (PR #69). `main` intocada; nenhuma PR mesclada.
- Código `d4d3456` acrescenta ao `SQLiteEventStore.archive_cpmm_launches` um cursor opcional por `source_id` e `first_sequence`. RAW de todas as entregas, inclusive sem Initialize, identidades CPMM e cursor são persistidos numa única transação SQLite.
- Testes `3cebcab2c1cd021ecd45abc5a94736ab8371ea53` cobrem reabertura, repetição idempotente, sequências ausentes, replays conflitantes, isolamento por origem, rollback forçado e validação de parâmetros.
- GitHub Actions **aprovado** para o commit com código e testes `3cebcab`: **756 testes**, `compileall` e instalação Python 3.12 bem-sucedidos. Log: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44757088354. Documentação posterior não altera código.
- Contrato e ressalvas: `docs/SMR-LAUNCH-STREAM-CURSOR.md`. A sequência é criada pelo consumidor e **não** é slot/seq nativa da Solana. Cobertura anterior ao primeiro evento: `UNKNOWN`. Nem provedor nem horário estão autenticados.
- Estado: **persistência de cursor offline validada em CI; consumidor online e reconciliação de lacunas remotas pendentes**.
- Próxima tarefa independente: criar/adaptar consumidor Solana de leitura para alimentar lotes RAW, armazenar origem estável e fazer backfill e reconexão fail-closed; testar atrasos e eventos perdidos. Em paralelo, a simulação continua bloqueada até cotações com proveniência externa e swaps contemporâneos do mesmo pool.
- Negociação real desabilitada; nenhum merge ou contratação autorizados. Não inventar percentual global sem critérios de aceite.


### Distribuição econômica e marco Solana Launch Backfill — 2026-11-20

Duas frentes de execução foram representadas em branches isoladas, sem ativação de agentes Codex separados:
1. **Código** `codex/smr-launch-live-backfill`: `src/smart_money_radar/services/launch_live_backfill.py` e cursor RPC em `src/smart_money_radar/storage/event_store.py`, baseados na PR #70.
2. **Testes de segurança** `codex/smr-launch-live-safety-tests`: `tests/test_launch_live_safety.py` sem alterar a implementação.
3. A branch temporária `codex/smr-launch-live-integration` combina as duas frentes e acrescenta métodos Helius somente leitura com commitment `finalized` e comando `smr launch-backfill` protegido por `SMR_ALLOW_NETWORK` e `HELIUS_API_KEY`.

**Validação real**: GitHub Actions `SMR tests`, head de código `e62266c2165c936863aa7acdc71872bc0b810ecb`, **762 testes aprovados, zero falhas, compileall aprovado**: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44759245353. Os seis testes independentes de backfill, interrupção e rollback passaram. Os 756 testes anteriores também foram preservados.

**Limitações bloqueantes**: a implementação cobre apenas endereços Solana expressamente monitorados e fornece recuperação por RPC e persistência, mas **não executou sessões reais prolongadas de rede**, não oferece cobertura global de todos os launches, nem valida independentemente origem do provedor, relógio e finalização além da declaração RPC. Ainda falta integração WebSocket para atualização reativa, avaliação de lacunas entre assinaturas, captura confiável de RAW da resposta HTTP e testes de falha real/latência. `source_id` e sequência são locais ao consumidor. A primeira varredura é um baseline `UNKNOWN`; nunca declarar cobertura completa.

**Próximo módulo prioritário**: WebSocket de notificação com reconexão e backfill obrigatório após restabelecer conexão, mantendo origem estável e bloqueio fail-closed. Em paralelo independente, auditoria de proveniência de RPC e fixtures reais finalizadas. Não mesclar `main`, contratar serviços nem habilitar negociações.


### Comando Mestre 6 — Solana WebSocket Live, ciclo 2026-11-20

- Estado de retomada conferido: PR #70 a #73 Draft, base `codex/smr-launch-live-integration@baadb99`. CI da #73 confirmou 762 testes; `main` não foi alterada.
- Duas frentes isoladas, **0 agentes Codex independentes**: PR #74 com módulo `launch_live_monitor.py`, PR #75 com testes `test_launch_live_monitor.py`. Os testes foram integrados em `codex/smr-launch-websocket-integration`; o comando `smr launch-live` foi adicionado ao CLI.
- A estratégia WebSocket usa `logsSubscribe` em `confirmed` somente para ativar reconciliação; checkpoint e evidências de lançamentos persistem exclusivamente a partir de RPC `finalized`. Cada sessão executa backfill antes de processar notificações; reconexões usam backoff com jitter; silêncio desencadeia verificação periódica e nova assinatura. Instrumentadas métricas de sessões, notificações, recuperações, perdas e tempo de reconciliação; cobertura permanece `UNKNOWN`.
- Primeiro workflow integrado falhou em um teste com fixture incorreta para o silêncio pós-ACK; fixture corrigida e suíte novamente executada. **CI aprovado no SHA de código `70697064780f7a738b5e02f439dcb64d9c988097`: 769 testes, zero falhas, compileall**: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44761362086.
- Matriz de módulos e critérios de aceite em `docs/SMR-LAUNCH-LIVE-ACCEPTANCE.md`. Ausência de critérios globais ponderados: percentual de progresso ainda não mensurável.
- **Não houve uso de rede RPC/WebSocket real, credenciais ou serviços pagos nesta sessão.** A capacidade de monitorar endereços com mock/fixtures não prova cobertura em tempo real nem origem autenticada. Continuidade Solana Live é **PARCIAL**, aguardando validação com provedor autorizado, reconciliação de reorgs, paginação hostil/429 e medição real de latência. Não habilitar operações financeiras.
- Próxima tarefa: prova de integração com fonte real e diagnósticos de cobertura e proveniência, antes de classificar o monitor como operacionalmente concluído. Não fazer merge em main.


### Comando Mestre 7 — preparação de validação Solana real (2026-11-20)

- Inspecionado o estado efetivo da PR #76 `codex/smr-launch-websocket-integration@6b57762656702fccd165a0db660dcaea6514583d`, sem merge; 769 testes anteriores confirmados.
- Ambiente atual sem `HELIUS_API_KEY` nem `SMR_ALLOW_NETWORK` configurados. **NENHUMA CONSULTA A RPC/WS REAL NESTA SESSÃO**. Não usar dados das fixtures como observações reais.
- Duas frentes isoladas e coordenadas diretamente pelo GitHub, **0 agentes Codex independentes**: PR #77 implementação de métricas e reforços de backfill, PR #78 testes adversariais independentes. Integração Draft na PR #79, branch `codex/smr-real-validation-integration`.
- Alterações: correspondência assinatura hint (confirmed)→RPC finalized, cronômetros monotônicos e percentis somente com >=20 amostras; contadores 429, duplicatas, hints pendentes e coalescing; barreiras contra páginas RPC duplicadas/fora de ordem ou status não finalizados; relatório JSON atômico sem credenciais e sessão controlada `smr launch-live --duration-seconds N --metrics-json caminho.json`.
- RPC de alto volume: padrão CLI de `--min-reconcile-interval-seconds 1`; notificações agregadas não são classificadas como finalizadas, e qualquer lacuna não recuperável mantém cobertura `UNKNOWN`.
- **Código validado** no commit `4dc388f05da670a114b8b031f34c5737e9e5bb47`: GitHub Actions geral, **786 testes aprovados, zero falhas, compileall aprovado** https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44764651003. Workflow estrito também aprovado: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44764668309. Comandos reais de captura não foram executados.
- Procedimento reproduzível: `docs/SMR-SOLANA-LIVE-REAL-VALIDATION.md`; matriz de aceite: `docs/SMR-LAUNCH-LIVE-ACCEPTANCE.md`.
- Métricas de rede real: eventos=0 coletados nesta sessão; latência p95=**não medida**; lacunas externas=**não avaliadas**; proveniência externa=**não atestada**. Não confundir zero eventos observados com inexistência de eventos na Solana.
- **Próxima ação bloqueante**: ambiente sob controle do operador com autorização explícita e credenciais adequadas, captura limitada de um endereço público e comparação de WebSocket com backfill finalized. Testar desconexões, 429 reais, custo, reinício, slots e integridade. Após isso decidir se escala para o programa CPMM inteiro.
- Estado: Solana Live **parcial**, operacionalmente não aprovado. Continuar sem ativar trading, sem contratar serviços e sem merge na `main`. Progresso global sem percentuais ponderados de aceitação; **não mensurável**.
