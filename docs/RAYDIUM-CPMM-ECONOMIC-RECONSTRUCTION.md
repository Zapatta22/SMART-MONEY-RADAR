# Raydium CPMM — reconstrução econômica por operação

## Objetivo

Transformar a identificação estrutural de uma instrução CPMM em uma operação econômica individual somente quando os valores e a carteira puderem ser atribuídos com evidência on-chain suficiente. Uma transação pode conter vários swaps; cada swap deve manter identidade independente por `(chain, signature, instruction_index, cpi_path)`.

Esta etapa não autoriza execução de ordens. O resultado continua sendo observacional e read-only.

## Estado das camadas existentes

- `raydium_cpmm_decoder.py`: reconhece `SwapBaseInput` e `SwapBaseOutput` e decodifica os argumentos.
- `raydium_cpmm_accounts.py`: resolve as 13 contas-base, incluindo token accounts do lado do usuário e vaults do pool.
- `raydium_cpmm_analyzer.py`: localiza instruções CPMM externas e CPI, preservando índice externo, índice linear interno, `stackHeight` e `cpi_path`.
- `transaction_parser.py` / `domain/normalization.py`: atualmente produzem deltas agregados por carteira e mint. Isso não atribui um delta a cada swap.
- PR #4 já propõe persistência atômica/idempotente de `SwapObservation`, `SwapClassification` e `SwapEvidence`; não duplicar essa camada.

## Princípio de segurança

**Não converter argumentos da instrução em quantidades executadas.** `minimum_amount_out` e `max_amount_in` são limites; `amount_out` em exact-output é uma quantidade solicitada, não prova isolada de recebimento. A observação econômica deve vir das transferências executadas e/ou dos deltas de saldo ligados às contas exatas da operação.

**Não converter deltas agregados da carteira em swaps individuais.** Se uma transação tiver dois swaps do mesmo mint, um delta líquido da carteira não revela quanto pertence a cada um.

Quando a atribuição não for inequívoca, não criar `SwapObservation`. Registrar diagnóstico/evidência parcial e manter classificação `UNKNOWN` somente se houver uma observação econômica válida que possa ser formada; caso contrário, não persistir uma operação econômica.

## Evidências que precisam ser correlacionadas

1. **Identidade da instrução CPMM**
   - Assinatura e índice da instrução externa.
   - Caminho CPI e profundidade, quando fornecidos.
   - Programa Raydium CPMM, discriminator e tipo da instrução.
   - `pool_state`, token accounts do usuário, vaults, token mints e token programs.

2. **Transferências SPL / Token-2022 executadas**
   - Inspecionar `meta.innerInstructions` e instruções externas relevantes.
   - Suportar transferências `transfer` e `transferChecked` quando parseadas pelo RPC e, em fase posterior, seus formatos compilados.
   - Preservar programa token, source, destination, authority, mint quando disponível, quantidade bruta, decimals, índice linear, índice externo e trilha CPI.
   - Não confundir valor bruto transferido com valor líquido recebido quando houver transfer-fee/Token-2022.

3. **Deltas por token account**
   - Ler `preTokenBalances` e `postTokenBalances` por `accountIndex`, não somente por owner/mint agregado.
   - Usar `uiTokenAmount.amount` como inteiro decimal bruto e `decimals` validado; não usar float.
   - Validar que mint e decimals correspondem ao token mint esperado pelo swap.
   - Ausência de um lado só pode ser tratada como saldo zero quando a estrutura RPC completa e a presença do accountIndex no outro lado sustentarem criação/fechamento da conta. Se os arrays estiverem ausentes/incompletos, não inferir zero.
   - Preservar owner e accountIndex como evidência; não assumir que `payer` é sempre o dono econômico dos tokens.

4. **Atribuição de carteira**
   - A carteira monitorada deve vir do contexto de observação do SMR e/ou de owner/authority comprovado nas contas/transferências.
   - Não atribuir automaticamente `wallet_address = payer`; fee payer, signer, authority e proprietário econômico podem ser entidades diferentes.
   - Se não houver vínculo comprovado entre a operação e a carteira monitorada, não gerar observação para essa carteira.

## Correlação proposta

