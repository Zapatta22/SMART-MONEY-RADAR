# Pipeline transacional DAMM v2

## Objetivo

Encadear os componentes DAMM v2 existentes em uma única operação por payload `getTransaction`, sem alterar o parser legado nem persistir dados automaticamente.

## Ordem do pipeline

1. Validar `transaction.message`, `meta` e `meta.err`; execução desconhecida ou transação falha é rejeitada.
2. Executar `analyze_damm_v2_swap_events` e exigir associação única para todos os swaps e eventos DAMM v2 encontrados. Eventos órfãos e associações ambíguas bloqueiam o lote.
3. Resolver a instrução original (externa ou inner) e as `accountKeys`, incluindo `loadedAddresses` quando o payload usa chaves compiladas.
4. Resolver contas e direção input/output com `decode_damm_v2_swap_accounts`.
5. Decodificar todas as transferências SPL/Token-2022 e atribuí-las por contas e hierarquia CPI.
6. Decodificar snapshots completos de token accounts.
7. Executar reconciliação econômica agregada por transação.
8. Só com status `RECONCILED`, produzir bundles `SwapObservation` + `SwapClassification` + `SwapEvidence`.

## API

```python
result = process_damm_v2_transaction(
    raw_transaction,
    monitored_wallet=wallet,
    signature=signature,
    observed_at=observed_at,
    parser_version=PARSER_VERSION,
)
```

Estados possíveis: `NO_DAMM_V2_SWAPS`, `REJECTED` e `RECONCILED`. O resultado contém diagnósticos intermediários para auditoria. Em `REJECTED`, bundles nunca são emitidos.

## Limites deliberados

- O módulo não é chamado por `transaction_parser.py` ou `normalize_transaction`.
- Não grava no `SQLiteEventStore`, não avança checkpoint e não altera RAW.
- Não chama RPC/Helius nem faz operações on-chain.
- Não converte direção do pool em BUY/SELL; o adaptador mantém `UNKNOWN`.
- A suíte sintética cobre fronteiras fail-closed, mas não substitui fixture RAW mainnet com swap DAMM v2 real e reconciliação completa.
- A função retorna `RECONCILED` apenas quando as verificações existentes confirmam o lote. Isso não constitui sinal nem autorização para execução.

## Persistência e coordenação do checkpoint

O módulo `domain/damm_v2_persistence_pipeline.py` envolve o orquestrador
transacional e persiste bundles reconciliados e tentativas de reconciliação
no `SQLiteEventStore`. Ele **nunca** avança checkpoint.

O `WalletMonitor` agora executa DAMM v2 antes do pipeline Raydium CPMM:
- Se DAMM v2 encontrar swaps não reconciliados, a transação permanece pendente
  e o CPMM não pode avançar o checkpoint.
- Se DAMM v2 não encontrar swaps, ou concluir reconciliação completa, o fluxo
  segue para CPMM.
- O CPMM continua sendo o coordenador final do checkpoint nesta etapa; assim,
  transações sem swaps CPMM ainda são marcadas como processadas somente depois
  de DAMM v2 liberar a transação.
- Bundles são idempotentes no EventStore. Uma repetição após falha de outro
  venue não deve duplicar operações.

Testes de persistência usam SQLite `:memory:`; o teste do monitor simula
bloqueio DAMM e confirma que CPMM não é chamado e checkpoint não avança.
