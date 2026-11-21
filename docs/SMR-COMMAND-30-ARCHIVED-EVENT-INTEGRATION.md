# SMART MONEY RADAR — COMANDO MESTRE 30

**Data:** 2026-11-21 UTC. **PR de código:** #111 Draft, branch `codex/smr-cpmm-ws-integrated-recovery`. **PR isolada de workflow:** #113 Draft (base `main`, sem merge).

## Resultado verificado

- **CI código**: 1.081 testes em 11,080s, zero falhas, Python compilation OK, no commit `4e4237214efcdc0785037ce2a635b3bf15444d98`; [run #44843689529](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44843689529).
- Este é o total de uma única suíte, **não somar** aos 1.063 do CM29.
- Regressões intermediárias de importação do decoder Launch, fixture ausente, conversão de CPI tuple/list em JSON e mocks de painel foram corrigidas antes da CI acima.
- **Sem Solana RPC/WS live nova**; `main` permanece `5060bc65ddf181a4736fdb662c44c3fec0dd7259`, sem compras, vendas, VPS, chaves, merge ou contratos pagos.

## Produtores e proveniência

| Radar | Fonte efetivamente ligada nesta PR | Categoria e prova | Limite preservado |
|---|---|---|---|
| Launch Radar | `raydium_cpmm_launch.py` reutilizado da branch existente; registros `cpmm_launch_evidence` + bytes RAW `cpmm_launch_raw` lidos quando o schema Launch está presente no SQLite | Fixture de transação mainnet arquivada, slot 471578450, validação offline; `FIXTURE_OFFLINE` quando explicitamente rotulada; dados do arquivo local sem atestação externa são `ARCHIVED_UNATTESTED` | O produtor online Launch completo, seu archive writer, stream cursor, backfill e WebSocket ainda estão nas branches #68–#76; não foram substituídos nem integrados nesta branch. Não inventar eventos se tabelas ausentes |
| Smart Money Radar | Recibos `swap_replay_archive` junto a `swap_observations`, `observed_transactions`/RAW, `list_smr_archived_event_inputs` | `ARCHIVED_DERIVED`, BUY/SELL histórico derivado, assinatura, pool, operação, carteira, horário, slot se disponível. Teste end-to-end reabre SQLite em read_only e lê swap persistido | Hash recalculado ao ler sem hash ancorado independentemente: `raw_hash_unanchored`, qualidade `UNKNOWN`; não confundir BUY/SELL com ordem financeira |

Contratos:
- `radar_integration_status.py`: `RadarObservation`, `compose_radar_snapshot`, contrato compartilhado de observação e avaliação local de riscos.
- `radar_event_bridge.py`: `IntegratedRadarEvent` contém `id, radar, event_type, origin, source_id, provider, signature, slot, pool, observed_at, available_at, raw_sha256, raw_identity, coverage, evidence_quality, verdict, direction, reasons, source_reference, operational_authorized, wallet_address`. Campos ausentes tornam-se `None`/UNKNOWN. Não há sistema novo de ordens.
- `event_store.py`: leitores sem escrita `list_cpmm_launch_archived_event_inputs` e `list_smr_archived_event_inputs`, mantendo arquivos SQLite e transações originais.
- `dashboard_read.py`: expõe `radar_events.launch`, `radar_events.smart_money`, `radars[name].last_archived_event_at`. Essa data **não é batimento de coletor**. Os coletores continuam `status=UNKNOWN`, `evidence_coverage=UNKNOWN`, permissão financeira `False`, paper modes `BLOCKED`.
- `dashboard_http.py`: interface mobile em navegador local mostra canais separados, hashes, origem, evidência, motivos, data de disponibilidade, estado do coletor e último arquivamento. Mantém Bearer token, loopback e GET-only; nenhum novo endpoint de escrita.

Controles regressivos testados: fixture histórica rotulada offline; hash conflitante; documento de inicialização distinto; duplicados idempotentes; conflito entre identidades de pool; slot e assinatura ausentes; identidade de transação contraditória; ausência de ordenação comprovada; timestamp tardio; cobertura desconhecida; carteira e classificação BUY derivada; leitura SQL read-only; API e alvos HTML independentes; sem promoção de qualidade de fonte ou de permissão financeira.

**Política de sequência/slot:** a query SQLite não fornece um domínio de ordenação de ledger independente; portanto a leitura do histórico não deve inferir slot regressivo pela ordem das linhas (podem vir em `DESC`). `ordering_domain_unverified` preserva a lacuna e bloqueia qualquer uso como prova cronológica. Um futuro conector deverá validar ordenação de origem com stream/checkpoint explícitos. Nenhum rollback de slot artificial é declarado como falha live.

**Classificação e risco:** a presença de BUY/SELL e pool inicializado é observacional. Não há prova de liquidez atual, segurança do token, proprietário independente de carteiras, profundidade executável, assinaturas econômicas completas ou cobertura contínua. A integração de inteligência/classificador com contratos de oportunidades e simulação continua **bloqueada por evidência incompleta**; não habilitar papel/ordem via flags do chamador.

## Homologação live — PR #113 isolada

Foi criada [PR Draft #113](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/113), derivada diretamente do commit de `main` `5060bc6`, e sua comparação com `main` mostra **exatamente um arquivo novo**, `.github/workflows/smr-cm27-live-gate.yml`. Não há código funcional não relacionado. Ela **não foi mergeada**, ainda depende de revisão/aceitação humana e depois de acionamento manual `workflow_dispatch` com opt-in `READ_ONLY_BOUNDED_CM27` na branch com script de captura. A conexão GitHub do ChatGPT não expõe operação para disparar workflows; nenhuma captura foi executada.

## Continuidade e prioridades

1. **Próximo módulo de maior impacto:** integrar o *writer* e o *stream cursor/backfill* originais do Launch Radar das PRs #69–#76 ao SQLite existente, sem substituir os caminhos antigos, usando contratos de origem/slot/RAW; testes específicos de checkpoint, replays, abertura read-only e conflitos.
2. Conectar envelope transacional de origem (inclusive identidade RAW e assinatura/slot) a consenso Smart Money e classificação de segurança/liquidez por *cutoff*, mantendo classificação UNKNOWN diante de falta de fontes independentes.
3. Acoplar decisões somente a replay paper com bid/ask e custos auditáveis depois da atestação suficiente. Não simular PnL executável com evidência local.
4. Após aprovação humana de #113, registrar workflow na default branch, executar captura limitada e auditar artifact; se não houver desconexão natural, classificação A, nunca B.

A meta 14–21 dias continua sendo somente a primeira versão integrada. Os dois radares e funcionalidades futuras permanecem no escopo completo. Um executor principal, zero agentes auxiliares. Economia de créditos **não mensurável**.

## Percentuais (estimativas por aceitação, NÃO progresso global)

- CM27 recuperação persistente offline: **100% dos cenários acordados**, não equivale a endurance Android/live.
- CM30 leitura/contrato de eventos históricos: **100% do escopo implementado testado** (1081 testes na suíte integrada), não da operação completa dos produtores.
- Launch writer/monitor integrado na branch #111: **0% neste incremento**; módulos originais preservados nas branches antigas, integração pendente.
- Homologação live neste incremento: **0%**, nenhuma nova captura.
- Operação 24h e compra/venda real: **não homologadas**, sem percentual global tecnicamente mensurável.
