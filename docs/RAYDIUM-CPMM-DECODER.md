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


## Referências técnicas consultadas

- Raydium official CPMM instructions: https://github.com/raydium-io/raydium-docs-v1/blob/main/products/cpmm/instructions.mdx
- Raydium CPMM on-chain implementation (SwapBaseOutput): https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/instructions/swap_base_output.rs
- Raydium CPMM SDK demo (swapBaseOut): https://github.com/raydium-io/raydium-sdk-V2-demo/blob/master/src/cpmm/swapBaseOut.ts

A documentação oficial consultada confirma que SwapBaseInput e SwapBaseOutput usam as mesmas 13 contas-base e que o sentido input/output é orientado pelo usuário. O código on-chain de SwapBaseOutput confirma que o valor solicitado de output é ajustado por transfer-fee antes do cálculo, reforçando que os argumentos da instrução, isoladamente, não substituem a observação das transferências realmente executadas.


## Formatos de contas aceitos pelo analyzer

O analyzer aceita contas compiladas como índices numéricos em `message.accountKeys` (incluindo endereços carregados por Address Lookup Tables em `meta.loadedAddresses`) e contas já resolvidas como strings de endereço. Isso não significa que todo formato de resposta RPC foi validado: a entrada deve continuar contendo instruções com `data` codificada em Base58 e a lista de contas no formato esperado pelo analyzer. Instruções internas em `meta.innerInstructions` são deliberadamente ignoradas nesta versão.
