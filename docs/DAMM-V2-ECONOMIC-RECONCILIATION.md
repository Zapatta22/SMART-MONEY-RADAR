# DAMM v2 — reconciliação econômica por transação

## Objetivo e fronteira

O módulo `damm_v2_economic_reconciliation.py` compara evidências atribuídas de input/output/referral com os deltas pre/post de token accounts. A validação é feita para o lote completo de swaps DAMM v2 da transação, não dividindo deltas líquidos arbitrariamente entre swaps sequenciais.

O resultado `RECONCILED` significa que as transferências atribuídas e os deltas base pre/post por token account conferem no lote completo. Não significa que o estado TLV de withheld fees ou a configuração/epoch histórica do mint tenham sido verificados. Não cria `SwapObservation`, BUY/SELL, sinal, recomendação nem autorização de execução.

## Invariantes de input e output

| Papel | Débito bruto | Crédito spendable líquido |
|---|---|---|
| Input do usuário → input vault | `included_transfer_fee_amount_in` | `swap_result.included_fee_input_amount` |
| Output vault → usuário | `included_transfer_fee_amount_out` | `excluded_transfer_fee_amount_out` |

- O delta do token account de origem é negativo pelo bruto.
- O delta da conta de destino é positivo pelo líquido.
- `TransferCheckedWithFee` deve trazer fee explícita válida e reproduzir o líquido do evento.
- TransferChecked Token-2022 sem fee explícita só é aceito em input/output porque o EvtSwap2 fornece os valores bruto e líquido que serão confrontados com os deltas.
- SPL Token não pode apresentar diferença bruto/líquido por transfer fee.

## Referral

- Quando `has_referral=True` e `referral_fee>0`, a transferência precisa estar atribuída.
- Vault, mint e Token Program são revalidados pelo `FeeMode` oficial.
- O débito do vault é o bruto `referral_fee`.
- Para referral Token-2022 via `TransferChecked` padrão, o líquido é calculado pela configuração histórica do mint no epoch da transação; exige snapshot prestate específico daquela instrução e prova de que a configuração não mudou antes dela. Sem isso, falha fechado.
- `TransferCheckedWithFee` usa a taxa explícita da instrução, que também é conferida contra o mint prestate/epoch.
- A transferência de referral não pode ser confundida com o output do usuário.

## Agregação e proteção contra múltiplos swaps

O reconciliador:
1. recebe todos os contextos e evidências de swaps DAMM v2 da transação;
2. agrega débitos/créditos esperados por token account, mint e decimals;
3. exige inventário completo de transferências decodificadas e rejeita transferências não atribuídas que toquem contas envolvidas;
4. compara cada delta agregado com snapshots pre/post completos;
5. rejeita transferências reutilizadas, CPI não confiável, identidade/contas divergentes, snapshots incompletos e qualquer divergência.

Movimentos externos que atinjam as mesmas token accounts também podem provocar `INCOMPLETE`; não são absorvidos por inferência. A garantia depende de o chamador fornecer o conjunto completo de swaps DAMM v2, a saída completa do decoder de transferências e o resultado completo do decoder de deltas.

## Limitações explícitas

- O decoder de deltas exige snapshots pre/post pareados; não presume saldo zero quando falta um lado.
- O inventário de transferências é tão completo quanto as instruções suportadas pelo decoder SPL/Token-2022 atual. Extensões de transferência ainda não decodificadas permanecem fora do escopo.
- O módulo não consulta estado do mint nem escolhe epoch; não recalcula a taxa Token-2022 a partir de configuração histórica.
- `RECONCILED` não equivale à classificação BUY/SELL e não é, sozinho, condição suficiente para execução.
- Nenhuma RPC/Helius, fixture RAW, SQLite, checkpoint ou operação on-chain é executada.


## Ownership e withheld fees

- O reconciliador exige `monitored_wallet` explicitamente; as token accounts de input e output precisam declarar esse owner nos snapshots.
- Os dois vaults do pool precisam declarar `pool_authority` como owner. O `payer` não é usado como substituto do owner econômico.
- O resultado expõe `expected_withheld_fee_deltas`: para cada transferência Token-2022, bruto menos crédito spendable é registrado como aumento esperado de withheld na conta destino.
- `withheld_fee_status=EXPECTED_NOT_VERIFIED` significa que o delta foi derivado e conciliado com o saldo base, mas o TLV `TransferFeeAmount.withheld_amount` pre/post ainda não foi lido e comparado. `NOT_REQUIRED` significa que não houve fee retida esperada.
- Não inferir epoch nem taxa histórica a partir do estado atual do mint. A próxima camada deve receber snapshots históricos comprovados do mint e das token accounts, validar o epoch aplicável e comparar o delta real de withheld por conta.


