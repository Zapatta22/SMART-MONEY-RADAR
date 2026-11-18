# Raydium CPMM — decodificação estrutural

## Escopo desta entrega

O decoder reconhece as duas instruções de swap documentadas pelo Raydium CPMM:

| Instrução | Discriminator | Argumentos u64 |
|---|---|---|
| `SwapBaseInput` | `8fbe5adac41e33de` | `amount_in`, `minimum_amount_out` |
| `SwapBaseOutput` | `37d96256a34ab4ad` | `max_amount_in`, `amount_out` |

Ambas possuem 13 contas obrigatórias na ordem documentada. Contas adicionais são preservadas em `remaining_accounts`, sem atribuir semântica não verificada a elas.

## Limite semântico obrigatório

Os argumentos decodificados não representam necessariamente os valores efetivamente transferidos:

- `minimum_amount_out` é um limite inferior de slippage, não o output efetivo.
- `max_amount_in` é um limite superior de input, não o input efetivo.
- Em `SwapBaseOutput`, `amount_out` é o output solicitado pela instrução; a confirmação econômica deve continuar baseada em evidências da execução.
- Este módulo não classifica BUY/SELL, não reconstrói CPI e não substitui deltas de saldo ou eventos on-chain.

## Validação

Os testes unitários deste módulo cobrem os dois discriminators, valores little-endian, programa não correspondente, instrução desconhecida, dados inválidos/truncados, as 13 contas-base e a preservação de contas adicionais.

Os testes unitários sintéticos validam o contrato estrutural. Não constituem fixture real de mainnet nem aprovação de decoder em produção.
