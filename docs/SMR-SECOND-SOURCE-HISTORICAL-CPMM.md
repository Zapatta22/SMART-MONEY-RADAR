# SMR — Comando 16: segunda fonte RPC e estado histórico Raydium CPMM

**Data:** 20/11/2026. **Branch:** `codex/smr-second-source-historical-state`.
**PR:** #101 Draft, base PR #100. A `main` não foi alterada.

## Transação original

- Assinatura: `23n2r5iEcCJkPZ4G1vkTdBc8eUn3CgEWqtdxz4J4SQnEXnuiwJaP39kKK3NCHJPPsFAq8CiSjRLK5QA4JqUkzLLM`.
- Slot observado pela **primeira** fonte: `471039497` (resposta getTransaction solicitando finalized; finalização independente **não demonstrada**).
- Pool Raydium CPMM: `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`.
- Primeira fonte: `https://api.mainnet-beta.solana.com`, captura em 2026-11-20T18:24:55Z, RAW SHA-256 `3325222e2c33f6735432f12065b348b4657ae9cfc2c1141061c7c78639724dad`, arquivos persistidos na PR #100.
- Evento de blockchain de 18/11 não era comprovadamente disponível à estratégia antes de 20/11 (primeira captura real neste projeto). Não retroagir o cutoff.

## Segunda origem — consulta efetuada

- Endpoint `https://solana-rpc.publicnode.com`, 1 requisição real `getTransaction`, compromisso `finalized` solicitado.
- GitHub Actions: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44795018974.
- Resposta RAW exata (39 bytes): `{"jsonrpc":"2.0","result":null,"id":1}\n`.
- SHA-256 da resposta RAW: `ca3db3fe00f86a9485058afc1daf2f0547027fc3262b67c570f89d0b4638c8c6`.
- Status `UNKNOWN`: pode refletir histórico indisponível no nó. **Não confirma e não contradiz a assinatura/slot**. Sem meta, pool, vaults ou taxas comprováveis nessa resposta.
- O manifesto inicial declarou `source_agreement_on_signature=true` por eco da assinatura **solicitada**; esse campo não veio de uma transação retornada. O RAW e manifesto originais foram mantidos sem adulteração; `second-source/interpretation.json` corrige explicitamente a interpretação.

## Outra fonte alternativa — indisponível

- Endpoint `https://public-solana-mainnet.rpcnode.dev`, 1 requisição tentada, GitHub Actions: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44795352312.
- Status `UNKNOWN` por `HTTPError`, sem corpo de transação recuperado; portanto, não há hash RAW de transação dessa tentativa.
- **Independência de infraestrutura das três fontes NÃO comprovada**: URLs diferentes não demonstram operadores ou infraestrutura independentes.
- A cópia permanente dos artefatos de ambas as fontes foi realizada sem nova chamada de rede: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44796066170.
- Arquivos: `data/evidence/mainnet/2026-11-20/second-source/` e `third-source/`.

## Estado histórico do CPMM

`services/historical_cpmm_state.py` usa os **mesmos bytes RAW observados da primeira fonte**, vinculando SHA-256, assinatura, slot, programa, pool, AmmConfig referenciada e vaults. Reconstrói valores `meta.preTokenBalances` e `meta.postTokenBalances`:

| Vault | Saldo no início da transação | Saldo no fim | Diferença |
|---|---:|---:|---:|
| HIGH (6 decimais) | 62.368.009,739127 | 62.387.737,216382 | +19.727,477255 HIGH |
| WSOL (9 decimais) | 313,591578802 | 313,493478885 | -0,098099917 WSOL |

**Limite temporal essencial:** esses dados são limites da transação, **não** um snapshot comprovado imediatamente antes ou depois da instrução de swap. O saldo do vault bruto **não é igual** à reserva econômica CPMM quando existem taxas acumuladas e outros ajustes.

- `PoolState` histórico em binário: **ausente**.
- `AmmConfig` histórica em binário e taxas trade/protocolo/fundo/criador: **ausentes**.
- Autoridade real dos vaults / PDAs e completude dos updates anteriores ao swap: **não atestadas**.
- Reserva efetiva imediatamente pré-swap: **desconhecida**.
- Taxa da transação Solana: `27000` lamports no RAW; **não** substitui taxa CPMM.
- `quote_id` economicamente validado, preço executável e replay de lucro: **não disponíveis**.
- `HistoricalAccountWitness` inventaria futuros PoolState/AmmConfig/vaults com slot, disponibilidade, bytes originais e hashes, exigindo prova de posição pré-swap. Mesmo flags externas declaradas como atestadas **não** ativam cálculos financeiros sem verificador independente integrado.

Um RPC comum `getMultipleAccounts` fornece um estado de contas no contexto da consulta; `minContextSlot` define um mínimo de slot, **não** uma viagem a um slot antigo. Não inserir contas atuais como histórico. Para recompor prestate, obter arquivo de atualizações de conta com ordem de instrução/slot e provas verificáveis.

## Testes e continuidade

- `services/rpc_source_comparison.py` compara origem, slot, assinatura, pool, mints, vaults, valores econômicos, hash de payload e identidade declarada de infraestrutura sem presumir independência.
- Testes adversariais cobrem `result:null`, infraestrutura compartilhada, operadores desconhecidos, JSON inesperado, hash adulterado, divergência de slot, assinatura, pool e taxa, histórico posterior à transação e ao cutoff e determinismo.
- **887 testes aprovados, zero falhas, compileall**, commit de código `1fad264e2f8cc4dc7783565b497652653fa971d6`:
  https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44796715478.
- Um teste de JSON RPC como lista expôs exceção no commit anterior; foi corrigida no SHA acima. Não citar CI de commits anteriores como final.

## Próxima prioridade

Usar fonte externa **que realmente suporte snapshots históricos** de PoolState, AmmConfig e vaults até antes do swap no slot `471039497`, com primeiro horário de disponibilidade e ordem comprovada, proprietário do programa validado e reserva efetiva calculada pelos validadores CPMM já existentes. Repetir consulta finalizada de assinatura por outro RPC só se o provedor demonstrar cobertura do histórico necessário. Sem VPS, serviços pagos, ordens reais ou alterações na `main`.

Progresso global: não mensurável até critérios e pesos de aceite.
