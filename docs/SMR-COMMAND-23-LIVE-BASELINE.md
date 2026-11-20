# SMR — Comando Mestre 23: baseline live contemporâneo com WebSocket CPMM

Data: **2026-11-20**, PR Draft baseada em #107, sem alteração de `main`.

## Inventário de recuperação

A PR #107 permaneceu Draft; head recuperado `42f30259749314c5a72fae52c4a8685b1e27d96e`. Os módulos `PublicCpmmWsSession`, `SQLiteGeyserRawStore`, `inspect_prospective_cpmm_response`, RAW original CPMM e o registro `docs/SMR-CODEX-CONTINUITY.md` foram lidos antes das modificações. Baseline anterior: 982 testes, zero falhas. `main` permaneceu `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

## Sessão real e baseline

Uma sessão pública limitada de WebSocket `wss://api.mainnet-beta.solana.com/` abriu quatro `accountSubscribe` com `commitment: finalized` solicitado, para PoolState, AmmConfig, vault HIGH e vault WSOL, nesta ordem:

1. `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`
2. `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`
3. `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`
4. `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`

**Quatro ACKs efetivamente recebidos**, e somente então um `getMultipleAccounts` (uma consulta) ao RPC público `https://api.mainnet-beta.solana.com`. A tarefa RPC foi executada em thread assíncrona enquanto a tarefa WebSocket continuava consumindo e arquivando frames antes de interpretar os dados. Nenhum frame de notificação foi ignorado de propósito por seu slot.

- Início `2026-11-20T21:16:26.359517+00:00`; fim `2026-11-20T21:17:06.408814+00:00`. Duração **40,049297 s**.
- Requisição baseline `2026-11-20T21:16:26.742830+00:00`; disponibilidade da resposta `2026-11-20T21:16:26.931642+00:00`.
- RPC `context.slot = 471884671`; as quatro contas retornaram na mesma resposta.
- `baseline_status = RPC_DECLARED_PROSPECTIVE_ONLY`; layout PoolState/AmmConfig, proprietários SPL e vaults foram validados usando o decodificador **já existente** e a conta de autoridade extraída do RAW original.
- SHA-256 do request `fb7f4b76fa774d65524d2d1ed852ede29ab56969590aefd2f119ea1bdf661e67`; SHA-256 da resposta `8f90211a257ffb099dacf64b2d1cf64684a1f07582cf867cf12635d50c422ae7`.
- **0 accountNotification** durante a sessão. Os 4 frames recebidos foram exclusivamente ACKs. Nenhuma mudança específica de PoolState/AmmConfig/vault observada; portanto, não há comparação de binários pré/pós-notificação real neste marco.
- Identificador de sessão `solana-ws-baseline-5164ee89-84f7-4ce7-bb1c-a65663c06661`. Journal existente SQLite com quatro frames ACKs, `PRAGMA integrity_check=ok`, metadados da sessão, ordem **apenas de chegada local**, hashes auditáveis, sem `txn_signature`, `write_version` ou banco Geyser inventados.
- Captura live: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44818816642.
- Arquivamento **offline, sem nova requisição RPC nem abertura WebSocket**, após conferir RAW, hashes, identidade, decodificador, SQLite e cardinalidade: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44819397079.
- Arquivos preservados permanentemente na branch `data/evidence/mainnet/2026-11-20/live-cpmm-baseline-slot-471884671/`: 4 requests WebSocket RAW; 4 frames ACK RAW; `baseline.request.raw.json`, `baseline.response.raw.json`, `geyser-raw.sqlite`, `manifest.json`.

## Integração e semântica

- `tools/capture_live_cpmm_ws_baseline.py`: sessão WS única de até 40 segundos, até 80 frames e até 1 MiB por frame, 4 inscrições e uma consulta `getMultipleAccounts` **após quatro ACKs**; leitura WebSocket permanece ativa durante o RPC. Sessão RAW e SQLite são preservados mesmo com falha de provedor, com `UNKNOWN` por padrão.
- `services/cpmm_ws_baseline_bridge.py`: reutiliza `inspect_prospective_cpmm_response`, compara slot e SHA binário de cada eventual accountNotification real com o baseline e registra `BEFORE_BASELINE_SLOT`, `SAME_SLOT_STATE_MATCH`, `SAME_SLOT_STATE_CONFLICT`, `AFTER_BASELINE_SLOT`, `UNKNOWN` ou `CONFLICT`. Verifica cutoff e integridade RAW antes de comparar. Mesmo a igualdade de slot não demonstra ordem intra-slot.
- A confirmação de quatro subscriptions **não fecha a janela de corrida**. Uma resposta RPC não garante que mensagens WebSocket anteriores, do mesmo slot, ou atrasadas tenham sido totalmente entregues. `coverage=PARTIAL` reflete apenas snapshot contemporâneo observado, **não** sequência completa; `race_window_closed=False`, `global_ledger_order_verified=False`, `delivery_continuity_attested=False`.
- `websockets.accountSubscribe` não fornece `txn_signature` ou `write_version`; nenhum evento fabricado é inserido na timeline Geyser. Não atribuir eventos desconhecidos aos swaps anteriores; `main` e controles financeiros intactos.

## Testes e economia

- `tests/test_cpmm_ws_baseline_bridge.py`: **14 novos casos**, baseados em fixture RAW RPC real previamente preservada mais vetores de notificações **sintéticos e explicitamente de teste**. Casos: igualdade/diferença no mesmo slot, slots antes e depois do baseline, assinaturas desconhecidas, hash RAW adulterado, cutoff de baseline e notificação, conta errada, reconnect, respostas incompletas, ausência de RAW, determinismo e bloqueios.
- A primeira CI de integração encontrou autoridade Raydium incorreta usada pela fixture e checagem indevida de tipo de RAW. Foi corrigido obtendo a autoridade correta da transação real `GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL`. **CI integrada final 996 testes, zero falhas** no commit de código `3208e71f42f4aaa6f822ad75be342a478553fc52`: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44819255872.
- Sem Helius, VPS, serviço pago, envio de transações, ordens ou dados de usuário sensíveis.

## Próxima prioridade

A sessão apresentou **zero alterações**, embora baseline tenha sido válido. Próximo marco seguro é obter pelo menos uma `accountNotification` real das mesmas quatro contas em uma nova janela **com baseline/ACKs/journal intactos**, evitando looping excessivo e sem confundir chegada de mensagens com continuidade. Para fechar cobertura exigiria prova adicional de entrega integral, ordem e lacunas/reconexões, provavelmente infraestrutura/stream mais capaz que accountSubscribe público. Manter compras/vendas, simulação de PnL executável e cobertura `COMPLETE` bloqueadas.
