# SMART MONEY RADAR — COMANDO MESTRE 27: RECUPERAÇÃO PERSISTENTE WEBSOCKET

Data: 2026-11-20. PR [#111](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/111), branch `codex/smr-cpmm-ws-integrated-recovery` sobre PR #110 (base `codex/smr-cpmm-ws-resilience`). `main` preservada, nenhum merge. Uma frente executora, zero agentes auxiliares, sem rede Solana neste ciclo, sem VPS, custos, chaves privadas ou operações financeiras.

## Base auditada
- Estado anterior: PR #111 Draft, 1.030 testes aprovados, código `88de2f6`, continuidade `c9ca5f9`, controlador conectado ao loop live, uma reconexão no máximo, 4 contas CPMM; último baseline **real** conhecido no slot 471887787 e **nenhuma** notificação live; recuperação live não provada.
- Reutilizados `CpmmRecoveryRunner`, `BoundedCpmmRecovery`, `PublicCpmmWsSession`, `SQLiteGeyserRawStore` e o decodificador de baseline. Nenhum store novo foi criado.

## Melhorias implementadas na PR #111
1. `recover_incomplete_capture_sessions(source_id=...)` no SQLite existente: identifica sessões iniciadas sem `finished_at`, e domínios RAW órfãos em caso de interrupção entre registro do stream e abertura da sessão; persiste `process_interrupted_unknown` com contagem dos frames e preserva os bytes originais. É idempotente.
2. O runner recupera essas identidades no início sem reabri-las, registra `recovered_incomplete_session_ids`, cria nova sessão e domínio UUID e mantém `coverage=UNKNOWN`.
3. Após os quatro ACKs, request RPC é persistido no journal da sessão; a resposta RPC, quando obtida dentro de uma janela controlada, também é arquivada no domínio de origem **antes** de encerrar a sessão desconectada. Um socket já desconectado nunca autoriza promoção do baseline, mesmo havendo bytes íntegros.
4. Timeout e cancelamento impedem promoção e não aguardam indefinidamente a chamada tardia (até 250 ms após queda de WebSocket, limitado pelo prazo global). Respostas indisponíveis ou descartadas por cancelamento **não são alegadas como RAW capturado**.
5. Erros de RPC e de inscrição são classificados separadamente, e falhas de persistência bloqueiam nova tentativa. Deadline global também é aplicado à avaliação do baseline. O resultado não atesta ordem global, assinaturas, `write_version` ou cobertura completa.
6. A inserção do frame e o checkpoint local permanecem vinculados pela transação SQLite existente; idempotência e detecção de SHA-256 continuam responsabilidade do store reaproveitado. Checkpoint local comprova só frames arquivados, nunca a continuidade da rede.

## Evidências de teste
- CI final **1.043 testes, zero falhas**, Python compilation aprovada, commit de código `f2187d42ee42e076426b648352cb6af15dde2f4a`: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44836760223.
- Testes novos de reinício SQLite, RAW arquivado após resposta tardia, isolamento de duas sessões, falha/timeout RPC, domínio órfão, prazo global e manutenção de `UNKNOWN`, usando exclusivamente transportes sintéticos.
- Testes adversariais específicos confirmam rejeição de slot RPC regressivo, dados RPC incompletos, rollback RAW/ checkpoint na mesma transação SQLite sob falha injetada e colisão SHA-256 sem avanço indevido. Não houve consulta RPC/WebSocket real nesta etapa.

## Pendências que NÃO foram promovidas a conclusão
- **Reconexão live demonstrada: NÃO.** Último baseline real continua slot 471887787; não inventar novas assinaturas, slots, notificações ou atualização CPMM.
- O rollback SQLite sob falha injetada já foi testado; ainda não houve teste de queda física do dispositivo nem SIGKILL em todas as fases. Ausentes prova live de sequência contínua e backfill de lacunas. Regressão de slot e baseline incompleto foram testados offline com resposta sintética, não com prova real de rede.
- `coverage=UNKNOWN`; execução financeira permanece desautorizada. A API de leitura/gravação de sessão deve ser usada por **um** capturador por `source_id` para evitar disputa entre processos; exclusividade multiprocesso não foi implementada.

## Próximo gate
Concluir a auditoria de concorrência multiprocesso e interrupção do processo nos pontos ainda não simulados; revisar e consolidar PRs Draft por dependência. Depois, avaliar uma única sessão Solana real, curta e auditável, sem forçar desconexões na infraestrutura pública. Não executar compras ou vendas, não efetuar merge automático.


## Comando Mestre 27 — encerramento do gate OFFLINE em 2026-11-20

- PR #111 Draft, mesmo branch, sem merge. Último código validado `24e967ddb231315750ce69e4ba8c6685accf0e19`; CI integrada **1.049 testes, zero falhas**, Python compilation OK: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44838111116. Um executor, zero agentes auxiliares, sem chamadas Solana live nesta fase.
- SQLite Geyser RAW schema **v5**: `geyser_capture_source_leases` no próprio store existente; reivindicação exclusiva e recuperação de sessões interrompidas em uma transação; detecção de dupla captura pelo mesmo `source_id`; recuperação após morte de processo Linux somente com prova local `/proc/PID/stat` e tick de início contra reutilização de PID. Sem prova inequívoca, bloqueia nova captura. Migração v3/v4 preservada.
- Suite de cenários offline com journal reaberto confirma integridade SQLite, RAW durável antes do checkpoint, rollback atômico ao falhar checkpoint e ao falhar recuperação, replays idempotentes, conflitos SHA-256, escopo e sessão novos, tratamento de RPC tardio/timeout/cancelamento, slot regressivo e baseline incompleto, concorrência, encerramento do proprietário local. `coverage=UNKNOWN` e execução financeira inativa.
- **Conclusão offline: SIM, sob os critérios de teste definidos; não equivale à homologação live, recuperação após desligamento físico testada ou operação 24/7.** Nota: o teste de processo encerrado é local controlado; não foi comprovado SIGKILL físico ou portabilidade de /proc para Android.
- **Homologação live: NÃO.** Nenhuma nova sessão pública Solana após baseline real conhecido no slot 471887787 (4 ACKs, 0 notificações). A nova execução live existe apenas como workflow opt-in `.github/workflows/smr-cm27-live-gate.yml`, acionamento manual com `READ_ONLY_BOUNDED_CM27`, prazo 75 s, até duas chamadas de baseline nas duas sessões, quatro contas, 80 frames, job 3 min, artifact RAW + SQLite. Nenhuma captura live foi disparada ou validada.
- `main` permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. Sem VPS, serviços pagos, chaves privadas, compras/vendas ou merge. Próxima tarefa desbloqueada: execução live curta e auditável por workflow manual e preservação permanente do artifact após checar credenciais/infra, sem simular falha do provedor; resultado deve registrar `recovery_live_proven=false` se desconexão natural não ocorrer.
