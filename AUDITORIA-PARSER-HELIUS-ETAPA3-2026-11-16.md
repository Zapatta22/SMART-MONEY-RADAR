# Auditoria do Parser Solana e Helius — Etapa 3

**Data:** 2026-11-16  
**Escopo:** `transaction_parser.py`, `helius.py`, testes do parser/RPC e integração do parser no `WalletMonitor`.

## Resultado

A auditoria aprofundou o parser e o cliente RPC. Foram aplicadas correções conservadoras e adicionados testes automatizados. A suíte completa passou com **33 testes aprovados, 0 falhas**; `compileall` também foi aprovado.

## Alterações implementadas

1. O parser não interpreta arrays de saldo ausentes/malformados como saldo zero. Se `preTokenBalances` ou `postTokenBalances` não forem listas, deixa de emitir deltas de tokens artificiais para aquela resposta.
2. O campo SPL `decimals` é validado como inteiro não booleano no intervalo `0..255`, evitando payloads fora do domínio do campo `u8`.
3. Mantida a agregação de saldos de várias contas token da mesma carteira e do mesmo mint.
4. Adicionado teste de transferência SOL decodificada em `innerInstructions`.
5. Adicionados testes do cliente RPC para preservação de `before`/`until` na paginação de `getSignaturesForAddress` e rejeição de limite inválido.
6. README atualizado com a cobertura atual e os limites do parser.

## Cobertura atual comprovada

- Deltas agregados por mint, desde que o campo `owner` dos registros de saldo corresponda ao endereço monitorado.
- Instruções `System Program` `transfer` e `transferWithSeed` quando explicitamente decodificadas em `jsonParsed`, tanto em instruções externas quanto em `innerInstructions`.
- Timestamp `blockTime` quando presente; caso contrário, `occurred_at=None`.
- Transações com `meta.err` não geram eventos.

## Lacunas e riscos ainda abertos

### Bloqueio de integridade de dados — prioridade alta

`WalletMonitor._collect_transaction` chama `parse_transaction`, grava os eventos retornados e avança o checkpoint mesmo quando a lista de eventos está vazia. Isso pode ocorrer legitimamente, mas também quando a resposta não contém campos reconhecidos pelo parser. A assinatura passa a constar como processada e o payload bruto não é armazenado. Consequência: a operação pode desaparecer da visão analítica e não poderá ser reinterpretada localmente quando o parser ganhar suporte a novos programas.

**Decisão técnica recomendada para a próxima etapa:** persistir a transação bruta (ou um registro durável de observação com payload e estado de parsing) antes de avançar o checkpoint; separar `observed`, `parsed`, `unsupported`, `failed_on_chain` e `parse_error`; permitir replay/reprocessamento versionado. Definir política de retenção e orçamento de armazenamento antes de habilitar isso em volume.

### Cobertura funcional do parser

- Não reconstrói semântica completa de swaps, rotas de agregadores, pools, LP, staking, lending ou operações específicas de programas.
- Não calcula SOL líquido por diferença de `preBalances`/`postBalances`; portanto não captura de forma abrangente taxas, rent, recompensas, fechamento/criação de contas ou outros efeitos nativos.
- Não calcula preço, valor em USD, slippage, PnL ou intenção.
- Depende de `owner` nos saldos de token; registros sem owner são ignorados de forma conservadora.
- O RPC solicita `maxSupportedTransactionVersion: 0`; versões de transação posteriores não estão cobertas por esta implementação.
- Não houve validação com fixtures de transações reais de todos os programas prioritários, nem teste remoto contra Helius/Solana.

## Evidências de teste

Comando:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m compileall -q src tests
```

Resultado: **33 testes aprovados, 0 falhas**; compilação aprovada. Testes executados com fakes/mocks; nenhuma chamada real à rede foi realizada.

## Estado de implantação

As alterações existem somente na cópia local de auditoria e no pacote versionado desta etapa. Não foram instaladas no ambiente do usuário, Replit, telefone ou VPS. O sistema continua sendo um monitor parcial somente leitura, não o SMR completo.
