# DAMM v2 — atribuição de transferência de referral

## Fonte on-chain fixada

- Repositório: `MeteoraAg/damm-v2`
- Commit: `18936b18c26708f6e9b52cacc01ea2f99868ba8e`
- Referências: `programs/cp-amm/src/instructions/swap/ix_p_swap.rs`, `programs/cp-amm/src/state/fee.rs`, `programs/cp-amm/src/event.rs`.

## Comportamento confirmado no programa

Após calcular e aplicar o resultado do swap, o handler:
1. transfere `included_transfer_fee_amount_in` do usuário para o input vault;
2. transfere `included_transfer_fee_amount_out` do output vault para o usuário;
3. se `has_referral`, transfere `swap_result.referral_fee` do vault do token de cobrança para `referral_token_account`;
4. emite `EvtSwap2`.

A transferência de referral é separada das transferências de input e output do usuário.

## Determinação do vault de referral

A função oficial `FeeMode::get_fee_mode` é espelhada por `resolve_damm_fee_mode`:

| collect_fee_mode | trade_direction | fees_on_input | fees_on_token_a | Vault do referral |
|---|---|---:|---:|---|
| BOTH_TOKEN | A_TO_B | false | false | token B |
| BOTH_TOKEN | B_TO_A | false | true | token A |
| ONLY_B | A_TO_B | false | false | token B |
| ONLY_B | B_TO_A | true | false | token B |
| COMPOUNDING | A_TO_B | false | false | token B |
| COMPOUNDING | B_TO_A | true | false | token B |

O valor bruto da transferência de referral deve ser exatamente `EvtSwap2.swap_result.referral_fee`. Mint e Token Program também devem corresponder ao vault selecionado pelo FeeMode.

## Regras de atribuição

- A transferência deve ocorrer no mesmo grupo de instrução externa, ser descendente CPI do swap, ter hierarquia confiável e ocorrer antes do EvtSwap2.
- Quando `has_referral=True` e `referral_fee>0`, exige-se exatamente uma transferência do vault correto para a conta referral.
- Duplicidade, ausência, CPI não confiável, mint/programa divergente ou amount bruto diferente deixam a evidência AMBIGUOUS, TRANSFER_MISSING ou INCOMPLETE.
- Uma transferência não pode ser reutilizada por dois swaps ou papéis.
- TransferCheckedWithFee pode carregar `fee_amount_raw`; a taxa permanece separada e exige reconciliação posterior.

## Limites

O resultado continua `ATTRIBUTED`, nunca `MATCHED`. Esta camada não valida os deltas de token accounts/vaults, não reconcilia as transfer fees de referral, não cria SwapObservation e não produz BUY/SELL. A reconciliação econômica deve combinar EvtSwap2, input/output/referral transfers, Token-2022 withheld e deltas agregados por conta sem dividir arbitrariamente operações sequenciais.

## Validações fail-closed adicionais

- Somente `TRANSFER_CHECKED` e `TRANSFER_CHECKED_WITH_FEE` são aceitos para atribuição com mint/decimals.
- `TRANSFER_CHECKED_WITH_FEE` exige Token-2022 e `0 <= fee_amount_raw <= amount_raw`; qualquer fee em tipo comum é rejeitada.
- Amount bruto deve ser inteiro u64 positivo. Transferência de referral de valor zero não é atribuída; quando `referral_fee == 0`, nenhuma transferência é exigida.
- Mesmo com essas validações, `ATTRIBUTED` não significa igualdade econômica: a taxa de transferência e os deltas ainda precisam ser reconciliados em módulo posterior.
