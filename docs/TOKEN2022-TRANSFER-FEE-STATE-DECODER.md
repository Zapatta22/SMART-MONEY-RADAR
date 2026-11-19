# Decoder de estado TransferFee — Token-2022

## Escopo

Parsing offline das extensões TransferFeeConfig (mint) e TransferFeeAmount (token account). Não consulta RPC, não infere epoch histórico, não associa transferências a swaps, não reconcilia nem persiste.

## Layout de bytes

Fonte oficial fixada: `solana-program/token-2022@875693f53c77534b46f0d06bdf781430870f8177`, arquivos `interface/src/extension/transfer_fee/mod.rs`, `interface/src/extension/mod.rs` e `interface/src/state.rs`.

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

Rejeita tipo de conta incorreto, dados base truncados, cabeçalho/payload TLV truncados, extensão alvo ausente/duplicada, tamanho inesperado e basis points acima de 10.000. Extensões conhecidas não alvo são ignoradas pelo comprimento TLV; discriminantes não definidos no enum oficial são rejeitados. O tipo `Uninitialized` (0) encerra a lista de extensões; uma cauda final de um byte é tolerada conforme o iterador oficial Token-2022 (pode ocorrer durante realocação). Padding zero é aceito. O decoder também valida o estado base inicializado, tags COption, aceita token account Frozen, e rejeita comprimento 355 (colisão com Multisig) conforme StateWithExtensions::unpack.

Authorities são mantidas opacas. O withheld_amount lido isoladamente não prova a taxa de uma transferência. Saldos pre/post representam spendable, não withheld. Transferência bruta, crédito líquido, delta spendable e withheld precisam ser reconciliados por operação sem movimentos concorrentes desconhecidos.


- Validação adicional: o decoder agora rejeita bytes não zero no padding do Mint entre o byte 82 e o AccountType no offset 165. Teste negativo dedicado adicionado. Isso fecha uma lacuna do parser TLV sem alterar o formato de contas Token-2022.

### Validação da estrutura base conforme o parser oficial

Além do TLV, a decodificação valida:
- Mint: is_initialized == 1, tags COption de mint/freeze authority iguais a 0 ou 1 e padding zero até AccountType.
- Token account: estado Initialized ou Frozen; tags COption de delegate, is_native e close authority iguais a 0 ou 1.
- Comprimento total de 355 bytes é rejeitado por colidir com o tamanho de Multisig.
- Somente tipos ExtensionType definidos no commit oficial fixado são aceitos; tipos desconhecidos falham fechados.

O resultado expõe `extension_types` (todos os tipos TLV conhecidos presentes). O consumidor deve inspecionar essa lista e bloquear extensões que não estejam cobertas pelo fluxo econômico; em particular, este decoder não interpreta extensões confidenciais de fee, transfer hooks ou outros mecanismos. O decoder também não valida o owner do account no runtime; o chamador deve comprovar que mint/token account pertence ao Token-2022 Program antes de usar o resultado.
