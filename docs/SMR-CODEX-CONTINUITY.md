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

### Primeira entrega offline do Launch Radar

A branch `codex/smr-launch-radar-cpmm`, código `c388515`, parte da
revisão #67. O comando `smr launch-scan` reconheceu a inicialização CPMM
na captura finalizada do slot `471578450` e devolveu uma única ocorrência
quando o mesmo arquivo foi passado duas vezes. Os 749 testes locais e
o workflow geral passaram. [PR #68](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/68) ·
[CI da #68](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674612791)

A branch local de integração `codex/smr-pr64-fronts-integration` em
`74ddb28` combina código das PRs #65, #66, #67 e #68. A suíte combinada
passou com 754 testes, compilação e `git diff --check`. As quatro PRs
permanecem separadas para revisão. A próxima etapa offline de Launch Radar
é persistir a identidade e o RAW de inicializações ao consumir o fluxo
Solana, com deduplicação durável e recuperação testada. Detecção de liquidez
e alertas operacionais permanecem pendentes.

A revisão da #64 reaproveita o decoder e o estimador já existentes. O
protótipo `codex/smr-cpmm-quote-model@6ce93e0` ficou isolado devido à
sobreposição. A checagem pelo CLI da #67 também passou no snapshot público
do slot `471602593`, SHA-256 `33ec5fdb0f79632a1d822667e11ce15e71a053f85714e60ddc073cac9ee84493`.
Essas duas leituras verificam estruturas em slots distintos e ainda não
formam uma série de cotações observadas.

### Arquivo durável de lançamentos

A PR #69, branch `codex/smr-launch-journal`, código `493e7b4`, acrescenta
`launch-scan --journal`. A persistência preserva os bytes RAW, a relação
com a identidade do pool e conflitos. Os testes forçaram falha de gravação,
conferiram rollback e repetiram a varredura após reabrir o banco. Passaram
751 testes na branch, e o CI geral foi aprovado.
[PR #69](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/69) ·
[CI geral](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674879174)

A integração local das cinco PRs desta rodada está em
`codex/smr-pr64-fronts-integration@e4fa4b6` e passou com 756 testes,
`compileall` e `git diff --check`. O próximo passo offline do Launch
Radar é conectar o journal ao consumidor Solana, com cursor próprio e
replay retomável. A próxima validação da Simulação depende de uma série
contemporânea, auditável, com cotações de origem verificável e swaps
finalizados do mesmo pool. Nenhuma PR foi mesclada.


### Auditoria de retomada — 2026-11-20, sessão GitHub

- A PR #64 permanece Draft em `feat/cpmm-reserve-estimator-audit@1ded0b58aad4b361938aff658d0e4f2c8048f8e8`, com base `codex/smr-paper-pool-scope` (PR #63). O CI estrito do head foi aprovado: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44654045991.
- A correção da cadeia crítica já foi desenvolvida na PR #67, `codex/smr-pr64-validation@53af336f115901dd29fb35759ce189973eb66802`. CI geral, CI estrito e benchmark estão aprovados nesse SHA: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674972597, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674972494, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674972617. Isso comprova o CI que foi executado, não autentica fonte externa das cotações.
- Revisão do código da #67: `verify_paper_quote_tick` confronta SHA-256 e valores RAW, porém RAW e hash são fornecidos pelo mesmo bundle; continuam ausentes a origem externa autenticada e o relógio confiável. `_fill_risk_rejection` reavalia notional, liquidez, slippage e perda no fill nos dois modos; atenção especial a regressões de estados e eventos históricos.
- Frentes independentes: painel #65, Smart Money #66, detecção offline de launch #68 e journal persistente #69. A PR #69 declarou 751 testes locais e o CI geral passou no SHA `493e7b459befdf23a7441a6e4c8297fe0ed55e23`: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44674879174.
- O registro anterior cita integração local `codex/smr-pr64-fronts-integration@e4fa4b6`, mas essa branch não apareceu na lista remota consultada. Portanto os 756 testes reportados são evidência declarada de ambiente local, **não** uma validação de branch de integração acessível no remoto. Não afirmar cadeia integrada nem iniciar merge.
- **Próxima ação bloqueante de simulação:** captar série contemporânea e independente de cotação bid/ask, profundidade, horário de observação e disponibilidade, mais swaps finalizados do mesmo pool CPMM; estabelecer origem, hashes externos e política de confiança; reproduzir comparação e taxas em fixtures públicas. Não promover `MODEL_ESTIMATE_NOT_OBSERVED` a quote executável.
- **Próxima ação independente de Launch Radar:** conectar consumidor Solana ao journal persistente com cursor e replay retomável, idempotência, conflitos, backfill e testes de interrupção; branch isolada derivada da #69, sem alterar `main`.
- Esta atualização é **documental**, não executou nova suíte local e não equivale a aprovação de integração. Nenhuma negociação real autorizada, nenhum merge.
