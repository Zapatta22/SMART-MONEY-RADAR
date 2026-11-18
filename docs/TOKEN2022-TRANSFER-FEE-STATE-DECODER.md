# Decoder de estado TransferFee — Token-2022

## Escopo

Parsing offline das extensões TransferFeeConfig (mint) e TransferFeeAmount (token account). Não consulta RPC, não infere epoch histórico, não associa transferências a swaps, não reconcilia nem persiste.

## Layout de bytes

Fonte oficial: solana-program/token-2022, interface/src/extension/transfer_fee/mod.rs e interface/src/extension/mod.rs.

- ExtensionType TransferFeeConfig = 1, payload 108 bytes.
- ExtensionType TransferFeeAmount = 2, payload 8 bytes.
- TLV: u16 type little-endian + u16 length little-endian + payload.
- AccountType Mint = 1; AccountType Account = 2.
- AccountType no offset 165; TLV começa no offset 166.
- Mint base 82 bytes; token account base 165 bytes.
- TransferFeeConfig: authorities opacas (64 bytes), withheld_amount u64, older_transfer_fee (18 bytes), newer_transfer_fee (18 bytes).
- Cada TransferFee: epoch u64, maximum_fee u64, basis_points u16.
- TransferFeeAmount: withheld_amount u64.

## Seleção histórica

Com epoch explicitamente fornecido: selecionar newer se epoch >= newer_transfer_fee.epoch; caso contrário older. O decoder não obtém epoch do relógio nem da configuração atual. O chamador deve fornecer epoch histórico comprovado para a slot/transação; sem isso, não presumir taxa.

## Fail-closed e limites

Rejeita tipo de conta incorreto, dados base truncados, TLV truncado, extensão alvo ausente/duplicada, tamanho inesperado e basis points acima de 10.000. Extensões desconhecidas válidas são ignoradas pelo comprimento TLV. Padding zero é aceito.

Authorities são mantidas opacas. O withheld_amount lido isoladamente não prova a taxa de uma transferência. Saldos pre/post representam spendable, não withheld. Transferência bruta, crédito líquido, delta spendable e withheld precisam ser reconciliados por operação sem movimentos concorrentes desconhecidos.


- Validação adicional: o decoder agora rejeita bytes não zero no padding do Mint entre o byte 82 e o AccountType no offset 165. Teste negativo dedicado adicionado. Isso fecha uma lacuna do parser TLV sem alterar o formato de contas Token-2022.