## Decoder de withheld pre/post

- `token2022_transfer_fee_state.decode_transfer_fee_amount_delta(pre_account_data, post_account_data)` decodifica o TLV `TransferFeeAmount` em ambos os snapshots e retorna delta assinado (positivo, zero ou negativo, por exemplo após harvest).
- A função exige a extensão nos dois lados e o mesmo conjunto de extensões. Não trata extensão ausente como zero.
- O decoder valida bytes/TLV, mas não prova que os bytes são snapshots imediatamente antes/depois da transação. A proveniência temporal, assinatura, slot e ordenação devem ser garantidos pelo coletor.
- O resultado do reconciliador DAMM ainda mantém `withheld_fee_status=EXPECTED_NOT_VERIFIED` até que os deltas TLV observados sejam ligados à mesma transação e comparados com `expected_withheld_fee_deltas`.
- `getTransaction` com `preTokenBalances/postTokenBalances` não substitui os bytes TLV pre/post da token account; o valor spendable e o withheld extension são campos distintos.


## Verificação de withheld vinculado à transação

- `verify_damm_v2_withheld_fee_deltas` recebe o resultado base, snapshots TLV decodificados e a identidade da transação (assinatura, slot e ordem).
- Cada snapshot precisa corresponder à mesma assinatura/slot/ordem e comprovar `pre_snapshot_order < transaction_order < post_snapshot_order` no mesmo domínio de ordenação do coletor.
- O snapshot precisa trazer referências distintas para os estados pre/post e a saída tipada de `decode_transfer_fee_amount_delta`; o verifier compara o delta observado com o valor esperado por conta/mint.
- Resultado `withheld_fee_status=VERIFIED` só é emitido quando todas as contas com fee esperada têm snapshots correspondentes e os deltas TLV coincidem exatamente.
- Falta de snapshot, identidade diferente, ordem não demonstrada, extensão ausente ou valor divergente mantém o lote fora de verificação e retorna `INCOMPLETE` (duplicidade retorna `AMBIGUOUS`).
- Os campos de proveniência são um contrato do coletor, não uma prova criptográfica por si só. A implementação do adapter precisa garantir que os refs/hash correspondam aos bytes realmente coletados na fronteira da transação.


## Verificação da configuração histórica do mint e epoch

- `decode_transfer_fee_config_optional(mint_data)` valida o estado base/TLV do mint e retorna `None` quando a extensão `TransferFeeConfig` não existe; a função estrita `decode_transfer_fee_config` continua lançando erro quando a extensão é ausente.
- Cada `DammV2ExpectedTransferFee` identifica uma transferência Token-2022 específica (outer/inner instruction, mint, bruto e fee inferida/explicita).
- `verify_damm_v2_mint_fee_config` exige um snapshot por transferência, vinculado ao mesmo mint, assinatura/slot/ordem e anterior à transação. O adapter também deve provar que a configuração do mint não mudou antes daquela transferência dentro da transação.
- Com configuração presente, escolhe `older_transfer_fee` ou `newer_transfer_fee` pelo epoch fornecido e recalcula a taxa com `calculate_transfer_fee` (ceil e cap); sem extensão, a taxa esperada é zero.
- `mint_fee_config_status=VERIFIED` só ocorre se todas as transferências Token-2022 conferirem com a configuração prestate e epoch.
- A função não deriva epoch do slot: o adapter precisa fornecer epoch historicamente correto. O estado atual do mint não substitui prestate.
- Referral Token-2022 via `TransferChecked` padrão agora pode ser reconciliada quando o adapter fornece o snapshot histórico específico da instrução; o líquido é calculado pelo mint config/epoch e depois confrontado com os deltas base e withheld. Sem snapshot ou se o mint puder ter mudado antes da transferência, falha fechado.


## Referral Token-2022 TransferChecked padrão

- `reconcile_damm_v2_economic_batch` aceita opcionalmente `mint_fee_snapshots`, `transaction_epoch`, `transaction_slot` e `transaction_order`.
- Para referral Token-2022 em `TRANSFER_CHECKED`, exige exatamente um snapshot que corresponda ao outer/inner instruction e mint da transferência.
- Calcula a taxa no bruto referral com a configuração prestate e epoch, deriva o crédito líquido, agrega o delta da referral account e registra `fee_source=MINT_PRESTATE`.
- A chamada posterior a `verify_damm_v2_mint_fee_config` revalida todos os snapshots e todas as taxas do lote, incluindo input/output/referral.
- Sem snapshot, com identidade divergente, epoch incorreto ou possível alteração do mint antes da transferência, o lote retorna `INCOMPLETE`.
