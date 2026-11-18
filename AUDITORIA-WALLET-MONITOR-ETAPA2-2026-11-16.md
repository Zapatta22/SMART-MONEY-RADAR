# Auditoria WalletMonitor / HeliusDataSource — Etapa 2

**Data:** 16/11/2026  
**Escopo:** cópia local de auditoria do SMART MONEY RADAR.

## Resultado

- **26 testes aprovados, 0 falhas.**
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- Nenhuma chamada real à Helius/Solana foi realizada.

## Alterações consolidadas nesta etapa

### 1. Deduplicação entre backfill e WebSocket

`WalletMonitor._collect_transaction` consulta `EventStore.has_processed_signature`
antes de buscar a transação. Se a assinatura já foi processada para aquela
carteira, a notificação repetida é ignorada. O teste
`test_websocket_notification_overlapping_backfill_is_deduplicated` cobre a
sobreposição.

### 2. Persistência do checkpoint

`SQLiteEventStore.save_checkpoint` insere a assinatura em
`processed_signatures` e atualiza `wallet_checkpoints` dentro da mesma transação
SQLite. Isso torna atômica a atualização do marcador e do registro de
processamento. A persistência dos eventos e o checkpoint continuam sendo
operações distintas; em caso de interrupção entre elas, a idempotência da
gravação de eventos permite repetir o processamento sem duplicar eventos.

### 3. Falhas de backfill e RPC

Foram adicionados testes para: checkpoint fora do limite de páginas; retries
esgotados sem avanço do checkpoint; erro RPC preservando o checkpoint; e
recuperação incremental após checkpoint. Em falha, o monitor não avança o
checkpoint como se a transação tivesse sido processada.

### 4. Lifecycle da CLI e SQLite

A CLI executa `shutdown_asyncgens()` e `shutdown_default_executor()` antes de
fechar o Event Store e o event loop. O segundo passo é relevante porque o
adaptador Helius usa `asyncio.to_thread` para chamadas RPC. O fechamento do
Event Store ocorre também no caminho de exceção do monitor. Foi testado ainda
o fechamento idempotente do SQLite em memória.

## Evidências de teste

- `test_backfill_fails_if_checkpoint_is_outside_page_limit`
- `test_backfill_keeps_checkpoint_when_transaction_retries_are_exhausted`
- `test_backfill_rpc_error_preserves_checkpoint`
- `test_websocket_notification_overlapping_backfill_is_deduplicated`
- `test_monitor_closes_event_store_when_run_finishes`
- `test_monitor_closes_event_store_when_monitor_raises`
- `test_close_is_idempotent_for_in_memory_store`
- Demais testes da suíte de settings, RPC, parser, métricas, armazenamento e monitor.

Comando executado:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m compileall -q src tests
```

Resultado observado nesta execução: **26/26 OK** e `COMPILEALL_OK`.

## Limitações ainda abertas

1. O backfill permanece limitado a 10 páginas de até 100 assinaturas por
   carteira por conexão. Ao exceder o limite, falha explicitamente sem avançar
   o checkpoint; ainda falta estratégia operacional de recuperação para
   períodos de indisponibilidade muito longos.
2. A primeira execução sem checkpoint não faz varredura histórica.
3. Não foi validada remotamente a semântica/ordem da paginação com Helius.
4. Não há medição de throughput ou latência sob carga; o processamento segue
   serial.
5. O parser continua parcial e não decodifica todos os programas e formatos
   de swap da Solana.
6. A persistência de eventos e o checkpoint não são uma única transação
   conjunta; a segurança contra repetição depende da idempotência da EventStore.
7. Não há integração ponta a ponta com Launch Radar, Market Radar, Decision
   Engine, Risk Manager, Portfolio Manager ou execução de swaps.

## Estado de entrega

Este relatório e o pacote correspondente descrevem uma cópia local de auditoria.
Não foram instalados no telefone, Replit ou VPS do usuário. Não foram usadas
credenciais nem contratados serviços.
