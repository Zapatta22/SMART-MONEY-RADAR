# Adaptador DAMM v2 para contratos de domínio

## Fronteira

`build_damm_v2_swap_domain_bundles()` converte contextos e evidências de transferência DAMM v2 em três contratos independentes: `SwapObservation`, `SwapClassification` e `SwapEvidence`.

A função não decodifica transações, não atribui transferências e não substitui a reconciliação econômica. Ela só aceita um lote cujo resultado fornecido seja `RECONCILED`, com snapshots completos, e cujo número de operações corresponda exatamente aos contextos e evidências recebidos.

## Regras de construção

- A identidade usa `build_swap_operation_id("solana", signature, instruction_index, cpi_path)`.
- A carteira monitorada é confirmada pelo campo `owner` dos deltas das token accounts de origem do input e destino do output.
- `input_amount` representa o débito bruto da carteira, conforme `EvtSwap2.included_transfer_fee_amount_in`.
- `output_amount` representa o crédito spendable líquido, conforme `EvtSwap2.excluded_transfer_fee_amount_out`.
- Os valores são convertidos para `Decimal` com os decimals das transferências; não há conversão para float.
- A classificação inicial é sempre `UNKNOWN`, confiança zero. A direção A→B/B→A do pool não define, sozinha, o ativo-base/quote nem a semântica BUY/SELL.
- Os três objetos compartilham `operation_id`, mas não são fundidos em um registro monolítico.

## Falha fechada

A função rejeita lote não reconciliado, snapshots incompletos, evidência não atribuída, associação não MATCHED, inconsistência de contas/mints, ausência de propriedade verificável da carteira e divergência de cardinalidade.

## Limites

- Não persiste no SQLite e não altera checkpoints.
- Não integra ainda o parser/normalizador.
- Não consulta RPC/Helius e não modifica fixtures RAW.
- Não produz sinal, recomendação ou autorização de execução.
- A existência de testes unitários não substitui execução da suíte nem validação com fixture mainnet comprovada.
