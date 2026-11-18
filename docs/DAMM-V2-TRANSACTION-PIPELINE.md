# Pipeline transacional DAMM v2

## Objetivo

Encadear os componentes DAMM v2 existentes em uma única operação por payload `getTransaction`, sem alterar o parser legado nem persistir dados automaticamente.

## Ordem do pipeline

1. Validar `transaction.message`, `meta.err` e `meta.innerInstructions`; execução desconhecida, transação falha ou metadados CPI ausentes/nulos são rejeitados. Lista vazia é aceita como evidência explícita de ausência de CPI. Em mensagens compiladas com `addressTableLookups`, exigir `meta.loadedAddresses` e cardinalidade exata de endereços writable/readonly antes de analisar índices de programa ou conta. Rejeitar também `loadedAddresses` não vazio quando não há lookup tables; o analyzer e os decodificadores independentes aplicam a mesma validação.
2. Executar `analyze_damm_v2_swap_events` e exigir associação única para todos os swaps e eventos DAMM v2 encontrados. Eventos órfãos e associações ambíguas bloqueiam o lote.
3. Resolver a instrução original (externa ou inner) e as `accountKeys`, incluindo `loadedAddresses` quando o payload usa chaves compiladas. A lista `accountKeys` deve usar um único formato: todos os itens como objetos `jsonParsed` ou todos como strings `compiled`; listas mistas são rejeitadas pelo pipeline, analyzer DAMM v2 e decodificadores de transferências/deltas.
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

A auditoria negativa de persistência também cobre um swap/Event CPI sintético
MATCHED cujo inventário de contas é inválido. O caso precisa gerar tentativa
`INCOMPLETE`, manter a assinatura na fila de replay e preservar o checkpoint.
Erros em estágios posteriores preservam as associações e diagnósticos já
produzidos, para que o adaptador de persistência não perca a identidade do swap
que ficou pendente.

Falhas de normalização também arquivam o payload bruto com `parse_status =
parse_error`, sem avançar checkpoint, para permitir replay após correção do
parser. Exceções inesperadas dentro do orquestrador transacional são convertidas
em `REJECTED`, preservando os diagnósticos já coletados e mantendo o fluxo
fail-closed.

## Fixture mainnet DAMM v2 — coleta local somente leitura

O catálogo versionado já contém um candidato Meteora DAMM v2. Para coletar
somente essa assinatura no Termux, sem baixar os outros quatro protocolos:

```bash
export SMR_SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
PYTHONPATH=src python tools/collect_damm_v2_fixture.py
```

O script grava RAW e manifesto localmente em
`data/fixtures/raw/damm-v2/`, valida a assinatura retornada e imprime slot e
SHA-256. Não envia o RAW ao GitHub, não anonimiza, não importa para SQLite e
não avança checkpoint. O próximo passo é inspecionar e anonimizar a fixture
localmente antes de qualquer proposta de versionamento.
