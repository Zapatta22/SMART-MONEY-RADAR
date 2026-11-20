# SMR — Comando Mestre 22: sessão real Solana WebSocket de contas CPMM

Data: 2026-11-20. Base PR #106; `main` sem alteração.

## Fonte e limites

- Fonte gratuita pública: `wss://api.mainnet-beta.solana.com/`, método `accountSubscribe`, quatro inscrições com compromisso **`finalized` solicitado**; nenhuma credencial Geyser, Helius, VPS, chave privada ou ordem.
- Contas solicitadas em ordem: PoolState `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`; AmmConfig `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`; vault HIGH `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`; vault WSOL `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG`.
- **Sessão real executada**: `2026-11-20T20:57:24.656758+00:00` a `2026-11-20T20:57:59.709004+00:00`; duração **35,052246 s**, uma conexão.
- **Quatro confirmações de inscrição** WebSocket recebidas (quatro subscription IDs distintos; quatro frames RAW arquivados). **ZERO notificações reais `accountNotification`** nesse período. Esta é uma ausência observada na janela; não prova ausência de atualizações fora dela, nem ausência de perda/filtragem de eventos.
- Sessão sem erro de rede no ciclo validado. Uma execução inicial da mesma arquitetura falhou por chave estrangeira SQLite (start antes de register); o bug foi corrigido, e o ciclo com 4 ACKs é o marco, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44815956132.
- Não foi feita nova consulta `getMultipleAccounts` para baseline neste comando: baseline binário das quatro contas com horário e `context.slot` dentro da janela `accountSubscribe` **não foi obtido**, portanto `baseline_validated=False` e **cobertura `UNKNOWN`**, mesmo que as confirmações de inscrição tenham sido recebidas.
- Integridade de journal registrada: four RAW frames entregues sequencialmente ao journal local, conexão/session ID `solana-accountsubscribe-4a3e664e-1cb5-48bf-9ea7-df250f351387`, fingerprint de frames `64b860b699db97132b34ae93a5137e15aa13c99d543afdd945d70e7ef2963e6d`. **Essa ordem 0..3 é apenas de chegada local dos ACKs**, não ordem de writes em ledger. `txn_signature=None`, `write_version=None`, global order/cross-stream independence **UNKNOWN**. Nenhum evento binário PoolState/AmmConfig ou vault foi observado. A fonte RPC não é atestada independentemente.
- Sessão e bytes preservados em `data/evidence/mainnet/2026-11-20/live-cpmm-ws-session/`: quatro requests RAW, quatro ACK frames RAW, `geyser-raw.sqlite` existente, manifesto. Arquivamento validado offline, sem nova requisição: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44816244740.

## Integração e validação

- `services/cpmm_public_ws_capture.py` é **adaptador de entrada**, não outra arquitetura de eventos; `PublicCpmmWsSession` usa diretamente `SQLiteGeyserRawStore.register_frame_stream/start_capture_session/append_wire_frame/finish_capture_session`. Frame RPC é identificado como `solana_ws_jsonrpc` ou `solana_ws_subscription_ack`, **nunca protobuf Yellowstone/Geyser**.
- `tools/capture_live_cpmm_ws.py` limita janela a 35 segundos, 4 endereços, máximo 60 frames, 1 MiB/frame, sem requisições financeiras; preserva resultados `NO_NOTIFICATIONS_OBSERVED` e erros.
- `tests/test_cpmm_public_ws_capture.py`: 13 testes **sintéticos apenas**, cobrindo duplicata, regressão de slot, conflito de payload no mesmo slot, assinatura/ordem desconhecidas, conta incorreta, conexão reiniciada, baseline ausente, RAW malformado, integridade SQLite, interrupção e bloqueios econômicos.
- Comparadores CPMM econômicos e timeline Geyser existentes **não** receberam eventos falsos: notificações RPC sem `txn_signature`/`write_version` não podem ser promovidas a `NormalizedAccountUpdate` com write_version fictício.
- **CI integrada: 982 testes, zero falhas**, commit de testes `5d5248d23fa8a5be83d8f183bbed680c9382f9bc`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44816140055. Pequeno endurecimento posterior limpa estados entre reconexões, mantendo o gap. Verificar CI desse commit antes de alegar 982 nele.

## Próximo passo

1. Para obter **notificações de conta reais**, executar nova sessão somente quando houver hipótese técnica independente e tempo de atividade maior/contas com evidência de mudanças; uma janela de 35 s sem eventos não autoriza extrapolação.
2. Fazer `getMultipleAccounts` durante sessão para baseline de quatro contas com horário e slot, comparar `accountNotification` com snapshot contemporâneo quando existirem notificações. Mesmo assim, duas observações não provam cobertura contínua.
3. Para updates específicos por assinatura, continuar dependendo do Geyser com proveniência de fornecedor ou associação verificável via transações e account writes; accountSubscribe não envia assinatura ou write_version. Não inventá-los.
4. Não fazer merge automático, executar operações financeiras, pagar Helius/VPS ou habilitar PnL econômico.

Status econômico: **bloqueado**. Progresso global não mensurável.