- Para cada swap CPMM, construir um candidato de fluxo de entrada esperado: token account de entrada do usuário → vault de entrada.
- Construir o fluxo de saída esperado: vault de saída → token account de saída do usuário.
- Correlacionar as transferências ao subtree CPI da instrução CPMM usando o prefixo de `cpi_path` e `stackHeight`. Sem hierarquia comprovável, não atribuir transferência a uma instrução por proximidade linear.
- Validar source/destination, mint, token program e ordem de execução. Não aceitar apenas coincidência de valor.
- Obter quantidade de entrada a partir do débito efetivo do token account de entrada do usuário; quantidade de saída a partir do crédito efetivo no token account de saída do usuário, ajustando a interpretação para taxas de transferência.
- Detectar reutilização de token accounts e múltiplos fluxos candidatos. Se duas operações puderem reivindicar a mesma transferência ou o mesmo delta, marcar ambas como ambíguas em vez de dividir ou duplicar quantidades.
- Manter swaps separados mesmo quando pertencem à mesma assinatura e à mesma carteira.

## Critérios mínimos para emitir SwapObservation

Todos devem ser verdadeiros:

- Instrução CPMM decodificada sem erro e transação bem-sucedida.
- Identidade da operação determinística e única.
- Input/output mint distintos e comprovados pelas contas/instrução.
- Débito de input e crédito de output positivos, finitos e atribuídos à operação.
- Transferências e/ou deltas correspondentes às contas corretas, sem dupla contagem.
- Carteira monitorada atribuída por evidência, não por suposição.
- Nenhuma ambiguidade não resolvida por conta reutilizada, múltiplas operações, CPI incompleto ou payload RPC parcial.

Se qualquer requisito falhar, a camada deve falhar de forma conservadora: sem quantidades inventadas, sem BUY/SELL forçado e sem persistência de uma observação econômica incompleta.

## Integração posterior

Quando uma operação estiver completa:

1. Gerar `operation_id` com `build_swap_operation_id(chain, signature, instruction_index, cpi_path)`.
2. Criar `SwapObservation` com quantidades efetivamente atribuídas.
3. Criar `SwapEvidence` com programa, venue, índices, CPI path e referências às evidências usadas.
4. Classificar BUY/SELL somente quando o ativo de referência e a direção forem comprovados; caso contrário, `UNKNOWN` com motivo explícito.
5. Persistir o bundle atomicamente usando a implementação existente proposta no PR #4, após sua integração e revisão.

## Plano de validação

- Testes sintéticos unitários para transfer, transferChecked, raw amount/decimals, token account criado/fechado, transfer-fee, CPI aninhado, múltiplos swaps na mesma transação, account reuse, dados ausentes e carteira não comprovada.
- Fixtures reais anonimizadas de mainnet, com payload RPC completo e proveniência preservada, para cada caminho CPMM aceito.
- Comparar reconstrução com token balance deltas e instruções de transferência independentes; toda divergência deve impedir a emissão de observação.
- Somente após fixtures reais aprovadas considerar integração com normalização e persistência.

## Não objetivos desta etapa

- Não executar swaps, assinar transações ou enviar ordens.
- Não calcular preço USD, PnL ou rentabilidade a partir de quantidades isoladas.
- Não inferir liquidez, volume ou propriedade de carteira sem fonte.
- Não substituir fixture real por fixture sintética.

## Decoder de transferências — primeiro incremento

Foi adicionado `solana_token_transfer_decoder.py` para extrair instruções base `Transfer` (opcode 3) e `TransferChecked` (opcode 12) dos programas SPL Token e Token-2022. O decoder aceita dados compilados em Base58 e instruções `jsonParsed`, resolve account keys estáticas/loaded, e preserva programa, source/destination/authority, mint, amount bruto, decimals, índice externo, índice interno, stackHeight, cpi_path e status de execução.

Limites atuais: não decodifica `TransferCheckedWithFee` nem outras instruções de extensão Token-2022; amount bruto da instrução não deve ser tratado como valor líquido recebido em tokens com taxa. Ainda não correlaciona transferências a swaps nem calcula quantidades econômicas.

Referências oficiais consultadas:
- Solana — Transfer tokens: https://solana.com/docs/tokens/basics/transfer-tokens
- Token-2022 — compatibilidade byte a byte das instruções base: https://github.com/solana-labs/solana-program-library/blob/master/docs/src/token-2022.md
- SPL Token instruction source: https://github.com/solana-program/token/blob/main/interface/src/instruction.rs
