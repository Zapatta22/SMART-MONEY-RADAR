# Meteora DAMM v2 — decoder EvtSwap2

## Escopo

Decoder offline e determinístico do payload completo de instrução Anchor event-CPI para `EvtSwap2`. O módulo não reconstrói a hierarquia CPI, não associa o evento a uma instrução externa, não reconcilia transferências e não cria `SwapObservation`, classificação BUY/SELL ou sinal de trading.

## Fonte de schema fixada

- Repositório oficial: `MeteoraAg/damm-v2-sdk`.
- Arquivo: `src/idl/cp_amm.json`.
- Commit do IDL: `eab5e8aaa951418db43abbac471d9762b2005f11`.
- Metadata do IDL: `cp_amm` versão `0.2.5`.
- Programa: `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`.
- Evento IDL `EvtSwap2` discriminator: `[189, 66, 51, 168, 38, 80, 117, 153]`.
- Envelope Anchor event-CPI: `[29, 154, 203, 81, 46, 165, 69, 228]`.

A fonte IDL é fixada para reprodutibilidade. Antes de habilitar ingestão em produção, ainda será necessário confirmar que a versão do programa implantada no intervalo de slots monitorado emite exatamente esse schema. O decoder não tenta adivinhar versões antigas.

## Layout Borsh atual

O payload recebido é a instrução self-CPI completa:

| Offset | Tamanho | Campo |
|---:|---:|---|
| 0 | 8 | Anchor event discriminator |
| 8 | 8 | EvtSwap2 discriminator |
| 16 | 32 | pool (Pubkey) |
| 48 | 1 | trade_direction |
| 49 | 1 | collect_fee_mode |
| 50 | 1 | has_referral (Borsh bool) |
| 51 | 8 | params.amount_0 |
| 59 | 8 | params.amount_1 |
| 67 | 1 | params.swap_mode |
| 68 | 8 | swap_result.included_fee_input_amount |
| 76 | 8 | swap_result.excluded_fee_input_amount |
| 84 | 8 | swap_result.amount_left |
| 92 | 8 | swap_result.output_amount |
| 100 | 16 | swap_result.next_sqrt_price (u128) |
| 116 | 8 | swap_result.claiming_fee |
| 124 | 8 | swap_result.protocol_fee |
| 132 | 8 | swap_result.compounding_fee |
| 140 | 8 | swap_result.referral_fee |
| 148 | 8 | included_transfer_fee_amount_in |
| 156 | 8 | included_transfer_fee_amount_out |
| 164 | 8 | excluded_transfer_fee_amount_out |
| 172 | 8 | current_timestamp |
| 180 | 8 | reserve_a_amount |
| 188 | 8 | reserve_b_amount |

Comprimento esperado: 196 bytes (16 bytes de envelope + 180 bytes de body).

## Enumerações validadas

- `trade_direction`: 0 = A→B; 1 = B→A.
- `collect_fee_mode`: 0 = BothToken; 1 = OnlyB; 2 = Compounding.
- `swap_mode`: 0 = ExactIn; 1 = PartialFill; 2 = ExactOut.

Os valores são preservados como inteiros raw. O decoder não transforma direção do pool em BUY/SELL de carteira.

## Regras fail-closed

- Exige exatamente 196 bytes; dados truncados, anexados ou de schema legado são rejeitados.
- Exige os dois discriminators corretos.
- Exige Borsh bool estrito (somente 0 ou 1).
- Rejeita direções, modos de coleta e modos de swap desconhecidos.
- Lê u64/u128 little-endian sem conversão para float.
- Converte o Pubkey de 32 bytes para Base58.
- O schema atual usa `claiming_fee` + `compounding_fee`. Layout legado com `partner_fee` não é aceito.

## Limites e próxima integração

O resultado tipado é apenas o evento decodificado. Para associá-lo a uma operação:
1. identificar a instrução externa `swap`/`swap2` do programa DAMM v2;
2. demonstrar que a instrução do evento é self-CPI descendente daquela instrução;
3. validar a hierarquia CPI completa e os índices;
4. obter contas/mints/vaults da instrução externa e estado/epoch quando necessário.

Se qualquer elo CPI estiver ausente ou inconsistente, a associação deve permanecer incompleta. O evento, isoladamente, não prova quem foi o trader, nem substitui transferências Token-2022, deltas por conta ou reconciliação econômica.

Nenhum RPC, Helius, SQLite, checkpoint, RAW fixture ou operação on-chain é executado por este módulo.
