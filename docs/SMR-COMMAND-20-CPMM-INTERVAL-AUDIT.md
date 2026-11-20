# SMR — Comando 20: auditoria real de transações no intervalo CPMM

**Data:** 2026-11-20. **PR #105 Draft**, base #104, sem alteração ou merge da `main`.

## Observações e aquisição (quatro consultas RPC no total)

Intervalo entre capturas prospectivas reais de PoolState/AmmConfig/vault HIGH/WSOL: **(471856996, 471860762]**, ou 3766 slots. Primeira observação do pool: 2026-11-20T19:37:10.344983+00:00; segunda: 2026-11-20T19:50:40.432045+00:00. Ambos os snapshots RPC são originais preservados na PR #104.

Foi executada **uma única** chamada `getSignaturesForAddress` de no máximo 1000 resultados para `CqvMZmWDvEufa5rzkubidyR4zMDqDPoLjAtsW6wGsPMu`, em `https://api.mainnet-beta.solana.com`, com `finalized` solicitado. A resposta incluiu 1000 assinaturas; intervalo total retornado entre slots 471619227 e 471866732, com **3 candidatas no intervalo específico**. Isso é só uma página: não demonstra captura de todas as escritas às quatro contas e **não** é prova de que todas as transações do intervalo foram enumeradas. A cobertura permanece `PARTIAL`, e `pagination_exhausted=False`.

- Consulta real: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44809684411
- SHA-256 RAW da lista: `bbb2060ca28209bc8413461860d9cb39ea54453be3c949b2a5abe0b513c2cb3c`
- Arquivamento permanente, sem repetir chamada RPC: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44809784281
- Arquivos: `data/evidence/mainnet/2026-11-20/cpmm-interval-471856996-471860762/{request.raw.json,response.raw.json,manifest.json}`

## Consulta das três assinaturas candidatas

Efetuadas apenas **3 novas chamadas** `getTransaction` sem chave e sem enviar transações, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44809872091.

| Slot listado | Assinatura | RPC/transação | SHA-256 RAW |
|---:|---|---|---|
| 471857488 | `3JSyzXZWsNBxqkqRt4Gbri2B3ZuanWq1z8f8Vgbi6zCNoCKys1xT325UHN9Wrkd4oeJkiSuXdTBWfmqZjsW66Bz4` | `UNKNOWN` (`result:null`) | `54bd6392bccf8e0984e11b59d2ec7749e865a13797af136fd42aa421e47359d8` |
| 471860518 | `Y8ZGmqJCsCS4tWP181bQoxUB2HUr5k5gGJ3VnQxjCcnUk8xd7QWbjxNUXsJSgQ417drRHXTJPSNfDh15VGoN17W` | `RPC_CONSISTENT_UNATTESTED` | `b4fef8c93f20a97349b657bc53c4be383b2153bf00e2c97822dc44c63089f6e5` |
| 471860536 | `4WuWPyiaKxgTLxBpQvauqJAzbCgyk7gZjjn7vDdVSYeWuNuM8UkeVR1aN6536MA6yg5RGNehgneX65AsDJJSrjET` | `RPC_CONSISTENT_UNATTESTED` | `b51d4561ba88cceb20cbd0e7ee9555da1ee57d68b1fa461337fe829762887830` |

Duas respostas incluem assinatura, slot, sucesso e instruções relacionadas ao pool CPMM. Uma não retornou a transação, portanto não é possível determinar seu programa, contas, valores ou taxa pela resposta. Não fazer nova consulta equivalente automaticamente. Os RAWs das três tentativas e manifestos foram preservados permanentemente sob `transactions/` via https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44809953411, **sem nova consulta**.

**Ordenação comprovada:** os slots das duas transações retornadas (471860518 antes de 471860536) são comparáveis; o índice de transação dentro de slot permanece **desconhecido** e não é inferido por ordem de listagem. A ordenação de instruções dentro de cada transação é a fornecida no payload RPC; não há stream contínua de quatro contas validada.

**Reconciliação econômica:** não há prova de que os três itens da lista sejam todas as transações de pool, nem de que cada alteração das quatro contas seja um swap. Não existe reprodução completa dos dois snapshots por eventos ordenados. Deltas HIGH/WSOL entre snapshots seguem observados (PR #104), mas **resíduos econômicos de todos os eventos do intervalo são UNKNOWN**, sem valores artificiais ou PnL.

## Módulos reutilizados e implementação pequena

- Reutilizados: `decode_raydium_cpmm_swaps`, `services/prospective_cpmm_history.py`, `storage/cpmm_prospective_history.py`, `storage/geyser_recovery_store.py` para desenho de checkpoint, e os contratos `data_sources/geyser_{account,transaction}_updates.py`. Nada foi reimplementado de Geyser RAW ou event store.
- Novo `services/cpmm_interval_transaction_audit.py`: compara a listagem RAW às capturas, slot, assinatura, pool, transação e disponibilidade; retorna `PARTIAL`, `UNKNOWN` ou `CONFLICT`; descarta autorização financeira. Uma lista de assinaturas não certifica cobertura de writes.
- Novo `storage/cpmm_interval_evidence.py`: extensão append-only do SQLite da PR #104, com RAW/payload/hash, origem, horário, classificação, vínculo com ambas capturas e checkpoint atômico. Checkpoint gravado **somente depois de todas as evidências, na mesma transação SQLite**; crash antes de commit reverte o conjunto. Evidência repetida é idempotente; RAW alterado causa conflito.
- **CI integrada 956 testes aprovados, zero falhas e compileall**, commit `774d37817b8e3518e36878380030dec6c79bcbcc`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44810462045. Testes adversariais cobrem assinatura duplicada, slot diverso, pool errado, RAW modificado, dados futuros, evento não encontrado, paginação incompleta, ordem desconhecida, checkpoint parcial e reentrada determinística. Correções de duas execuções intermediárias com erros de serialização foram registradas no SHA final.

## Pendências e próxima prioridade

1. Identificar evidências de mudanças de conta e assinatura que tenham ordenação/continuidade verificável usando os adaptadores WebSocket/Geyser já construídos. A API RPC de histórico de assinaturas do endereço é insuficiente sozinha para garantir escrita de todas as quatro contas.
2. Se houver nova fonte realmente diferente ou prova de cobertura histórica, investigar a assinatura UNKNOWN, preservando falha anterior.
3. Vincular deltas econômicos apenas a eventos com todas as evidências (incluindo taxas não-swap, account writes, ordem e reversões), mantendo resíduo `UNKNOWN` até prova suficiente.
4. Não fazer merge, comprar, vender, pagar serviços ou habilitar ordens. Progresso global: não mensurável.
