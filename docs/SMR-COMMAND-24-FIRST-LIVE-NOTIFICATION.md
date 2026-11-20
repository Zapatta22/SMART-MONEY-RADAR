# SMR — Comando Mestre 24: primeira notificação live CPMM, tentativa única auditada

Data: **2026-11-20**. Branch `codex/smr-cpmm-first-live-notification`, base PR #108, **sem merge em `main`**.

## Recuperação

PR #108 em Draft, head `0c9c0a11fe6176397e6bbc387a83804fc694247e`, `main` verificada `5060bc65ddf181a4736fdb662c44c3fec0dd7259`, último commit de código validado `3208e71` com 996 testes aprovados e baseline real anterior no slot `471884671`. Reutilizados `PublicCpmmWsSession`, `SQLiteGeyserRawStore`, `inspect_contemporaneous_baseline` e validador PoolState/AmmConfig. Não implementadas arquiteturas paralelas.

## Estratégia e execução única

- Exatamente **uma nova sessão WebSocket pública** `wss://api.mainnet-beta.solana.com/`, quatro `accountSubscribe` solicitados com `finalized`, e um único `getMultipleAccounts` contemporâneo em `https://api.mainnet-beta.solana.com` depois de quatro ACKs. Endereços: PoolState `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`; AmmConfig `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`; vault HIGH `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`; vault WSOL `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`. Os vaults são candidatos mais prováveis a refletir swaps, porém sem probabilidade medida ou promessa de notificação no período; os quatro foram monitorados.
- O teto configurado era **75 segundos** ou 80 frames; o monitor terminaria após primeira notificação `OBSERVED` arquivada no RAW journal. Condicionalmente, até **1 RPC adicional** após uma notificação real. **Não foi realizado RPC adicional** porque não ocorreu notificação. Sem VPS, Helius, credenciais ou envio de transações.
- Sessão real iniciada `2026-11-20T21:27:36.881630+00:00`, encerrada `2026-11-20T21:28:37.204327+00:00`, duração **60,322697 segundos** (abaixo do teto). **Quatro ACKs reais, zero notificações `accountNotification`**. A execução Actions concluiu `success` porque preservou os dados e os bloqueios, mas o manifesto operacional indica `status=NETWORK_OR_WS_ERROR`, `error=ConnectionClosedError`, e `session_report.gaps` deve conservar `connection_lost`. **Não declarar a janela uma sessão contínua terminada normalmente.**
- Baseline real conjunto **slot `471887787`**, solicitado `2026-11-20T21:27:37.203752+00:00`, resposta disponível `2026-11-20T21:27:37.354956+00:00`, quatro contas validadas `RPC_DECLARED_PROSPECTIVE_ONLY`. SHA-256 da resposta original `c4f10427ef143d4dd7570133d124966cfb146097ea704c78b2d6fab66187f5d8`. Esse baseline não prova stream contínuo nem explica evento específico.
- `notifications_received=0`; logo **nenhuma conta alterada comprovada, nenhum slot/hash de notificação real**, nenhum delta ou relacionamento WebSocket→RPC específico. `coverage=PARTIAL` significa apenas que o snapshot RPC foi observado; a **cobertura do stream é `UNKNOWN`**, acentuada pela desconexão. Não há assinaturas nem `write_version`.
- Quatro pedidos WS RAW, quatro ACK RAW, pedido/resposta RPC, manifesto original e SQLite persistidos. `session_frames_stored=4`, verificação de integridade e SHA em https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44820879005 **sem nova chamada RPC/WS**. Coleta https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44820468353. Pasta imutável `data/evidence/mainnet/2026-11-20/first-notification-attempt-slot-471887787/`.

## Alterações e testes

- Alterado **apenas o coletor existente** `tools/capture_live_cpmm_ws_baseline.py`: teto 75 s, parar quando primeira notificação observada já arquivada, guardar hash/slot/conta, e executar no máximo um novo `getMultipleAccounts` apenas se surgir notificação. Uma resposta posterior, se obtida, **não é fonte independente para validar evento nem prova continuidade**.
- `tests/test_cpmm_first_live_notification.py` acrescenta **14 testes** com RAW do baseline real da PR #108 e notificações **sintéticas de teste**: primeiro evento, conta incorreta, SHA adulterado, slot regressivo, duplicata, baseline ausente, desconexão, mesmo slot, antes/depois do baseline, interrupção do journal, cutoff, replay e bloqueio financeiro.
- CI integrada: **1010 testes aprovados, zero falhas**, código no commit `c12b62727f4c5017a44e8833e7b950c6620090df`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44820732065. Captura real anterior ao commit somente de testes.
- Sem merge, gastos, chaves privadas, ordens ou lucro/retorno inventado. Progresso global não mensurável.

## Próxima hipótese técnica

Não repetir imediatamente a mesma sessão com os mesmos parâmetros: em três sessões curtas das mesmas quatro contas não chegaram notificações; esta ainda terminou com desconexão aos 60 s. Investigar **offline** a política de timeout/keepalive do WebSocket público e introduzir identificação explícita de heartbeat e razão de desconexão, com fechamento sem falso positivo e política de reconexão sem promover checkpoint. Somente depois de justificativa e testes considerar nova sessão única, talvez com duração/reconexão revisada ou observação prospectiva de pool cuja atividade seja demonstrável; não alterar as quatro contas deste módulo sem propósito explícito.
