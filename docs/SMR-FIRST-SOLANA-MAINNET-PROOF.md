# SMR — primeira prova real Solana mainnet (2026-11-20)

**Situação:** captura pública real concluída em branch Draft #100, sem
qualquer envio de transação, carteira, credencial ou gasto com provedor.
Transação é observada via RPC; **autenticação independente não concluída**.

## Identidade e aquisição

- Solana mainnet, método read-only `getTransaction`, assinatura
  `23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM`.
- Endpoint: `https://api.mainnet-beta.solana.com` (Triton One),
  1 requisição efetiva, `commitment=finalized` **solicitado**.
- Slot RPC observado: **471039497**, mesmo do explorador independente
  utilizado apenas para escolha do alvo. `transaction.meta.err=null`.
- Evento na cadeia: **2026-11-18 18:45:26 UTC** (blockTime).
- Observação RPC: **2026-11-20 18:24:54.797654 UTC**;
  disponibilidade para a estratégia: **2026-11-20 18:24:55.131940 UTC**.
- Resposta RAW: `data/evidence/mainnet/2026-11-20/23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM.raw.json`.
- Manifesto: `data/evidence/mainnet/2026-11-20/first-proof.manifest.json`.
- **SHA-256 RAW**:
  `3325222e2c33f6735432f12065b348b4657ae9cfc2c1141061c7c78639724dad`.
- Coleta GitHub Actions: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44792506494
  (artefato ZIP #14657530899). Persistência *sem nova chamada RPC*:
  https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44793176514
  com verificação do RAW, slot, assinatura, instrução e contas.
- Nível de confiança: `RPC_CONSISTENT_UNATTESTED`. Não há attestation
  independente de assinatura de validador, finalização em segundo RPC ou
  integridade econômica do pool.

## Programa e pool realmente presentes na instrução

- Programa Raydium CPMM:
  `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`.
- PoolState:
  `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`.
- AmmConfig declarado:
  `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`.
- Vault de entrada:
  `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`.
- Vault de saída:
  `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`.
- Mint de entrada HIGH:
  `7ymF66Z6VhgNiwadtVhjTtT6U7iQRpSxeiRrhfufhigh`
  (6 decimais).
- Mint de saída WSOL:
  `So11111111111111111111111111111111111111112`
  (9 decimais).
- A instrução de swap de índice 3 do payload possui 13 contas CPMM;
  os índices e mints correspondem ao manifesto.

## Deltas de balances contidos no próprio RAW (slot 471039497)

| Campo | Pre | Post | Delta |
|---|---:|---:|---:|
| Vault HIGH (unidades brutas, 6 decimais) | 62,368,009,739,127 | 62,387,737,216,382 | +19,727,477,255 |
| Vault WSOL (lamports, 9 decimais) | 313,591,578,802 | 313,493,478,885 | -98,099,917 |

A variação reflete **19.727,477255 HIGH** no vault de entrada e
**0,098099917 WSOL** no vault de saída. `meta.fee=27000` lamports
é taxa de transação Solana, **não** comprovação da taxa CPMM.

Esses saldos são evidência pontual da transação obtida via RPC, **não
certificam reservas efetivas** do CPMM nem taxas de protocolo, estrutura
PoolState, vault authority, PDA ou custos de uma nova ordem.
A coleta posterior também não demonstra que os dados estariam disponíveis
em 18/11/2026 para uma decisão histórica: o primeiro availability
comprovado para esta amostra é 20/11/2026 18:24:55 UTC.

## Testes e bloqueios

- CI de regressão na branch contendo o RAW original:
  https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44793416811
  — **859 testes aprovados, zero falhas e compileall**, commit de código
  `2690625d1ade59abff4e07e884aca7d41e2a6cbf`.
- Os dez novos testes cobrem SHA, assinatura, slot, escopo do programa
  e pool, 13 contas, mints/vaults, saldos, cronologia, ausência de
  autenticação externa e proibição de execução/ROI.
- Sem snapshot histórico auditado de PoolState/AmmConfig/vaults com
  taxas válidas neste slot, **não calcular cotação teórica baseada em
  reservas presumidas**.
- `strict_economic_replay` permanece bloqueado: não promover esta
  observação a preço executável nem considerar lucro/drawdown.

## Próxima prioridade

1. Consultar segunda fonte RPC de maneira limitada e comparar assinatura,
   slot e RAW, sem chamar coincidência de prova criptográfica.
2. Reconciliar PoolState/AmmConfig e vaults no contexto histórico do
   **slot 471039497**, validando owner, configuração, taxas, saldos e
   as respectivas disponibilidades. Não usar reservas de hoje como
   snapshot histórico.
3. Só então criar `quote_id` teórico com corte temporal; manter
   executabilidade e replay econômico em bloqueio até a prova adequada.

`main` preservada; PR #100 Draft, sem merge.
