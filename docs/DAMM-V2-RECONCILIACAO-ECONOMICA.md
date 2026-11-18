# DAMM v2 — Especificação de reconciliação econômica por operação

Status: **especificação em elaboração; nenhum reconciliador econômico implementado**  
Escopo: instruções swap e swap2 no Meteora DAMM v2, evento EvtSwap2, transferências SPL/Token-2022 e deltas de token accounts.

## 1. Objetivo e regra de segurança

O objetivo é provar, individualmente, quais quantidades de cada ativo foram debitadas do usuário, creditadas ao vault, debitadas do vault e creditadas ao usuário em uma operação DAMM v2. Só depois dessa prova poderá existir um resultado econômico MATCHED e, em etapa posterior, um SwapObservation.

A associação estrutural swap ↔ EvtSwap2 e a atribuição estrutural de transferências são pré-condições, não prova econômica. Os estados ATTRIBUTED, FOUR_ACCOUNT_DELTAS_PRESENT e AUDITED nunca podem ser promovidos automaticamente a MATCHED.

Fail-closed: qualquer campo ausente, semântica não comprovada, divergência, ambiguidade, taxa não decodificada, conta compartilhada sem atribuição exata ou transferência reutilizada impede MATCHED.

## 2. Base documental e versão

- Decoder atualmente fixado ao código oficial MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e.
- Documentação oficial de eventos: https://github.com/MeteoraAg/docs/blob/main/developer-guides/damm-v2/program/events.mdx
- Documentação oficial de instruções: https://github.com/MeteoraAg/docs/blob/main/developer-guides/damm-v2/program/instructions.mdx
- Rust SDK e quote helpers: https://github.com/MeteoraAg/docs/blob/main/developer-guides/damm-v2/rust-integration/library.mdx

A documentação publicada atualmente confirma os significados dos parâmetros por modo e descreve os campos de EvtSwap2. Ela não substitui a inspeção do código-fonte fixado que gerou uma transação histórica. Mudanças posteriores na documentação ou no programa não podem ser aplicadas retroativamente sem versionamento.

## 3. Semântica dos modos

| Modo | params.amount_0 | params.amount_1 | Tratamento |
|---|---|---|---|
| EXACT_IN | Entrada solicitada | Saída mínima | Não assumir que o parâmetro é o débito bruto do usuário nem que output_amount é o crédito líquido final. |
| PARTIAL_FILL | Entrada solicitada | Saída mínima | amount_left representa entrada não utilizada segundo a documentação; não calcular entrada executada por subtração até validar semântica e taxas no código da versão fixada. |
| EXACT_OUT | Saída desejada | Entrada máxima | Não inverter os campos nem interpretar amount_0 como entrada. Validar a saída econômica efetiva e a entrada efetivamente debitada, incluindo transfer fees. |

O swap legado é tratado estruturalmente como exact-in: amount_in e minimum_amount_out. Sua quantidade executada também depende de confirmação pelas evidências da transação.

### Campos de resultado

- included_fee_input_amount e excluded_fee_input_amount: preservar separadamente; não assumir equivalência com débito do usuário, crédito do vault ou quantidade que moveu a curva sem validar a implementação da versão.
- amount_left: preservar como valor bruto do evento; nunca converter isoladamente em entrada executada.
- output_amount: preservar como valor do evento; a documentação atual o descreve antes dos efeitos externos de transfer fee.
- included_transfer_fee_amount_in, included_transfer_fee_amount_out e excluded_transfer_fee_amount_out: preservar individualmente; não somar/subtrair até a semântica exata de cada caminho de token program ser demonstrada.
- claiming_fee, protocol_fee, compounding_fee, referral_fee: componentes distintos. Não somar duas representações do mesmo componente nem presumir que todos são transferências separadas.
- reserve_a_amount e reserve_b_amount: snapshots pós-swap do pool; são evidência contextual, não substituem deltas atribuídos por operação.

## 4. Livro de quantidades obrigatório

