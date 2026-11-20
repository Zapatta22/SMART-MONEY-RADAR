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
