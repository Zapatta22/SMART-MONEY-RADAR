# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-16 — Etapa 10

## 1. Estado executivo

Fase atual: auditoria/consolidação da ingestão e preparação dos decodificadores Solana por programa.
Prioridade V1: Solana; arquitetura extensível sem implementar multichain agora.
Estado real: coletor/monitor Solana somente leitura com Helius RPC/WebSocket configurável, backfill, parser conservador, payload bruto, replay, normalização integrada e registro versionado de programas prioritários. O SMR completo não está implementado, integrado ou operando 24/7.

## 2. Base de referência e continuidade

Base mais recente: `SMR-CODIGO-BASE-ETAPA9-2026-11-16.zip`. A suíte foi reexecutada antes das alterações da Etapa 10: 62/62 testes aprovados.

## 3. Etapas consolidadas

- Etapas 1–6: robustez monitor/Helius, backfill, retries, shutdown, parser conservador, payload bruto/replay, integridade/backup e inventário.
- Etapa 7: contratos de domínio mínimos.
- Etapa 8: normalizador de transação.
- Etapa 9: integração do normalizador no WalletMonitor e persistência atômica no EventStore.
- Etapa 10: matriz programática de 15 programas Solana, classificação core/launchpad/AMM/aggregator, prioridades e fontes; cinco assinaturas mainnet públicas candidatas documentadas; protocolo de fixtures reais anonimizadas.

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

A tentativa de conexão ao RPC público `api.mainnet-beta.solana.com` falhou por DNS indisponível no runtime. Nenhuma chamada Helius, chave ou crédito foi utilizado. A etapa não criou JSONs fictícios. Payloads brutos, SHA-256 e projeções anonimizadas seguem pendentes.

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

## 8. Próxima tarefa exata

Coletar `getTransaction` finalized para as assinaturas candidatas documentadas, quando houver RPC de leitura autorizado e acessível; arquivar JSON bruto, hash, proveniência e projeção anonimizada; aprovar fixtures por protocolo. Depois implementar decodificadores específicos começando pelo protocolo com fixture completa e verificável. Não iniciar novos motores de inteligência nem execução financeira.

## 9. Protocolo de continuidade

Usar este registro e o pacote Etapa 10 como referência mais recente. Consultar artefatos antes de alterar código. Atualizar o registro e o pacote ao concluir cada etapa. Separar especificado, implementado, integrado, testado, validado remotamente e em produção.
