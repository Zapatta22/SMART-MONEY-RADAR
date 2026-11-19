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


## Inventário de instruções que inicializam TransferFeeConfig

- `decode_transfer_fee_config_mutation_instruction` reconhece o prefixo Token-2022 `TransferFeeExtension` (tag externa 26) e os sub-tags `InitializeTransferFeeConfig=0` e `SetTransferFee=5`.
- O snapshot do mint não usa mais uma declaração booleana genérica de que o mint não mudou. Ele recebe `transfer_fee_config_init_positions` e `transfer_fee_init_inventory_complete`.
- O verifier exige inventário completo das instruções de inicialização para aquele mint e rejeita qualquer `InitializeTransferFeeConfig` anterior ou na mesma posição da transferência.
- `SetTransferFee` não é tratado como alteração da taxa ativa no epoch corrente: no código Token-2022 fixado, a nova taxa é agendada para `current_epoch + 2` e a taxa ativa anterior é preservada em `older_transfer_fee`. A escolha older/newer continua feita por `fee_for_epoch(transaction_epoch)`.
- O adapter ainda precisa percorrer instruções externas e CPI, decodificar o programa Token-2022, resolver a conta mint e construir o inventário completo por mint. Sem inventário completo, falha fechado.
- Fonte de referência: `solana-program/token-2022@875693f53c77534b46f0d06bdf781430870f8177`, `interface/src/extension/transfer_fee/instruction.rs` e `program/src/extension/transfer_fee/processor.rs`.


## Scanner de instruções externas e CPI

- `decode_solana_instruction_inventory(raw_transaction)` produz inventário ordenado de instruções externas e inner/CPI, com program ID, contas resolvidas, bytes de dados/parsed type e posição outer/inner.
- O inventário é incompleto se `meta.innerInstructions` estiver ausente, a transação tiver falhado, program ID/account index não puder ser resolvido ou dados Token-2022 relevantes não puderem ser decodificados.
- `collect_transfer_fee_config_init_positions(inventory, mint)` percorre instruções Token-2022 cuja primeira conta é o mint, reconhece `InitializeTransferFeeConfig` e retorna posições `(outer_index, inner_index)`; `-1` representa instrução externa.
- `SetTransferFee` é validada, mas não entra na lista de inicialização porque agenda taxa futura e preserva a taxa ativa no epoch corrente. Sub-tags desconhecidas para a extensão causam inventário incompleto.
- O resultado `TransferFeeConfigInitInventory` fornece diretamente `initialization_positions` e `complete` para preencher o snapshot do mint. O adapter ainda precisa ligar essa saída ao coletor de snapshots históricos e ao cálculo do epoch.


## Construtor de snapshots de mint por transferência

- `build_damm_v2_mint_fee_config_snapshots(evidence, mint_prestate_by_mint, instruction_inventory, ...)` conecta a evidência de cada transferência Token-2022 ao prestate TLV do mint e ao inventário externo/CPI.
- Gera um snapshot por identidade outer/inner/mint, incluindo assinatura e slot da transação, epoch, ordem da transação, ordem do prestate, configuração decodificada, posições de inicialização, fonte e state ref.
- Exige que o inventário corresponda exatamente à assinatura/slot da transação e esteja completo; o prestate do mint precisa ser do mesmo slot e anterior à transação no mesmo domínio de ordenação.
- A configuração é decodificada por `decode_transfer_fee_config_optional`; ausência da extensão vira `config_state=None`, enquanto TLV inválido gera erro.
- A saída pode ser passada diretamente a `reconcile_damm_v2_economic_batch` (necessária para referral Token-2022 padrão) e depois a `verify_damm_v2_mint_fee_config`.
- O construtor não busca dados históricos: o adapter ainda precisa fornecer bytes de mint realmente capturados antes da transação, com fonte/ref rastreáveis. Estado atual obtido por `getAccountInfo` não serve como substituto.


## Fonte histórica candidata: Yellowstone Geyser / Helius LaserStream

Pesquisa documental de 19/11/2026:

