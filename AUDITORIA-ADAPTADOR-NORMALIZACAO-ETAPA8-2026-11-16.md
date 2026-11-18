# SMR — Adaptador de normalização — Etapa 8

Data: 16/11/2026

## Entrega

Criado `domain/normalization.py` com `normalize_transaction` e o resultado
`NormalizedObservation`. O adaptador transforma a resposta RPC do parser atual
em três representações compatíveis:

1. `ObservedTransaction`: envelope, payload bruto, cadeia, carteira, assinatura,
   instante de observação, slot, horário on-chain, versão e estado.
2. `TokenBalanceDelta`: deltas SPL tipados, mantendo quantidade Decimal.
3. `ActivityEvent`: eventos legados preservados para o pipeline atual.

SOL nativo não é rotulado como mint SPL e fica apenas nos eventos legados de
transferência até existir um contrato específico de movimento nativo.

## Estados

- `parsed`: parser produziu pelo menos um evento.
- `no_events`: parser não produziu evento; payload permanece no envelope.
- `failed_on_chain`: RPC indicou `meta.err`.

Exceções de parsing não são convertidas silenciosamente em `no_events`; elas
continuam sendo exceções para que a camada chamadora registre `parse_error`.

## Compatibilidade

O adaptador não altera o monitor, EventStore ou esquema SQLite. Não há ainda
persistência dos novos contratos no pipeline em execução. Isso evita declarar
integração ponta a ponta antes dos testes transacionais e de migração.

## Validação

- 58 testes `unittest` aprovados.
- `compileall` aprovado.
- 5 testes novos para normalização, status, payload, slot e validação de entrada.
- Sem chamadas reais à Helius/Solana, sem teste de carga e sem deploy.

## Próximo passo

Integrar o adaptador no WalletMonitor/EventStore com uma gravação atômica do
envelope normalizado e dos deltas, preservando os registros ActivityEvent e a
compatibilidade com bancos existentes. Antes de migração, criar teste de
reabertura de banco antigo e rollback em falha de persistência.
