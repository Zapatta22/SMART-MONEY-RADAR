# SMR — Comando Mestre 21: vínculo temporal real de transações CPMM com vaults

Data: **2026-11-20**. Branch `codex/smr-cpmm-tx-account-temporal-links`, base PR #105, sem merge em `main`.

## 1. Recuperação e inventário

A PR #105 permanece Draft; seu commit inicial conferido é `2776944e04c06af5fe13543d6e440a8203dd1b47`. Os 956 testes da PR #105 serviram de baseline. As duas capturas prospectivas (slots `471856996` e `471860762`), o inventário de 3 assinaturas candidatas, o RAW das 2 transações recuperadas e a resposta `result:null` foram lidos antes das alterações. `main` permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`.

Foram reutilizados `data_sources/geyser_account_updates.py` (`NormalizedAccountUpdate`), `data_sources/geyser_account_timeline.py`, `storage/geyser_raw_store.py`, `storage/geyser_recovery_store.py`, `data_sources/raydium_cpmm_analyzer.py`, `data_sources/solana_token_balance_deltas.py`, `data_sources/raydium_cpmm_transfer_reconciliation.py`, `services/cpmm_swap_event_evidence.py` e `storage/cpmm_interval_evidence.py`/SQLite. **Não foi criada outra arquitetura de eventos nem importado Geyser sintético como histórico real.**

## 2. Evidências reais de duas transações

O mesmo pool `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`, programa Raydium CPMM, AmmConfig `D4FPEruKEHrG5TenZ2mpDGEfu1iUvTiqBxvpU8HLBvC2`, vault HIGH `C5S7w9bJ81oaksCpTrBUMX5Wn4RfSxbnnkCBwMuMaPdU`, vault WSOL `8cGsmrpU5rkLszygFgaFfo8PaFBipm1zfqSLxTdytKmG` e mints esperados foram vinculados aos RPC RAWs:

- `Y8ZGmqJCsCS4tWP181bQoxUB2HUr5k5gGJ3VnQxjCcnUk8xd7QWbjxNUXsJSgQ417drRHXTJPSNfDh15VGoN17W`, slot `471860518`, SHA da resposta `b4fef8c93f20a97349b657bc53c4be383b2153bf00e2c97822dc44c63089f6e5`. Delta vault HIGH na transação: **+420832697460** unidades RAW; vault WSOL **−1411073214** lamports. A assinatura, slot, `meta.err=null`, instrução Raydium CPMM e contas associadas são confrontados.
- `4WuWPyiaKxgTLxBpQvauqJAzbCgyk7gZjjn7vDdVSYeWuNuM8UkeVR1aN6536MA6yg5RGNehgneX65AsDJJSrjET`, slot `471860536`, SHA `b51d4561ba88cceb20cbd0e7ee9555da1ee57d68b1fa461337fe829762887830`. Delta vault HIGH **+130978120008** RAW; WSOL **−436023113** lamports.
- Há **correspondência exata nos limites das transações**: vault HIGH `76688954539225` RAW no pós da primeira e pré da segunda; vault WSOL `256828166819` lamports no pós da primeira e pré da segunda. Esta é uma correspondência auditável entre dois `preTokenBalances/postTokenBalances` de RPC, **não** um account write Geyser, não prova sequência sem eventos ocultos, não permite atribuir todo delta dos snapshots às duas transações.
- `PoolState` e `AmmConfig` aparecem na instrução CPMM; suas imagens binárias no momento de cada transação não vieram no `getTransaction`, portanto o estado pós-write exato delas é **UNKNOWN**. As duas capturas `getMultipleAccounts` são de slots diferentes e não servem de writes por assinatura. Não se inferiu índice de transação dentro do slot ou commit criptograficamente independente.
- Resíduos econômicos do **intervalo inteiro** seguem `UNKNOWN`; não atribuir o gap de 3766 slots a duas transações.

## 3. Recuperação da transação UNKNOWN

Hipótese nova: um endpoint alternativo gratuito poderia oferecer a transação que no RPC original veio `result:null`. Foi enviada **uma única consulta `getTransaction`** para `https://solana-rpc.publicnode.com` com `finalized` solicitado, para assinatura `3JSyzXZWsNBxqkqRt4Gbri2B3ZuanWq1z8f8Vgbi6zCNoCKys1xT325UHN9Wrkd4oeJkiSuXdTBWfmqZjsW66Bz4` slot listado `471857488`. O resultado também veio `null`; não houve recuperação.

- Coleta: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44812142868.
- RAW da requisição, resposta e manifesto `UNKNOWN` preservados sem nenhuma nova consulta no workflow https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44812226891.
- Local: `data/evidence/mainnet/2026-11-20/cpmm-interval-471856996-471860762/alternate-rpc/`.
- A diferença de hostname não prova independência da infraestrutura. **Parar tentativas equivalentes.**

## 4. Implementação e validação

- `services/cpmm_transaction_account_links.py`: liga assinatura, slot, instrução CPMM e identidades de pool/config/vault/mints aos limites de saldos SPL; classifica `OBSERVED_TX_BOUNDARY`, `PROBABLE_INCOMPLETE`, `UNKNOWN`, `CONFLICT`. Um `NormalizedAccountUpdate` com `txn_signature` reivindicado **não** se converte automaticamente em prova de write real; sem frame RAW e proveniência de stream, `account_write_confirmed=False`.
- `services/cpmm_transaction_boundary_bridge.py`: compara pós do vault HIGH/WSOL na primeira transação ao pré dos mesmos vaults na segunda. As correspondências são `OBSERVED_BOUNDARY_MATCH`, porém `intervening_writes_excluded=False`, `state_write_proven=False`, `interval_coverage_complete=False` e `economic_execution_authorized=False`.
- `tests/test_cpmm_transaction_temporal_links.py`: 13 testes novos com RAWs reais e casos adversariais de outro pool, vault/mint incompatível, assinatura trocada, null, cutoff, mesmo slot, mudança de saldo, suposto update Geyser sem proveniência, ausência de writes, determinismo e bloqueio financeiro.
- **CI integrada aprovada: 969 testes, zero falhas, compileall**, commit de código `a39bfb9684ce71fdb2ba58a14a8d7485fdcf6509`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44812445699.

## 5. Pendências e continuação

- **Writes reais Geyser/WS não disponíveis no repositório para o intervalo antigo**; portanto, transações ligadas a saldos SPL não representam o mesmo que atualização histórica completa de PoolState/AmmConfig/vaults.
- Para continuação prospectiva: integrar fontes de writes **capturados a partir de agora** ao `SQLiteGeyserRawStore` e `AccountUpdateTimeline` existentes, com fonte, ordering_domain, stream_sequence, RAW de frame, pre/post state, assinatura, confirmação/rollback e checkpoints atômicos. Qualquer intervalo sem baseline e sem prova de continuidade segue `UNKNOWN/PARTIAL`.
- Sem compra/venda, Helius, VPS, chaves privadas, serviços pagos, `COMPLETE` não comprovado ou merge na `main`. Progresso global não mensurável.