A reconciliação deve produzir uma linha independente para cada lado do swap, com inteiros em unidades raw e mint/decimals explícitos:

1. User input debit — débito bruto observado na conta de entrada do usuário.
2. Input vault credit — crédito líquido observado no vault de entrada.
3. Output vault debit — débito bruto observado no vault de saída.
4. User output credit — crédito líquido observado na conta de saída do usuário.
5. Input transfer fee / withheld — taxa de transferência efetivamente retida no caminho de entrada, se aplicável.
6. Output transfer fee / withheld — taxa de transferência efetivamente retida no caminho de saída, se aplicável.
7. AMM fee components — componentes do evento, mantidos separados das transfer fees do Token Program.

As quatro contas devem ser distintas para uma operação simples. Se papéis colidirem, ou se uma conta for compartilhada por mais de uma operação na mesma transação, a atribuição deve ser demonstrada por transferências individuais e ordenadas. Deltas preTokenBalances/postTokenBalances são agregados por transação e não podem ser rateados proporcionalmente nem atribuídos por heurística.

## 5. Requisitos SPL Token e Token-2022

- Resolver token program, mint, decimals, source e destination para cada transferência.
- TransferChecked exige consistência de mint e decimals.
- Transfer sem mint/decimals demonstráveis permanece incompleto.
- Para Token-2022, decodificar explicitamente a instrução com fee (incluindo TransferCheckedWithFee, quando presente), o valor de fee e o estado/contabilidade de withheld amount aplicável.
- Não tratar o valor enviado como valor recebido líquido.
- Não deduzir taxa apenas pela diferença entre transfer amount e saldo do destinatário.
- Validar a taxa do evento contra a transferência e contra o efeito líquido/withheld observado.
- Extensões de transfer hook, confidential transfer, ou qualquer extensão não suportada devem bloquear MATCHED.

## 6. Exclusividade e ordem

Cada transferência e cada efeito de saldo usado na prova deve ser consumido por no máximo uma operação.

Atribuição exige:
- mesma transação e mesmo grupo de instrução externa;
- caminho CPI descendente demonstrável, stack height confiável e ordem anterior ao EvtSwap2, conforme o fluxo do programa;
- pares exatos de contas e mint;
- pool e vaults consistentes com o mapeamento de contas;
- ausência de candidatos concorrentes;
- nenhuma transferência compartilhada/reutilizada.

Quando houver swaps sequenciais no mesmo pool, a ordem das instruções e os eventos individuais devem ser preservados. Deltas finais do vault agregam todos os efeitos da transação; não provam isoladamente o delta de cada swap. Sem trilha individual completa que permita reconciliar cada operação sem resíduo, todas as operações afetadas permanecem não reconciliadas.

Transferências adicionais para taxas, referral, hooks, contas intermediárias, criação/fechamento de token accounts ou outras instruções que afetem os mesmos saldos devem ser identificadas. Se não puderem ser atribuídas exatamente, o resultado é inconclusivo.

## 7. Critérios mínimos para MATCHED econômico

Um swap só pode receber MATCHED quando todos forem verdadeiros:

1. Instrução DAMM v2 e EvtSwap2 associados univocamente.
2. Pool, direção, mints, token programs, contas e decimals resolvidos sem conflito.
3. Modo e parâmetros decodificados e coerentes com a versão do programa.
4. Quatro efeitos econômicos (débito do usuário, crédito do vault de entrada, débito do vault de saída e crédito do usuário) demonstrados em unidades raw.
5. Transfer fees e withheld amounts, quando existentes, decodificados e reconciliados nos dois lados.
6. Componentes de fee do AMM tratados sem dupla contagem.
7. Transferências e efeitos usados são exclusivos desta operação; nenhum efeito foi reutilizado.
8. Restrições do modo respeitadas (mínimo de saída, máximo de entrada e tratamento de preenchimento parcial), sem inferir quantidades executadas a partir dos limites solicitados.
9. Não há resíduo inexplicado, snapshot ausente, falha de transação ou efeito externo não atribuído.

