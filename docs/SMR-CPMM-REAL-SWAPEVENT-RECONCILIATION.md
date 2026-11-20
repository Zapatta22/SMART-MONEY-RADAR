# SMR — Comando 17: evidência SwapEvent CPMM real e reconciliação inteira

**Data:** 2026-11-20. **PR:** #102 Draft, base #101, `main` preservada. Sem novas consultas RPC, Helius, VPS ou operações financeiras.

## Inventário original (antes de qualquer consulta)

- Transação real preservada em `data/evidence/mainnet/2026-11-20/23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM.raw.json`.
- SHA-256 RAW: `3325222e2c33f6735432f12065b348b4657ae9cfc2c1141061c7c78639724dad`; primeira observação disponível **20/11/2026 18:24:55.131940 UTC**. Evento on-chain no slot **471039497** em 18/11/2026.
- Pool Raydium CPMM `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`; `SwapBaseInput` #3, vault HIGH `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`, vault WSOL `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`. Endereços, mints e deltas de transação já confrontados na PR #101.
- Segunda fonte PublicNode: `result:null`, sem prova adicional; terceira fonte RpcNode: erro HTTP. Sem evidência histórica independente de PoolState/AmmConfig.
- Decodificadores já existentes (reutilizados, não reimplementados): `domain/cpmm_binary_state.py` (PoolState + AmmConfig, incluindo taxas acumuladas), `domain/cpmm_pool_config_envelope.py`, `domain/cpmm_vault_account_check.py`, `domain/cpmm_reserve_snapshot.py`, `data_sources/raydium_cpmm_analyzer.py`, `services/historical_cpmm_state.py`.
- RAW original **não contém** binários persistentes completos de PoolState/AmmConfig ou snapshots autênticos de vault pré-instrução; contém `meta.logMessages` e transferências CPI. As fixtures anonimizadas do repositório são apenas testes, não snapshots históricos verificáveis desta transação.

## Evidência nova localizada nos logs da transação real

A linha `Program data:` encontrada **dentro da invocação do programa CPMM** possui evento Anchor `SwapEvent`, com 170 bytes, discriminador `sha256('event:SwapEvent')[:8]`. O hash SHA-256 do binário decodificado é:

`ffa65f6423fd8462f3d1941cbf59aaadb53dab7521c942086a817f94dbf7f702`.

A estrutura segue o repositório oficial `raydium-io/raydium-cp-swap`, `programs/cp-swap/src/states/events.rs`, e a fórmula inteira de `curve/{calculator,constant_product,fees}.rs`:

| Campo real do SwapEvent | Unidades RAW | Unidade humana |
|---|---:|---:|
| `input_vault_before` (reserva efetiva declarada pelo evento) | 62.350.461.617.001 | 62.350.461,617001 HIGH |
| `output_vault_before` (reserva efetiva declarada pelo evento) | 311.084.308.598 | 311,084308598 WSOL |
| `input_amount` | 19.727.477.255 | 19.727,477255 HIGH |
| `output_amount` | 98.099.917 | 0,098099917 WSOL |
| `trade_fee` | 49.318.694 | 49,318694 HIGH |
| `creator_fee` | 49.075 | 0,000049075 WSOL |
| `input_transfer_fee` / `output_transfer_fee` | 0 / 0 | Nenhuma taxa de transferência indicada |
| `base_input` / `creator_fee_on_input` | true / false | Swap com input exato e taxa do criador na saída |

### Reconciliação inteira observada, sem taxa presumida

```text
input_liquido = 19.727.477.255 - 49.318.694 = 19.678.158.561 HIGH (raw)
saída_bruta = floor(19.678.158.561 × 311.084.308.598
                    / (62.350.461.617.001 + 19.678.158.561))
            = 98.148.992 WSOL (lamports)
saída_líquida = 98.148.992 - 49.075
              = 98.099.917 lamports = 0,098099917 WSOL
diferença versus evento e vault de saída = ZERO
```

A taxa trade observada é **compatível** com 2.500 partes por milhão (0,25%) e a taxa de criador em saída é **compatível** com 500 partes por milhão (0,05%) sob `ceil` de Raydium. Isso é inferência da transação, **não** verificação da configuração `AmmConfig` no slot. Não atribuir taxas protocol/fund/creator acumuladas por bucket sem PoolState histórico.

**Distinção histórica:** `preTokenBalances` em `meta` representa o início da transação, enquanto `SwapEvent.input_vault_before/output_vault_before` são os valores de reserva efetiva que o próprio programa **declarou imediatamente antes do swap**. Diferenças RAW entre saldos da transação e reservas de evento: 17.548.122.126 HIGH e 2.507.270.204 WSOL (unidades mínimas). Não interpretar essa diferença como repartição comprovada dos buckets de taxas sem snapshot binário.

## Estado de confiança e elegibilidade

- `SwapEvent`: **observado em payload RPC real**, discriminador/layout compatíveis e reconciliação inteira com diferença zero.
- Original RAW: confirmado com hash arquivado; autenticidade **independente** do RPC ainda não provada.
- Reserva efetiva pré-instrução: **declarada e reproduzida pelo evento**; **não** comprovada por snapshot PoolState e vault externo independente.
- PoolState histórico completo: **pendente**. AmmConfig histórica completa: **pendente**.
- Taxas trade e creator: **valores realizados no evento comprovados localmente**; rates e outros buckets de taxas não confirmados independentemente.
- Momento em que a estratégia poderia conhecer o evento: **20/11/2026 18:24:55 UTC ou depois**, nunca retroagir ao swap de 18/11.
- Quote disponível antes da decisão, preço executável, PnL simulado confiável, validação de prover independente e execução financeira: **NÃO autorizados**. Campos `quote_available_before_swap=False`, `executable_quote_proven=False`, `replay_eligible=False`.

## Validação e próximo caminho independente

- Novo módulo `services/cpmm_swap_event_evidence.py` reaproveita decodificadores de instrução e o verificador RAW original; interpreta apenas 1 evento Anchor ligado à invocação CPMM, verifica identidade pool/mint, cutoff, hashes e reproduz resultado com inteiros e arredondamento conforme Raydium.
- 15 testes adversariais adicionais em `tests/test_cpmm_swap_event_evidence.py`: evento real, discriminador, tamanho, flags, pool incompatível, duplicata, fora do contexto CPMM, hash e cutoff, divergência de transferência, alteração material da taxa, determinismo e bloqueio de execução.
- **902 testes, zero falhas**, CI no commit de código `094c941c81bce27924c474b28252d92d5e394f42`: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44801167222.
- Prioridade seguinte: prova histórica gratuita ou arquivada das contas PoolState/AmmConfig, com versão do layout em 18/11 e dados binários, owner/PDA, ordem da instrução e acesso temporal. Eventos de outros swaps podem corroborar matemática, mas não devem ser promovidos a snapshots.
- Não repetir consultas aos endpoints que retornaram null/HTTPError sem nova justificativa. Sem merge na `main`.
