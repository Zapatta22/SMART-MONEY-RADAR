# SMR — Etapa 10: matriz de programas e plano de fixtures

Data: 2026-11-16  
Status: matriz implementada; assinaturas públicas candidatas localizadas; payloads RPC brutos ainda não coletados. Nenhuma fixture sintética será rotulada como real.

## 1. Regra de evidência

Uma página de explorer confirma que uma assinatura pública foi indexada e exibe metadados resumidos. Isso não substitui o payload integral `getTransaction` necessário para testar o parser. Portanto, os registros abaixo são **candidatos a fixture**, não fixtures brutas aprovadas.

Para aprovar uma fixture real, arquivar:

1. resposta integral de `getTransaction` em JSON, `encoding=json` (coerente com o coletor Etapa 11; instruções permanecem indexadas e devem ser resolvidas contra `accountKeys` + `meta.loadedAddresses`), `commitment=finalized` e versão de transação suportada;
2. assinatura, slot, `blockTime`, status e lista de programas envolvidos;
3. URL de origem e data/hora de coleta;
4. SHA-256 do JSON bruto original;
5. projeção anonimizada para testes, mantendo IDs de programas, mints e contas de pool necessárias;
6. expectativas observáveis revisadas manualmente: instruções, CPI, deltas de saldo e classificação esperada.

O payload bruto deve ser mantido como evidência imutável e não versionado em repositório público se contiver endereços de carteiras de usuários. Na projeção de teste, substituir signers, fee payers, carteiras e token accounts pessoais por aliases estáveis apenas dentro daquela fixture. Não anonimizar program IDs, mints, pools nem contas de protocolo necessárias ao decodificador. Não incluir o mapa reversível de aliases no pacote de testes.

## 2. Matriz priorizada