Se qualquer condição falhar: INCOMPLETE, AMBIGUOUS, UNRESOLVED ou novo estado negativo específico; nunca MATCHED por aproximação.

## 8. Matriz de testes sintéticos obrigatória

Criar fixtures sintéticas isoladas, com valores raw pequenos e conhecidos, cobrindo:

- ExactIn: direção A→B e B→A, com e sem transfer fee em cada lado.
- PartialFill: consumo integral e parcial; amount_left coerente e incoerente; fee on input e fee on output quando suportados pela configuração.
- ExactOut: ambos os sentidos; saída solicitada, entrada máxima, entrada efetiva e transfer fees.
- Token-2022: transfer fee explícita, TransferCheckedWithFee, withheld amount coerente, divergente e ausente.
- Duas ou mais operações no mesmo grupo externo, mesmo pool, vault compartilhado e contas de usuário compartilhadas.
- Transferência candidata duplicada, fora de ordem, fora do caminho CPI, reutilizada ou concorrente.
- Deltas pre/post ausentes, parciais, duplicados, mint/decimals divergentes e sinais incorretos.
- Transferências não relacionadas que afetam as mesmas contas.
- Evento ausente, duplicado, ambíguo, pool divergente e transação falha.

Cada teste positivo deve provar todas as equações com números inteiros raw e ausência de resíduo. Cada teste negativo deve provar que não há MATCHED.

## 9. Separação entre evidência, reconciliação e domínio

- Decoders produzem evidências estruturadas.
- Analisadores associam instrução, evento, contas e transferências.
- O reconciliador econômico compara quantidades e taxas por operação.
- Somente um resultado econômico comprovado pode alimentar um adaptador DAMM v2 para SwapObservation, SwapClassification e SwapEvidence.
- Não reutilizar automaticamente o pipeline CPMM: compartilhar contratos de domínio não significa compartilhar regras de reconciliação.
- Não criar persistência, checkpoint ou execução on-chain nesta etapa.

## 10. Estado atual observado nos cinco RAW locais

Auditoria local redigida concluída em 18/11/2026:
- Fixture 1: uma operação estruturalmente associada e uma transferência atribuída; cobertura de delta DELTA_SIGN_MISMATCH; revisão de transfer fee requerida.
- Fixture 3: uma operação estruturalmente associada e uma transferência atribuída; cobertura de delta SNAPSHOT_SET_INCOMPLETE.
- Fixture 2: nenhum swap DAMM v2 reconhecido no escopo atual; uma issue global de delta.
- Fixtures 4 e 5: nenhum swap DAMM v2 reconhecido no escopo atual.
- Nenhuma operação obteve reconciliação econômica comprovada.

Esses resultados não autorizam correção por inferência, importação ou geração de SwapObservation.

## 11. Próxima implementação — ainda não iniciada

1. Auditar no commit oficial fixado os caminhos de swap, swap2, exact-in, partial-fill, exact-out, transfer-fee input/output e collect-fee mode.
2. Construir uma tabela de equações por token program e modo, com origem exata de cada campo.
3. Implementar decoder de transfer fee/withheld Token-2022 e testes isolados.
4. Implementar reconciliador puro, sem banco/rede, com atribuição exclusiva e resultado negativo explícito.
5. Validar fixtures sintéticas; somente depois executar auditoria local redigida dos RAW.
6. Só então avaliar adaptador para contratos de domínio.

Até a conclusão desses passos, MATCHED deve significar apenas associação estrutural nos módulos já existentes, nunca reconciliação econômica.

## 12. Auditoria das equações no código oficial fixado

Auditoria direta do código MeteoraAg/damm-v2@18936b18c26708f6e9b52cacc01ea2f99868ba8e confirmou os comportamentos abaixo. Arquivos centrais: programs/cp-amm/src/instructions/swap/swap_exact_in.rs, swap_partial_fill.rs, swap_exact_out.rs, state/pool.rs, state/fee.rs, utils/token.rs e instructions/swap/ix_p_swap.rs.

