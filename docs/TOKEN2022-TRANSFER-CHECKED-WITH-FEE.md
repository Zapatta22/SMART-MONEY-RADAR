# Token-2022 — TransferCheckedWithFee

## Fonte oficial fixada

- Repositório: `solana-program/token-2022`
- Commit: `875693f53c77534b46f0d06bdf781430870f8177`
- Fontes: `interface/src/extension/transfer_fee/instruction.rs`, `program/src/processor.rs` e `clients/js/src/generated/instructions/transferCheckedWithFee.ts`.

## Layout compilado

A instrução usa `TokenInstruction::TransferFeeExtension` (opcode 26), subdiscriminador 1 para `TransferCheckedWithFee`, seguido de:

| Offset | Tamanho | Campo |
|---:|---:|---|
| 0 | 1 | opcode 26 |
| 1 | 1 | subdiscriminador 1 |
| 2 | 8 | amount (u64 little-endian) |
| 10 | 1 | decimals (u8) |
| 11 | 8 | fee (u64 little-endian) |

Comprimento total exato: 19 bytes.

Contas: índice 0 source, 1 mint, 2 destination, 3 authority; signers multisig opcionais seguem depois. A instrução só é reconhecida sob o programa Token-2022. Outros subdiscriminadores da extensão são ignorados por este decoder.

## Semântica econômica

- `amount_raw` é o valor bruto debitado da conta de origem.
- `fee_amount_raw` é a taxa esperada na instrução. O programa Token-2022 recalcula a taxa usando o epoch atual e rejeita a instrução se o valor declarado divergir.
- Em uma transação executada com sucesso, o destino recebe em saldo spendable `amount_raw - fee_amount_raw`; a taxa é acumulada no campo withheld da extensão `TransferFeeAmount` da conta de destino.
- Os snapshots `preTokenBalances/postTokenBalances` refletem o saldo spendable, não o withheld. Por isso, para reconciliar deltas, a entrada líquida no destino precisa descontar a taxa; a origem continua debitada pelo bruto.

O decoder preserva bruto e taxa separadamente. Não infere epoch, não consulta mint, não valida configuração histórica e não converte valores para float.

## Integração e limites

- `SolanaTokenTransfer.instruction_type` recebe `TRANSFER_CHECKED_WITH_FEE`; `fee_amount_raw` fica disponível.
- O reconciliador Raydium calcula crédito spendable líquido no destino para esta variante e reporta `output_amount_raw` líquido recebido pela carteira.
- TransferChecked padrão com taxa Token-2022 continua sem taxa explícita no payload; divergências de delta permanecem INCOMPLETE. Nenhuma reconciliação é promovida por inferência.
- O analisador DAMM v2 pode atribuir a instrução por CPI, mas a atribuição continua `ATTRIBUTED`, não MATCHED. A reconciliação econômica DAMM v2 ainda exige validação do evento, taxas, transferências de referral e deltas por operação.

Nenhuma RPC/Helius, fixture RAW, banco, checkpoint ou operação on-chain é executada por este módulo.

## Validação no decoder e no contrato de domínio

- O decoder rejeita fee maior que o bruto, valores parsed fora de u64 e representação mista de accountKeys. A variante só é reconhecida sob o Token-2022 Program.
- Para dados `jsonParsed`, `feeAmount` precisa ser inteiro ou string decimal escalar; estruturas desconhecidas são ignoradas, sem inferência.
- O reconciliador mantém `input_amount_raw` como débito bruto da carteira e `output_amount_raw` como crédito spendable líquido. O builder de domínio revalida o tipo/programa, valida a taxa e exige que a saída líquida seja `gross - fee`.
- A evidência registra bruto, fee e débito/crédito da carteira separadamente. O delta da origem continua sendo bruto; o delta de destino é líquido. A taxa withheld não é tratada como saldo spendable.