- O protocolo Yellowstone Geyser expõe account updates com `slot`, bytes completos da conta, `write_version` e `txn_signature` opcional. Isso permite associar um post-state ao signature da transação e ordenar updates da mesma conta.
- A documentação Helius descreve LaserStream como compatível com Yellowstone. No nível `processed`, account updates chegam em ordem de produção do validator e podem existir múltiplas atualizações da mesma conta no slot; em `confirmed`, assinantes recebem apenas o estado final. Portanto, para capturar pre/post, a coleta candidata precisa observar `processed` e depois reconciliar/confirmar a transação em commitment superior.
- LaserStream oferece reconexão/replay histórico de até 48 horas. Isso ajuda a recuperar lacunas recentes, mas não substitui arquivo histórico ilimitado nem persistência própria.
- Preprocessed Transactions entrega assinatura, slot, contas e instruções antes da execução, mas não inclui meta, inner instructions/CPI, balances ou resultado de execução. É sinal antecipado, não fonte autoritativa para reconciliação econômica.
- RPC padrão `getAccountInfo` retorna o estado consultado no slot de contexto, não bytes históricos arbitrários. `getTransaction` fornece `preTokenBalances/postTokenBalances`, mas não o TLV bruto `TransferFeeAmount` de cada token account.
- Arquitetura candidata: manter timeline por pubkey de account updates `processed`, armazenando `write_version`, `txn_signature`, slot, owner e bytes; quando chegar um update com assinatura-alvo, parear com o último estado anterior da mesma conta. Confirmar/finalizar a assinatura e descartar atualizações de forks revertidos.
- Usar o stream de transações pós-execução para obter meta/inner instructions e ligar os updates ao parser; Preprocessed pode antecipar o alerta, mas nunca liberar BUY/SELL.
- `getTransactionsForAddress` pode ajudar no backfill de transações, mas não fornece por si só os bytes pre/post de estado das contas.
- Helius LaserStream é candidato, não dependência aprovada nem conectada. A página oficial indica disponibilidade em planos Business ou superiores; confirmar custo/limites no momento da contratação. Manter interface provider-neutral para permitir Yellowstone próprio ou outro serviço compatível.

## Proveniência e integridade dos snapshots históricos

- `DammV2MintPrestate` exige `source_id` igual à origem da transação. O construtor `build_damm_v2_mint_fee_config_snapshots` recebe também o SHA-256 do payload da transação e vincula esses valores a cada snapshot de mint.
- O construtor calcula SHA-256 dos bytes brutos do mint prestate, preserva os próprios bytes no snapshot e deriva `config_state` decodificando esses bytes. Tanto o caminho de cálculo de fee quanto a verificação posterior recalculam o hash e decodificam novamente o TLV; rejeitam hash divergente ou `config_state` que não corresponda aos bytes.
- `verify_damm_v2_mint_fee_config` exige `transaction_source_id` e `transaction_payload_sha256` do contexto da transação. Compara ambos com cada snapshot, além de assinatura, slot, epoch, ordem, mint e posição exata da transferência.
- `DammV2WithheldFeeSnapshot` preserva bytes brutos pre/post, seus SHA-256, source ID, hash do payload da transação e referências separadas dos estados. `verify_damm_v2_withheld_fee_deltas` recalcula os dois hashes, decodifica novamente `TransferFeeAmount` a partir dos bytes e compara o resultado com `decoded_delta` recebido.
- O verifier withheld exige a mesma origem e o mesmo hash do payload transacional, além de assinatura, slot, ordem e `pre < transaction < post`. Snapshot de outra fonte, payload, bytes alterados ou delta que não corresponda aos bytes falha fechado.
- `reconcile_solana_transaction_damm_v2_bundle` propaga `source_id` e SHA-256 da identidade raiz ao reconciliador econômico. O adapter deve usar a mesma identidade ao construir e verificar snapshots.
- Esses hashes provam consistência e integridade dos bytes apresentados, não autenticidade criptográfica do provider nem correção do relógio/ordenação do adapter. A confiança na fonte, no domínio de ordenação e na captura pré/pós continua sendo responsabilidade da camada de ingestão; sem isso, não promover snapshots a VERIFIED.