### 12.1 Semântica dos valores de entrada

- included_transfer_fee_amount_in é o valor bruto passado à transferência do usuário para o vault.
- SwapResult2.included_fee_input_amount é a entrada líquida recebida pelo pool após a transfer fee Token-2022, mas antes de excluir a taxa de negociação do AMM.
- SwapResult2.excluded_fee_input_amount é a entrada após a taxa de negociação do AMM, usada no cálculo/reserva da curva.
- A transferência Token-2022 não é codificada pelo programa Meteora como uma instrução especial TransferCheckedWithFee. O código invoca TransferChecked; o Token-2022 aplica a TransferFeeConfig do mint. Portanto, não exigir opcode separado para reconhecer a taxa. É necessário decodificar a transferência e validar a configuração/epoch e o withheld amount correspondente.

### 12.2 EXACT_IN

1. amount_0 é transferido em bruto do usuário; calculate_transfer_fee_excluded_amount calcula o crédito líquido do vault.
2. Esse valor líquido é entregue a get_swap_result_from_exact_input.
3. included_fee_input_amount corresponde ao valor líquido de entrada antes da taxa AMM; excluded_fee_input_amount corresponde ao valor após a taxa AMM.
4. output_amount é o valor bruto enviado pelo vault de saída ao usuário, antes da transfer fee externa.
5. excluded_transfer_fee_amount_out é o crédito líquido esperado ao destinatário depois da transfer fee.
6. A saída mínima é validada contra esse crédito líquido.

### 12.3 PARTIAL_FILL

1. amount_0 é o limite bruto solicitado; primeiro é convertido em entrada líquida após a transfer fee.
2. A função de curva retorna amount_left e a saída. Quando existe entrada não consumida, o código subtrai amount_left do montante disponível após a taxa AMM e reconstrói a entrada com taxa AMM incluída, quando a taxa é cobrada no input.
3. Quando amount_left == 0, included_fee_input_amount é o montante de entrada líquido disponibilizado ao pool.
4. O montante bruto realmente transferido do usuário é recalculado com calculate_transfer_fee_included_amount sobre included_fee_input_amount; portanto, não é necessariamente todo amount_0.
5. amount_left não é valor devolvido ao usuário: a transferência é dimensionada ao consumo efetivo, deixando o restante na conta do usuário.
6. A saída é transferida em bruto e excluded_transfer_fee_amount_out é validado contra o mínimo de saída.

### 12.4 EXACT_OUT

1. amount_0 é a saída líquida desejada pelo usuário.
2. calculate_transfer_fee_included_amount converte essa saída líquida no valor bruto que o vault deve transferir; esse valor é included_transfer_fee_amount_out.
3. O cálculo do AMM determina a entrada necessária. included_fee_input_amount é a entrada antes de excluir a taxa AMM; excluded_fee_input_amount é a entrada após a taxa AMM.
4. A entrada bruta do usuário é calculada com calculate_transfer_fee_included_amount sobre included_fee_input_amount; esse valor é included_transfer_fee_amount_in e precisa ser menor ou igual a amount_1 (máximo bruto de entrada).
5. excluded_transfer_fee_amount_out é igual ao amount_0 líquido solicitado.
6. amount_left é zero no resultado exact-out produzido pelo código.

### 12.5 Taxa AMM, modo de cobrança e referral

