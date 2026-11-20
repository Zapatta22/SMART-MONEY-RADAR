# SMART MONEY RADAR — COMANDO MESTRE 28

**Data da auditoria:** 2026-11-20 (UTC). **Branch:** `codex/smr-cpmm-ws-integrated-recovery`; PR #111 Draft, sem merge; `main` `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

## 1. Captura live: autorização operacional

O workflow `.github/workflows/smr-cm27-live-gate.yml` foi inspecionado na PR #111. É **workflow_dispatch** de acionamento manual, input `approve_read_only=READ_ONLY_BOUNDED_CM27`. A integração GitHub acessível nesta execução permite leitura, consulta de CI, escrita de arquivos e PRs, mas **não disponibiliza operação para dispatch de workflows**. A API `mcp__GitHub__fetch` suporta GET e não substitui disparo POST; não executar contorno por commits acionados por push ou credenciais externas. **Workflow executado: NÃO**; **run_id: não existe**; **quatro ACKs novos: não medidos**; **baseline novo: não medido**; **notificações reais novas: zero comprovadas**; **reconexão real nova: não demonstrada**. Última evidência live anterior: slot `471887787`, 4 ACKs, zero notificações. `coverage=UNKNOWN` e execução financeira inativa.

O procedimento disponível para quem tem permissão no GitHub é GitHub > Actions > **SMR CM27 read-only bounded Solana WebSocket live gate** > Run workflow > selecionar o branch `codex/smr-cpmm-ws-integrated-recovery` > preencher `READ_ONLY_BOUNDED_CM27`. **Atenção:** o workflow novo ainda está apenas numa branch Draft, não na default branch `main`. O GitHub pode não exibi-lo para workflow_dispatch até que um workflow equivalente esteja registrado na default branch; não realizar merge ou mudança da `main` sem revisão. Se o workflow não aparecer, registrar o bloqueio; não induzir consultas públicas por outro gatilho.

Limites programados: `MAX_SECONDS=75`, `MAX_FRAMES=80`, quatro contas CPMM, orçamento de baseline de até `1 + max_reconnects` (no máximo duas chamadas), uma reconexão, job 3 minutos, RAW/SQLite em artifact de 7 dias. Network opt-in obrigatório; sem contratos financeiros ou chaves privadas.

## 2. Evidência e classificação de captura

No runner reutilizado foram adicionados os campos auditáveis: `four_subscriptions_confirmed`, `baseline_snapshot_confirmed`, `transport_reconnected_after_natural_disconnect`, `recovery_snapshot_confirmed`, `observed_notifications`, `stable_baseline_observed`, `recovery_live_proven` e `live_real_reconnection_observed`. O script preserva manifestos nas categorias `A_STABLE_SUBSCRIPTIONS_BASELINE`, `B_NATURAL_DISCONNECTION_RECOVERED`, `C_UNVALIDATED_OR_RECOVERY_FAILURE` e `D_REAL_NOTIFICATION`. A categoria D indica apenas ocorrência de notificação, não comprova por si só recuperação; inspecionar também os outros campos. Os testes são exclusivamente offline. `coverage` sempre `UNKNOWN`; nenhum campo promove autorização financeira. Testar critérios de ACK parcial, RPC indisponível e falha de segunda inscrição.

**CI validada:** 1.052 testes e compilação aprovados, commit `d6e49886e9eaac5e85b81e819442873db4574201`, GitHub Actions https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44840348051. Ajuste posterior do manifesto para eliminar declaração redundante em commit `f4af94cadc99192908b94691e31c4cf95e2d4e19` (mudança sem impacto lógico; verificar novo run quando existir).

## 3. Inventário real do repositório e preservação integral

A API do GitHub retornou **87 PRs abertas**. Não são 87 módulos independentes: as PRs #112 até #43 incluem grande cadeia linear com braços e bases intermédias; **#112 não substitui automaticamente #111**: são branches divergentes, e requerem comparação de diff e CI para evitar regressão. Bases #4/#5/#11 chegam a `main` e muitas dependem de desenvolvimento anterior não mergeado. Evitar merge na `main`, fechamento em lote e reimplementação.

Implementações localizadas no branch principal de trabalho (presença de código, NÃO homologação conjunta):

