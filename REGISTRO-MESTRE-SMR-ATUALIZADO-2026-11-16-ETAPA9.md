# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-16 — Etapa 9

## 1. Estado executivo

Fase atual: auditoria/consolidação da ingestão e preparação de decodificação Solana por programa.
Prioridade V1: Solana; arquitetura extensível sem implementar multichain agora.
Estado real: coletor/monitor de carteiras somente leitura com Helius RPC/WebSocket, backfill, parser conservador, persistência SQLite, payload bruto, replay e normalização integrada. O SMR completo não está implementado, integrado ou operando 24/7.

## 2. Base e evidência de continuidade

A conversa trouxe um Registro Mestre até a Etapa 6, mas a Library continha artefatos posteriores. A continuidade foi feita a partir do pacote mais recente recuperado: `SMR-CODIGO-BASE-ETAPA8-2026-11-16.zip`, acompanhado dos Registros Mestres das Etapas 7 e 8 e respectivos relatórios. A suíte do pacote Etapa 8 foi reexecutada antes de alterações: 58/58 testes aprovados.

## 3. Etapas concluídas

- Etapas 1–6: monitor/Helius, backfill e retries, shutdown, parser conservador, payload bruto/replay, integridade/backup e inventário, conforme relatórios anteriores incluídos no pacote.
- Etapa 7: contratos `ObservedTransaction`, `TokenBalanceDelta`, `SwapObservation`, `PoolSnapshot`, `WalletProfile`.
- Etapa 8: adaptador `normalize_transaction` produzindo envelope, deltas SPL e eventos legados.
- Etapa 9: integração do adaptador no `WalletMonitor` e persistência atômica no `SQLiteEventStore`.

## 4. Atualização técnica — Etapa 9

Arquivos alterados:
- `src/smart_money_radar/services/wallet_monitor.py`
- `src/smart_money_radar/storage/event_store.py`
- `src/smart_money_radar/domain/normalization.py`
- `tests/test_wallet_monitor.py`
- `tests/test_event_store.py`
- `tests/test_normalization.py`
- `README.md`

Entregas:
- WalletMonitor usa `normalize_transaction` e continua preservando payload bruto/`parse_error` em exceção.
- Nova tabela `token_balance_deltas` e novas colunas `chain`, `slot`, `occurred_at` em `observed_transactions`.
- Migração incremental de banco legado, sem perda de registros.
- Gravação atômica do envelope normalizado, deltas SPL, eventos legados, payload, assinatura processada e checkpoint.
- `get_token_deltas` e metadados estendidos.
- Replay substitui eventos/deltas derivados sem mover checkpoint ou sobrescrever payload bruto.
- Backup/restauração preserva deltas normalizados.
- `decimals` SPL é propagado apenas quando escalas observadas concordam.

Validação: 62 testes aprovados, 0 falhas; `compileall` aprovado. Testes locais/simulados, sem RPC real, carga ou benchmark.

## 5. Arquitetura atual comprovada

`CLI -> WalletMonitor -> HeliusDataSource -> JSON-RPC/WebSocket`

`WalletMonitor -> normalize_transaction -> ObservedTransaction + TokenBalanceDelta + ActivityEvent`

`WalletMonitor -> SQLiteEventStore -> observed_transactions / token_balance_deltas / activity_events / checkpoints`

A integração é da ingestão e persistência; não é pipeline de trading. Launch Radar, Market Radar, Swap Decoder por programa, Wallet Intelligence completo, Decision Engine, Risk Manager, Portfolio Manager, Execution Engine, paper trading, backtesting, app e deploy 24/7 continuam não implementados.

## 6. Restrições preservadas

- Solana V1; sem multichain nesta fase.
- Launch Radar e Market Radar permanecem pipelines independentes planejados.
- Modos IMMEDIATE e CONFIRMATION compartilham os mesmos bloqueios de segurança.
- Nenhum aprendizado pode contornar segurança ou alterar regras produtivas sem validação.
- Sem assinatura/envio de transações ou trades reais.
- Sem chamadas remotas pagas, contratação de VPS ou ativação de serviços pagos sem autorização explícita.
- Não rotular fixture sintética como fixture real.

## 7. Limitações e riscos remanescentes

- Parser ainda cobre deltas SPL e instruções System transfer/transferWithSeed decodificadas; não interpreta swaps/rotas/AMMs.
- Nenhuma fixture real de swap foi adicionada.
- Sem rate limiter, controle de créditos/budget Helius, circuit breaker, backpressure e métricas completas de latência.
- Sem replay em lote, retenção/rotação automatizada, backup agendado/off-site ou alertas operacionais.
- Sem RPC real, benchmark, carga, validação de VPS ou operação 24/7.
- Código segue apenas na cópia local de auditoria; não instalado no ambiente original, Replit ou VPS.

## 8. Próxima tarefa exata

Preparar matriz de programas/instruções Solana prioritários e coletar fixtures reais públicas verificáveis e anonimizadas, preservando proveniência e expectativas de parsing. Em seguida implementar decodificadores específicos com testes por programa. Não iniciar novos motores de inteligência ou execução financeira antes de concluir essa base de ingestão.

## 9. Protocolo de continuidade

Usar este registro e o pacote Etapa 9 como referência mais recente. Consultar artefatos antes de alterar código. Atualizar registro e pacote ao concluir cada etapa. Distinguir especificado, implementado, integrado, testado, validado remotamente e em produção.
