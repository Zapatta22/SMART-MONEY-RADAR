# SMR — Inventário de módulos e validação estrita do parser (Etapa 6)

Data: 16/11/2026  
Escopo: código-base local de auditoria; sem implantação.

## 1. Correção de parsing realizada

A revisão identificou coerção permissiva de tipos em campos RPC: `int(6.9)` truncava a escala SPL para 6, strings numéricas eram aceitas e `blockTime` aceitava float. Como isso pode alterar quantias ou horário, o parser agora exige:

- `blockTime`: inteiro JSON e não booleano;
- `uiTokenAmount.decimals`: inteiro JSON e não booleano, dentro de 0–255;
- `lamports`: inteiro JSON e não booleano.

Strings e floats não são convertidos silenciosamente. Testes novos cobrem decimais fracionários/textuais, lamports inválidos e timestamp fracionário.

## 2. Inventário real do código presente

| Módulo | Estado real | Limite principal |
|---|---|---|
| `domain/models.py` | Implementado: `Wallet`, `ActivityEvent` imutáveis e validação básica | Sem modelos de token, pool, swap, posição, ordem ou portfólio |
| `settings.py` | Implementado: configuração Helius, cluster, timeout, caminho SQLite e opt-in explícito de rede | Sem gestão dinâmica de limites/créditos Helius |
| `data_sources/base.py` | Implementado: protocolo síncrono `WalletDataSource` | Contrato não cobre streaming, health, cursor, batch ou provenance |
| `data_sources/helius.py` | Implementado: JSON-RPC HTTP, getVersion, getTransaction, getSignaturesForAddress, wrappers async por `to_thread` | Sem rate limiter, controle de créditos, circuit breaker, backpressure ou métricas de latência |
| `data_sources/solana.py` | Adaptador de compatibilidade para Helius | Não é fonte independente nem implementação multichain |
| `data_sources/transaction_parser.py` | Parser conservador de saldos token e instruções System transfer decodificadas | Não interpreta semanticamente swaps, AMMs, agregadores, LP, staking, lending, rent, fee/PnL/preço |
| `services/wallet_monitor.py` | Implementado: WebSocket, backfill, retry, checkpoint, persistência de observação e estados de parsing | Limites de backfill fixos; sem fila/worker escalável e sem monitoramento operacional completo |
| `services/wallet_tracker.py` | Implementado: consulta simples através do protocolo de fonte | Não calcula performance, reputação ou relações entre carteiras |
| `storage/event_store.py` | Implementado: SQLite, eventos, payload bruto, checkpoint, replay individual, WAL, integridade, stats e backup | Sem backup agendado/off-site, retenção, rotação, replay em lote ou migrações versionadas explícitas |
| `analysis/metrics.py` | Implementado: contagem de eventos por mint | Métricas descritivas mínimas, não inteligência preditiva |
| `cli.py` / `__main__.py` | Implementado: check e watch somente leitura, encerramento limpo | Sem API/app, serviço systemd, health endpoint, dashboard ou supervisor |

## 3. Componentes previstos que não existem no código atual

Não foram encontrados módulos implementados para:

- SMR Launch Radar e SMR Market Radar como pipelines independentes;
- normalização multi-DEX, descoberta de novos pools/pares e feed de lançamentos;
- decodificadores específicos de programas AMM/DEX e roteadores Solana;
- Wallet Intelligence: score histórico, qualidade de saída, clusters probabilísticos, sincronização e detecção de coordenação;
- Decision Engine, regras `IMMEDIATE`/`CONFIRMATION`, aprovação de sinais;
- Risk Manager com bloqueios de rug pull, liquidez, concentração, slippage, exposição e drawdown;
- Portfolio Manager, sizing, limites por posição e reconciliação de saldo;
- Execution Engine, simulador de swaps, roteamento, assinatura segura e confirmação on-chain;
- backtesting, paper trading, dataset histórico/ML, validação e promoção controlada de modelos;
- dashboard/app, autenticação, alertas, observabilidade e gestão de configuração remota;
- monitor de créditos Helius, orçamento de RPC e alertas de custo.

## 4. Mapa de dependências atual

`CLI -> WalletMonitor -> HeliusDataSource -> JSON-RPC/WebSocket`

`WalletMonitor -> transaction_parser -> ActivityEvent -> SQLiteEventStore`

`WalletTracker -> WalletDataSource Protocol -> HeliusDataSource`

`analysis.metrics -> ActivityEvent`

A arquitetura atual é uma vertical slice de coleta de atividade pública e persistência. Não é ainda uma plataforma de decisão/execução de trades. Não existe integração ponta a ponta dos radares com risco, portfólio e execução.

## 5. Dependências Python atuais

- Runtime: Python >=3.11.
- `python-dotenv >=1.0,<2.0`.
- `websockets >=14.0,<16.0`.
- Build: `setuptools >=68`.
- Testes: biblioteca padrão `unittest`.

Não há dependência atual de SDK de swap/DEX, ML, banco externo, fila distribuída, framework web ou UI.

## 6. Validação

- `PYTHONPATH=src python -m unittest discover -s tests -q`: **47 testes aprovados, 0 falhas**.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- Testes locais com doubles/mocks; nenhuma conexão real com Helius/Solana e nenhum teste de performance.

## 7. Conclusão técnica e prioridade recomendada

O código atual deve ser classificado como **coletor/monitor Solana somente leitura com persistência local e recuperação básica**, não como robô de trading. A próxima prioridade não é criar mais nomes de motores; é transformar a vertical slice numa base operacional confiável e estabelecer contratos de integração. Sequência recomendada:

1. Criar contratos de domínio para `ObservedTransaction`, `TokenBalanceDelta`, `SwapObservation`, `Pool/MarketSnapshot` e `WalletProfile`, sem afirmar que já há dados para todos.
2. Implementar ingestão normalizada e decodificadores Solana por programa, com fixtures reais anonimizadas e versionadas.
3. Adicionar rate limiting, budget/credit accounting Helius, métricas de latência, retries classificados e backpressure.
4. Implementar backup agendável, teste de restauração e alertas de armazenamento no host.
5. Só então compor Launch Radar e Market Radar como pipelines separados e integrar Decision/Risk/Portfolio em modo paper trading.

**Não habilitar dinheiro real ou assinatura/envio de transações nesta fase.**