- FeeMode::get_fee_mode deriva se as taxas são cobradas no input ou output a partir de CollectFeeMode e direção. Logo, a reconciliação precisa conhecer collect_fee_mode, trade_direction e has_referral; não basta conhecer o modo ExactIn/PartialFill/ExactOut.
- claiming_fee, protocol_fee, compounding_fee e referral_fee são componentes do cálculo de taxa AMM, não transfer fees Token-2022.
- claiming_fee e compounding_fee participam do accounting do pool; protocol_fee é contabilizado internamente no pool; referral, quando ativo, causa uma transferência adicional do vault para a conta referral, no token determinado por fees_on_token_a.
- O débito do vault não pode ser reconciliado olhando apenas a transferência principal de saída: a transferência referral e a forma de cobrança da taxa alteram o efeito total do vault. A transferência referral deve ser identificada e atribuída separadamente.
- apply_swap_result atualiza as reservas internas do pool com regras próprias para fee-on-input/output e adiciona compounding fee ao token B. As reservas do evento são snapshots pós-swap, não substitutos dos movimentos de token accounts.

### 12.6 Limite probatório Token-2022

O código Meteora calcula a transfer fee a partir da TransferFeeConfig do mint no epoch corrente e invoca TransferChecked. O crédito líquido do destinatário e o withheld amount pertencem a campos distintos do estado do token account. Os deltas padrão preTokenBalances/postTokenBalances mostram o saldo spendable, não bastam sozinhos para provar todos os campos withheld nem a configuração histórica do mint. Sem estado/configuração histórica válida no epoch da transação e evidência de withheld, manter o caso Token-2022 em estado não reconciliado.

### 12.7 Equações mínimas a validar por operação

Definições: G_in = included_transfer_fee_amount_in; N_in = included_fee_input_amount; A_in = excluded_fee_input_amount; G_out = included_transfer_fee_amount_out; N_out = excluded_transfer_fee_amount_out.

- Entrada: débito bruto da conta do usuário = G_in; crédito spendable do vault = N_in; diferença = transfer fee de entrada, comprovada pela configuração/estado Token-2022 ou zero para SPL Token.
- Saída principal: débito bruto do vault = G_out; crédito spendable do usuário = N_out; diferença = transfer fee de saída, comprovada ou zero para SPL Token.
- Taxa AMM de entrada, quando fees_on_input: diferença entre N_in e A_in precisa ser explicada pelos componentes de fee e regras de rounding do programa.
- Saídas adicionais (referral) são transferências separadas e devem ser reconciliadas à parte; não devem ser confundidas com G_out.
- Para taxas cobradas no output, o accounting de reserva inclui componentes AMM além da transferência principal. A igualdade de deltas do vault com a transferência principal isolada não é um invariante válido.

Essas relações foram derivadas do código fixado, mas ainda precisam ser implementadas como testes sintéticos com arredondamento, ambos os sentidos, três modos e todas as combinações de FeeMode. Nenhum reconciliador foi implementado; nenhum RAW foi alterado ou enviado.

### 12.8 Confirmação da semântica withheld no Token-2022

A documentação oficial Solana confirma que TransferChecked também aplica automaticamente a TransferFeeConfig e retém a taxa na extensão TransferFeeAmount da conta de destino. TransferCheckedWithFee é outra variante que permite validar uma taxa informada pelo chamador; ela não é obrigatória para reconhecer uma transferência DAMM v2 porque a implementação fixada usa TransferChecked.

Consequências para o SMR:
- O delta spendable do destinatário é o valor líquido; o withheld_amount é um campo separado da extensão da token account.
- A diferença entre débito bruto e crédito spendable deve coincidir com a taxa calculada pela configuração de mint ativa no epoch da transação, e com a variação de withheld_amount atribuível àquela transferência.
- Se houver mais de uma transferência para a mesma conta na transação, o withheld_amount final agregado não pode ser atribuído a uma transferência isolada sem estado anterior e sequência de instruções confiável.
- O RPC getTransaction padrão não fornece snapshots arbitrários do estado bruto de mint/token accounts antes e depois da transação. Se os dados históricos necessários não estiverem disponíveis por uma fonte de estado indexada/confiável, o caso permanece INCOMPLETE; não reconstruir withheld por aproximação.
- Não inferir o epoch/configuração histórica a partir da configuração atual do mint.

Fonte oficial: https://solana.com/docs/tokens/extensions/transfer-fees
