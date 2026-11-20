# SMART MONEY RADAR — Comando Mestre 25: resiliência WebSocket Solana CPMM

Data: 2026-11-20. Base PR #109 Draft no commit `f89a13ab81e9c25b809d8e7227dcaeccf3d366a4`. `main` preservada no SHA `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. **Sem nova consulta RPC, WebSocket live ou custos.**

## Diagnóstico verificado

Manifesto histórico imutável em `data/evidence/mainnet/2026-11-20/first-notification-attempt-slot-471887787/manifest.json`:

- 4 confirmações WS, 0 accountNotifications, baseline RPC slot 471887787 válido, journal SQLite com 4 frames e `integrity_check=ok`.
- A coleta durou **60,322697 s** e o manifesto contém `status=NETWORK_OR_WS_ERROR`, `error=ConnectionClosedError` e `session_report.gaps=[subscription_start_without_verified_baseline,connection_lost]`.
- O coletor antigo configurava `websockets.connect(...,ping_interval=None)`: keepalive ping automático **desabilitado**. `ws.recv()` possuía timeout para voltar ao loop, não um detector de saúde de conexão. Exceção de conexão era capturada genericamente e registrava só o nome da classe.
- **Causa de rede não determinada**: `ConnectionClosedError` não prova falha do provedor, inatividade de rede ou pong ausente. Sem close code, close reason ou frames do handshake, não atribuir a culpa.

## Alterações implementadas

1. `services/cpmm_ws_resilience.py`: `WsResiliencePolicy` valida limites, heartbeat de **20 segundos** e timeout de pong de **10 segundos**, timeout de leitura **3 segundos**; até **uma reconexão** por política padrão. Backoff `1s` com jitter determinístico limitado `±15%`, máximo `4s` e nenhuma tempestade de retry. Classifica `CLOSED`, `PING_TIMEOUT`, `IDLE_TIMEOUT`, `NETWORK_ERROR`, `SUBSCRIPTION_FAILED`, `BASELINE_FAILED` e `PERSISTENCE_FAILED` sem afirmar causa de rede.
2. `tools/capture_live_cpmm_ws_baseline.py`: corrigida configuração de `websockets.connect` para **`ping_interval=20,ping_timeout=10`**, preservado orçamento geral 75 s/80 frames e quatro contas. Uma leitura silenciosa não indica desconexão. Falha grava objeto `DisconnectRecord` com identidade da sessão, fase, classe e mensagem de exceção, horário, frames e `coverage=UNKNOWN`. Nenhuma nova sessão real foi executada para experimentar parâmetros.
3. `services/cpmm_ws_recovery.py`: controlador de **identidade nova de sessão** a cada tentativa, reutilizando `PublicCpmmWsSession` e `SQLiteGeyserRawStore`. Antes de permitir nova sessão exige encerramento anterior, registro explícito da lacuna e budget de retries. Mesmo após nova sessão com quatro ACKs, `recovery_ready=False` sem baseline e o relatório não afirma cobertura completa; checkpoint Geyser local nunca autentica histórico em ledger. **Limite importante: a implementação de retomada da sessão no coletor live ainda não foi conectada ao controlador**. É um contrato e mecanismo de gerenciamento testado **offline**; não declarar reconexão automática demonstrada na rede nem novo baseline pós-reconexão obtido.
4. `services/cpmm_public_ws_capture.py`: correção fail-closed: se o journal retorna um receipt de conflito/rejeição, o frame **não** é promovido a notificação válida. SQLite registra anomalias RAW e bloqueia replay verificado de stream contaminado. `PRAGMA integrity_check=ok` comprova integridade estrutural do DB, não legitimidade de evidência.
5. `tests/test_cpmm_ws_resilience.py`: **14 testes novos** com fixtures sintéticas para fechamento, timeout ping, silêncio, desconexão durante/depois do baseline, falha de inscrição, orçamento de retry, determinismo do backoff, duplicidade em conexões distintas, identidade RAW conflitante, restart SQLite, slot regressivo, impossibilidade de continuidade e bloqueio financeiro.

## CI e validação

- Suíte integrada **1.024 testes aprovados, zero falhas**, após correção de expectativa de contrato do journal de RAW conflitado, no SHA `53a136ed9ea2c2f383880bb85a02972eff3bdc22` e GitHub Actions https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44826964019.
- A primeira suíte do Comando 25 encontrou um teste adversarial com expectativa inválida: `append_wire_frame` retorna um receipt de conflito e contamina a stream, sem lançar exceção. Os testes finais verificam status de conflito, bloqueio de `verify_wire_session` e integridade física SQLite.
- **Não houve sessão live neste comando**, nenhuma notificação nova e nenhum novo baseline RPC. Último baseline live preservado permanece slot **471887787**, notificação real **zero**; cobertura do stream `UNKNOWN`.

## Bloqueios e prioridade seguinte

- **Pendente:** ligar controlador `BoundedCpmmRecovery` à orquestração WebSocket do coletor live com backoff, reinscrição dos quatro endereços, *novo* `getMultipleAccounts` após quatro ACKs, tarefa única de `ws.recv()` e journal por identidade nova. Essa integração deve ser demonstrada por testes determinísticos com websocket/RPC fakes antes de qualquer live; a política default de uma reconexão **não** significa que já exista retry operacional automático.
- Pendente: verificar semântica de `websockets` durante desconexão, capturar close code/reason quando disponíveis sem inferir culpa, testar falha de ping/pong com socket fake, e comprovar persistência de lacunas e checkpoint após interrupção entre ACK e baseline.
- `accountSubscribe` não fornece assinatura, `write_version` nem prova de continuidade. Nenhuma execução financeira autorizada, `COMPLETE` proibido. `main` sem merge, sem VPS/Helius/pagamento, sem chaves.
