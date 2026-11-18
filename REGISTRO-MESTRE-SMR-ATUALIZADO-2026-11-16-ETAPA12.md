# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-16 — Etapa 12

## 1. Estado executivo

Fase atual: auditoria/consolidação da ingestão e preparação dos decodificadores Solana por programa.
Prioridade V1: Solana; arquitetura extensível sem implementar multichain agora.
Estado real: coletor/monitor Solana somente leitura com Helius RPC/WebSocket configurável, backfill, parser conservador, payload bruto, replay, normalização integrada e registro versionado de programas prioritários. O SMR completo não está implementado, integrado ou operando 24/7.

## 2. Base de referência e continuidade

Base mais recente: pacote Etapa 11 gerado nesta sessão, derivado da base Etapa 10. Antes da Etapa 11: 66/66 testes aprovados. Após Etapa 11: 71/71 testes aprovados.

## 3. Etapas consolidadas

- Etapas 1–6: robustez monitor/Helius, backfill, retries, shutdown, parser conservador, payload bruto/replay, integridade/backup e inventário.
- Etapa 7: contratos de domínio mínimos.
- Etapa 8: normalizador de transação.
- Etapa 9: integração do normalizador no WalletMonitor e persistência atômica no EventStore.
- Etapa 10: matriz programática de 15 programas Solana, classificação core/launchpad/AMM/aggregator, prioridades e fontes; cinco assinaturas mainnet públicas candidatas documentadas; protocolo de fixtures reais anonimizadas.
- Etapa 11: coletor JSON-RPC HTTPS somente leitura para `getTransaction` finalized, CLI, manifesto de proveniência e SHA-256, proteção contra sobrescrita e cinco testes.

## 4. Atualização técnica — Etapa 10

Novos arquivos:
- `src/smart_money_radar/domain/program_registry.py`
- `tests/test_program_registry.py`
- `docs/fixtures/ETAPA10-MATRIZ-PROGRAMAS-E-FIXTURES.md`
- `AUDITORIA-MATRIZ-PROGRAMAS-FIXTURES-ETAPA10-2026-11-16.md`

Atualizado: `README.md`.

O registro de programas valida IDs Base58 como chaves públicas de 32 bytes, unicidade e metadados. Jupiter v6 é classificado como agregador, `venue=False`, para evitar dupla contagem da rota e das venues chamadas por CPI. Pump.fun Bonding Curve e PumpSwap são programas distintos.

Candidatos a fixture documentados: Raydium CPMM, Raydium AMM v4, Jupiter v6, Meteora DLMM e Meteora DAMM v2. São assinaturas reais localizadas em páginas públicas de explorer, com slot e status resumido. **Não são fixtures aprovadas**, pois os payloads RPC brutos ainda não foram coletados.

Validação: 66 testes aprovados, 0 falhas; compileall aprovado.

## 5. Limite de coleta

A tentativa de conexão ao RPC público `api.mainnet-beta.solana.com` falhou por DNS indisponível no runtime. Na Etapa 11 foi implementado um coletor para executar a coleta em ambiente com RPC HTTPS alcançável. Nenhuma chamada Helius, chave ou crédito foi utilizado. Não foram criados JSONs fictícios. Payloads brutos reais, SHA-256 de transações candidatas e projeções anonimizadas seguem pendentes.

## 6. Arquitetura atual comprovada

`CLI -> WalletMonitor -> HeliusDataSource -> JSON-RPC/WebSocket`

`WalletMonitor -> normalize_transaction -> ObservedTransaction + TokenBalanceDelta + ActivityEvent`

`WalletMonitor -> SQLiteEventStore -> observed_transactions / token_balance_deltas / activity_events / checkpoints`

`domain.program_registry -> classificação de Program IDs (catálogo, não decodificador)`

Não existem ainda decodificadores semânticos de swaps/launchpads/AMMs, Launch Radar, Market Radar, Wallet Intelligence completo, Decision Engine, Risk Manager, Portfolio Manager, Execution Engine, paper trading, backtesting, ML, app ou deploy 24/7.

## 7. Restrições preservadas

- Solana V1; sem multichain nesta fase.
- Launch Radar e Market Radar permanecem pipelines independentes planejados.
- IMMEDIATE e CONFIRMATION compartilham bloqueios de segurança.
- Aprendizagem não contorna segurança nem altera regras produtivas sem validação.
- Sem assinatura/envio de transações ou trades reais.
- Sem endpoint pago, créditos Helius ou VPS sem autorização explícita.
- Não rotular resumo de explorer ou fixture sintética como payload bruto real.

## 8. Atualização técnica — Etapa 11

Novos arquivos: `src/smart_money_radar/data_sources/rpc_fixture_collector.py`, `tools/collect_solana_fixtures.py`, `tests/test_rpc_fixture_collector.py`, `docs/fixtures/ETAPA11-COLETOR-RPC-EVIDENCIAS.md` e `AUDITORIA-COLETOR-RPC-ETAPA11-2026-11-16.md`. README atualizado.

O coletor exige HTTPS, usa `finalized`, valida assinatura/slot/JSON, preserva bytes recebidos, calcula SHA-256, cria manifest e impede sobrescrita. A suíte completa passou com 71 testes. A coleta remota continua não realizada devido ao bloqueio DNS/RPC deste runtime.

## 9. Atualização técnica — Etapa 12

Foi implementado auditor offline de evidências em `src/smart_money_radar/data_sources/fixture_audit.py`, CLI `tools/audit_solana_fixtures.py` e cinco testes em `tests/test_fixture_audit.py`. O auditor confere manifesto, política finalized/JSON, marcador de bruto não anonimizado, segurança do nome de arquivo, SHA-256 e correspondência de slot/assinatura entre manifesto e payload. Não acessa rede, não altera os arquivos e não declara aprovação semântica.

Os payloads sintéticos dos testes são apenas testes do auditor, não fixtures mainnet. A coleta real continua pendente por conectividade DNS/RPC.

## 10. Próxima tarefa exata

Executar a coleta das assinaturas candidatas em ambiente com RPC HTTPS acessível; rodar o auditor offline; revisar a estrutura e os programas/instruções invocados; criar projeção anonimizada separada; aprovar a primeira fixture. Só então implementar o decodificador correspondente. Não iniciar motores de inteligência nem execução financeira.

## 11. Protocolo de continuidade

Usar este registro e o pacote Etapa 11 como referência mais recente. Consultar artefatos antes de alterar código. Atualizar o registro e o pacote ao concluir cada etapa. Separar especificado, implementado, integrado, testado, validado remotamente e em produção.