| Bloco | Evidência de implementação | Gate de integração |
|---|---|---|
| Captura Smart Money/Carteiras | `wallet_monitor.py`, `wallet_signals.py`, `wallet_consensus.py` | Validar proveniência e autonomia entre carteiras; sem duplicar sinais |
| Launch Radar independente | PRs #68–#76, `launch_*` e testes associados em branches | Validar detector, journal, backfill e checkpoint separados do Smart Money |
| RAW e histórico Solana | `geyser_raw_store.py`, `event_store.py`, `sqlite_market_history.py`, PRs #43–#58 e #100–#112 | Confirmar hash, origem, stream, cutoff, migração e cobertura UNKNOWN |
| Segurança, liquidez, volume | `market_safety_liquidity.py`, `market_volume_audit.py`, `market_opportunity_bridge.py` | Provar dados autenticados/point-in-time antes de sinal elegível |
| Classificador | `opportunity_classifier.py`, `wallet_consensus.py` | Testar `REJECTED/UNKNOWN/WATCH/PRIORITY` sem permissão de trade |
| Gestão de risco/simulação | `paper_entry_risk_policy.py`, `strict_economic_replay.py`, `historical_opportunity_replay.py` | Exigir cadeia completa, evitar lookahead, comparar immediate/confirmed |
| Painel celular | `dashboard_http.py`, `dashboard_read.py`, PR #65 | Garantir somente leitura, lacunas e estado explícitos |
| Execução futura / 24h | Escopo preservado no roadmap, NÃO operação real nesta versão | Projeto separado com autorização explícita, guarda-chaves, kill switch e teste longo |

**Dependência crítica identificada:** o `strict_economic_replay.py` bloqueia corretamente porque nenhuma evidência local produz atestação independente de origem/finalização/quote executável. `historical_opportunity_replay.py` deixa cobertura UNKNOWN e não afirma performance econômica. Não contornar esses bloqueios para atingir uma data arbitrária; primeira integração precisa provar a cadeia de evidência.

## 4. Plano de integração controlada, sem perda de arquitetura

1. **Estabilizar base da PR #111**: gate offline 27 permanece concluído; validar classificação CM28 e preservar SQLite v5. Não incorporar a PR #112 apenas pelo número. Sem merge.
2. **Mapear dependências com base/head reais**: consolidar evolução linear desde #4/#5 e branches de trabalho; registrar PRs laterais que demandam comparação, e agrupá-las por código, testes e evidências, não fechar sem confirmação.
3. **Conectar dados → sinais → segurança** por um único envelope `(source_id, signature, slot, pool, transaction_id, available_at, raw_sha256)` imutável, usando contratos existentes; falhar fechado se duas fontes forem inconciliáveis ou se houver dados futuros.
4. **Risco → replay somente paper**: testar tanto entrada imediata quanto confirmada, spread bid/ask independente, posição, custos, slippage e proteção contra lookahead. A ausência de quote executável mantém `BLOCKED`.
5. **Painel Android**: consumir estado de coleta, lacunas, sinais `UNKNOWN` e simulação somente leitura; sem segredos, ordens ou falsa cobertura.
6. **Homologações separadas**: Solana live curta; testes de endurance/queda física no dispositivo; integração funcional de ambos os radares; simulação sem lucro inventado; só depois avaliação de execução financeira futura.

## 5. Execução e orçamento

Um executor, **zero auxiliares**: as tarefas de auditoria e mudança do mesmo runner não justificam paralelismo. A economia de créditos não foi mensurada. Nenhuma captura Solana, VPS, serviço pago, chave privada, operação financeira, merge ou modificação de `main`. A meta 14–21 dias é um objetivo para primeira integração e **não autoriza omitir funcionalidades futuras** nem constitui cronograma comprovado.

**Próxima tarefa:** obter disparo oficial do workflow (bloqueado nesta conexão) e arquivar artifact; em paralelo seguro, validar mapeamento de envelopes e auditabilidade `RAW → evento → consenso → classificação → risco → replay bloqueado → painel`, usando as funções existentes sem criar nova PR. Revisitar a PR #112 divergente antes de qualquer consolidação.
