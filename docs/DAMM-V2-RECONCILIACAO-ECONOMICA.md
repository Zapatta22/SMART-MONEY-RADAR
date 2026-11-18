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
