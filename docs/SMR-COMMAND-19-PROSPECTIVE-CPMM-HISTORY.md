# SMR — Comando 19: histórico prospectivo CPMM com duas capturas reais

**Data:** 2026-11-20. **PR #104 Draft**, base PR #103. **Sem merge na main.**

## Capturas e proveniência

Ambas as observações vieram de um único RPC público (`https://api.mainnet-beta.solana.com`) consultado **uma vez por captura** via `getMultipleAccounts` com `finalized` solicitado, retornando simultaneamente PoolState, AmmConfig, vault HIGH e vault WSOL. Não há comprovação de independência do provedor ou finalização criptograficamente autenticada.

| Evidência | Captura A | Captura B |
|---|---|---|
| Slot RPC declarado | **471856996** | **471860762** |
| Tempo de observação UTC | 2026-11-20 19:37:10.132099 | 2026-11-20 19:50:40.205574 |
| Disponível desde UTC | 2026-11-20 19:37:10.344983 | 2026-11-20 19:50:40.432045 |
| SHA-256 request RAW | `2ee9db161ff7928efee3e21ac4ac93d63daeec3cab22838a94c582b1a10ed718` | mesmo hash, mesmo pedido de quatro contas |
| SHA-256 response RAW | `2645d85a94cdd728f7485929b59fbdd475a1d200cb403c8f4a893e50a8f44562` | `98dc62c09500bfb7b950409905a81a752ecab83e6fb32ba3a98e3938935a8f6a` |
| Coleta real | https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44803809348 | https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44805881701 |
| Arquivamento offline | https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44803965437 | https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44805986093 |

Arquivos RAW de request, response e manifesto preservados separadamente em:

- `data/evidence/mainnet/2026-11-20/prospective-slot-471856996/`
- `data/evidence/mainnet/2026-11-20/prospective-slot-471860762/`

Sem consultas RPC adicionais na etapa de comparação. Assinatura original `23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM` e PoolState `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu` servem somente de vínculo de identidade, **não** provam que o estado observado em 20/11 estava disponível no swap de 18/11, slot `471039497`.

## Variações observadas e classificação

| Indicador | Captura A | Captura B | Delta |
|---|---:|---:|---:|
| Slot | 471856996 | 471860762 | **+3766 slots** |
| Vault HIGH bruto, RAW | 76503529653334 | 76819932659233 | +316403005899 |
| Reserva HIGH efetiva, RAW | 76473066869631 | 76789249151204 | **+316182281573** |
| Vault WSOL bruto, lamports | 257443240033 | 256392143706 | -1051096327 |
| Reserva WSOL efetiva, lamports | 257014075604 | 255961338866 | **-1052736738** |
| Total de taxas acumuladas HIGH (bruto - efetivo), RAW | 30462783703 | 30683508029 | +220724326 |
| Total de taxas acumuladas WSOL (bruto - efetivo), lamports | 429164429 | 430804840 | +1640411 |
| `AmmConfig.trade_fee_rate` | 2500 ppm | 2500 ppm | sem mudança |
| `AmmConfig.creator_fee_rate` | 500 ppm | 500 ppm | sem mudança |

O SHA do PoolState mudou; SHA do AmmConfig não mudou; ambos os vaults mudaram. Os seis buckets de taxas são decodificados e comparados respeitando a orientação token0/token1 (que pode ser diferente de input/output).

**Cobertura: `PARTIAL`.** Há duas observações confiáveis quanto à integridade local dos bytes RPC e comparação determinística, **não** sequência completa de account writes, instruções ou swaps nos 3766 slots intermediários. Nenhum delta é atribuível a um swap específico sem transações/eventos adicionais. Não existe estado `COMPLETE` neste comparador. A reconciliação `SwapEvent` da PR #102 permanece separada e não é preço executável.

## Arquitetura e SQLite

- `services/prospective_cpmm_history.py`: `capture_from_raw` valida os quatro RAWs e o escopo contra o swap original, SHA-256 de pedido/resposta, `available_at` antes do cutoff, seis taxas acumuladas e deriva `capture_id` estável. `compare_captures` classifica `PARTIAL`, `UNKNOWN` ou `CONFLICT`; um mesmo slot não prova mudança, slots invertidos e resposta após cutoff são conflitos, e a fonte permanece não autenticada independentemente.
- `storage/cpmm_prospective_history.py`: SQLite **append-only**, independente do banco de transações; campos incluem ID, pool, slot, fonte e endpoint, observação/disponibilidade, hashes, bytes RAW exatos, manifesto, versão do decodificador, ID da captura anterior, cobertura e integridade. Reabertura/replay idempotente, rejeição de regravação divergente e `PRAGMA integrity_check`.
- *Importante:* `OBSERVED` no cadastro de uma captura significa apenas que o snapshot foi obtido; `PARTIAL` na comparação significa que não há garantia de cobertura do intervalo. `UNKNOWN` quando faltam prova/slot/ordem; `CONFLICT` para dados inconsistentes. Nem a igualdade de slots nem um intervalo de um slot permitem declarar `COMPLETE`.

## Validação

**942 testes aprovados, zero falhas e compileall**, SHA de código `814a064caee6b7e10e323dac8aa9ae532f07551d`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44806434023.

Testes cobrem os dois RAWs reais, hashes fixos, slots iguais e invertidos, pool, vault e config divergentes, RAW adulterado, resposta incompleta, cutoff, taxa acumulada, provedor não independente, determinismo, append-only/idempotência e SQLite após reinício. A primeira execução de integração revelou cinco problemas de implementação/teste, todos corrigidos antes da CI acima; não confundir seus resultados com o marco final.

## Próxima prioridade

Adicionar um **reconciliador de diferenças de snapshots com recibos assinados de mudanças de contas** apenas quando existir fonte que garanta sequência consistente de atualizações. No momento, aumentar o número de capturas isoladas ajuda a medir tendências entre observações, mas **não** converte intervalos em cobertura completa. Preservar a ordem, a proveniência e o cutoff, sem VPS, custos, operações financeiras ou merge em `main`.