| Prioridade | Programa | Program ID | Papel | Escopo inicial |
|---|---|---|---|---|
| P0 | System Program | `11111111111111111111111111111111` | Core | transfer, createAccount, transferWithSeed |
| P0 | SPL Token | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` | Core | transfer, transferChecked, mintTo, burn, closeAccount |
| P0 | Token-2022 | `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` | Core | instruções comuns + transfer fee/hook com cautela |
| P0 | Associated Token Account | `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL` | Core | create/createIdempotent; suporte de contexto, não swap |
| P1 | Pump.fun Bonding Curve | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | Launchpad | create, buy/buy_exact_sol_in, sell, migrate |
| P1 | PumpSwap AMM | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | AMM | create_pool, buy/sell swap e CPI |
| P1 | Raydium CPMM | `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C` | AMM | initialize, swap_base_input/output |
| P1 | Raydium AMM v4 | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | AMM legado | initialize2, swap e inner token transfers |
| P1 | Jupiter Aggregator v6 | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | Agregador | route/route_v2; decompor CPI e não contar como venue |
| P2 | Raydium LaunchLab | `LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj` | Launchpad | initialize e migração |
| P2 | Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | AMM | create_pool, swap, posição/liquidez |
| P2 | Orca Whirlpools | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | AMM | initialize_pool, swap, liquidez |
| P2 | Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | AMM | initialize_lb_pair, swap multi-bin, liquidez |
| P2 | Meteora DBC | `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN` | Launchpad | initialize_virtual_pool, buy/sell, migration |
| P2 | Meteora DAMM v2 | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | AMM | initialize_pool, swap, liquidez |

A lista é a cobertura planejada inicial, não afirma suporte atual. O registro executável em `domain/program_registry.py` guarda IDs, categoria, prioridade, escopo e fonte de referência. O agregador Jupiter é marcado explicitamente como `venue=False` para evitar dupla contagem; a venue real deve ser identificada nas instruções internas/CPI.

## 3. Assinaturas públicas candidatas

Todas as páginas abaixo mostram transações mainnet finalizadas e resumo de swap. Ainda é necessário recuperar e arquivar o JSON RPC bruto antes de convertê-las em fixtures de teste.

| Programa/rota indicada pelo explorer | Assinatura | Slot | Estado observado | Fonte |
|---|---|---:|---|---|
| Raydium CPMM | `G2GwWpKY3ssU9JsWtc8FHTX5PqLYgYqBDpANu1jFLHK45qvEHsiZYRMoi5kVHZQGRsx85v26PYgAtGFUkZJvgJa` | 353586080 | finalized/success; `swap_base_input` | https://solscan.io/tx/G2GwWpKY3ssU9JsWtc8FHTX5PqLYgYqBDpANu1jFLHK45qvEHsiZYRMoi5kVHZQGRsx85v26PYgAtGFUkZJvgJa |
| Raydium AMM v4 | `26ETVS1u7jvobgdgp7pfd76AzbEY2aAmjk5h7b5qbnkuurf97BG5ErzZyF2kzwdQFQs7EaWfbxkryQHS7P8icJHc` | 334806214 | finalized/success; `raydium:swap` | https://solscan.io/tx/26ETVS1u7jvobgdgp7pfd76AzbEY2aAmjk5h7b5qbnkuurf97BG5ErzZyF2kzwdQFQs7EaWfbxkryQHS7P8icJHc |
| Jupiter v6 (rota; venue interna a confirmar pelo payload) | `29fhzpEDTFDANSYXu2s7WHT1LvQNym8RFDvXykpiqvPirXESW7fU93hSvhBGdFWuJ5v8T9sjDMu9TTMTRkZwkzPt` | 470208240 | finalized/success; Jupiter Swap | https://solscan.io/tx/29fhzpEDTFDANSYXu2s7WHT1LvQNym8RFDvXykpiqvPirXESW7fU93hSvhBGdFWuJ5v8T9sjDMu9TTMTRkZwkzPt |
| Meteora DLMM | `3MDoFjQV8sC6c5aMB1SLmGn21tQpVeCf24TN8Vq9V8NQcRMYQueKt5WKf8eYiLXvHR8oJX83qNEXTA9oi3UDFugS` | 390783149 | finalized/success; `swap` | https://solscan.io/tx/3MDoFjQV8sC6c5aMB1SLmGn21tQpVeCf24TN8Vq9V8NQcRMYQueKt5WKf8eYiLXvHR8oJX83qNEXTA9oi3UDFugS |
| Meteora DAMM v2 | `1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT` | 451432630 | finalized/success; swap | https://solscan.io/tx/1z8EYinixC5GZrwVsapJ4vW9Zfdx7j7EQnGZUVPQUm72WuXz8x5SMbakwunFXHYtftGiikm3JHLgwi2BwEVLLT |

## 4. Decoding invariants

- A signature is the transaction identity; each instruction occurrence also needs its instruction index and CPI path/stack depth.
- Resolve `programIdIndex` against the complete account key list, including loaded addresses for versioned transactions.
- Do not infer a swap from two balance deltas alone. Require program/instruction evidence and reconcile wallet-level token deltas.
- Distinguish top-level router instruction from venue CPIs. Count one economic swap per user intent/route, not one per nested venue leg unless explicitly modeling route legs.
- A transaction may contain ATA creation, SOL wrapping/unwrapping, fee transfers, tips and multiple swaps. Do not count rent, network fee or MEV tip as trade input/output.
- Failed transactions can pay network fees but must not create successful trade observations.
- Token-2022 transfer fees mean gross instruction amount and net wallet delta may differ; preserve both if supported, otherwise mark unresolved.
- Never treat SOL and WSOL as identical account movements without an explicit wrap/unwrap relationship.
- Preserve unknown instructions and raw payload; unknown does not mean irrelevant.

## 5. Bloqueio atual e próxima ação

O ambiente desta auditoria não conseguiu resolver DNS para `api.mainnet-beta.solana.com`; nenhuma chamada RPC foi feita e nenhuma chave Helius foi usada. Assim, a coleta do JSON bruto está bloqueada neste runtime. As assinaturas e resumos acima foram encontrados em páginas públicas de explorer, mas não são suficientes para aprovar fixtures executáveis.

Próximo passo quando houver um canal RPC de leitura autorizado: buscar as cinco assinaturas com `getTransaction`, arquivar respostas e hashes, anonimizar a projeção e revisar expectativas. Isso não requer assinatura ou envio de transação. Não usar endpoint pago nem consumir créditos Helius sem autorização explícita.
