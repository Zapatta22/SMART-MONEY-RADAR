# SMART MONEY RADAR — Registro Mestre — Etapa 8

Data: 16/11/2026

## Estratégia e restrições

Solana é a prioridade absoluta da V1. Launch Radar e Market Radar serão
pipelines independentes. Os modos IMMEDIATE e CONFIRMATION compartilharão os
mesmos bloqueios de segurança. Aprendizagem e inteligência não podem ignorar
Risk Manager nem alterar regras produtivas sem validação. Operação 24/7 em VPS
é objetivo futuro, sem contratação ou ativação de serviços pagos nesta etapa.

## Estado real da base

A base é um monitor de carteiras Solana somente leitura, com Helius RPC/
WebSocket, backfill, parser conservador, SQLite, payload bruto, replay, backup e
métricas básicas. Testes são locais/simulados.

## Etapa 7 — contratos de domínio

Adicionados `ObservedTransaction`, `TokenBalanceDelta`, `SwapObservation`,
`PoolSnapshot` e `WalletProfile`. Contratos validados, porém ainda não integrados
no pipeline legado.

## Etapa 8 — adaptador de normalização

Adicionados `domain/normalization.py` e `normalize_transaction`, retornando
`NormalizedObservation` com envelope `ObservedTransaction`, deltas SPL
`TokenBalanceDelta` e eventos legados `ActivityEvent`. Classifica `parsed`,
`no_events` e `failed_on_chain`, preserva payload bruto e mantém SOL nativo fora
do modelo SPL. Erros de parsing propagam para a camada chamadora, que pode
registrar `parse_error`.

**Limite:** o WalletMonitor e EventStore ainda não persistem os novos contratos.
Não existe integração ponta a ponta, decodificador completo de swaps, Launch
Radar, Market Radar, Wallet Intelligence, Decision Engine, Risk Manager,
Portfolio Manager, Execution Engine ou app operacional.

## Testes

- 58 testes `unittest` aprovados.
- `compileall` aprovado.
- 5 testes novos de normalização.
- Sem RPC real, benchmark, teste de carga ou implantação.

## Próxima tarefa exata

Integrar a normalização no WalletMonitor/EventStore de forma atômica,
preservando `ActivityEvent` e compatibilidade de bancos existentes. Testar
reabertura de banco antigo, rollback em falha de persistência, deduplicação e
replay. Em seguida, adicionar fixtures anonimizadas de swaps reais para os
programas Solana prioritários antes de construir o SwapDecoder.

## Artefatos

- `SMR-CODIGO-BASE-ETAPA8-2026-11-16.zip`
- `AUDITORIA-ADAPTADOR-NORMALIZACAO-ETAPA8-2026-11-16.md`
- `REGISTRO-MESTRE-SMR-ATUALIZADO-2026-11-16-ETAPA8.md`

Código em cópia local de auditoria, não instalado em telefone, Replit ou VPS.
