# SMART MONEY RADAR (SMR) — REGISTRO MESTRE

**Última atualização:** 2026-11-16  
**Regra de continuidade:** este documento é a referência operacional do projeto. Atualizar ao concluir cada etapa relevante. Antes de propor trabalho novo, consultar este registro e os artefatos existentes. Não reabrir decisões já aprovadas sem evidência de conflito técnico.

## 1. Estado executivo

- **Fase atual:** auditoria global da arquitetura e preparação para implementação.
- **Escopo realizado até aqui:** planejamento, especificações, código-base parcial e testes isolados.
- **Não confundir:** o SMR completo NÃO está implementado, integrado ou operando 24/7.
- **Prioridade da V1:** Solana. Preservar arquitetura extensível a outras chains sem implementar multichain agora.
- **Diretriz:** não iniciar novos motores de inteligência até concluir inventário, lacunas, dependências e plano de implementação.
- **Modo de trabalho:** cada tarefa deve produzir artefato, alteração de código, teste, decisão objetiva ou bloqueio claramente identificado. Evitar rebatizar funcionalidades já especificadas.

## 2. Evidências e artefatos encontrados

### 2.1 Pacote de código-base recuperado

Arquivo de origem na Library: `SMART-MONEY-RADAR-TODOS-ARQUIVOS.md` (58.744 bytes; criado em 2026-11-10). Contém 28 seções de arquivos, extraídas para um ambiente temporário de auditoria.

Estrutura encontrada:

- `cli.py`, `settings.py`
- `analysis/metrics.py`
- `data_sources/base.py`, `helius.py`, `solana.py`, `transaction_parser.py`
- `domain/models.py`
- `services/wallet_monitor.py`, `wallet_tracker.py`
- `storage/event_store.py`
- 6 arquivos de testes `unittest`
- README, pyproject, .env.example e .gitignore

Limites comprovados pelo README e pelo código: leitura somente; sem envio/assinatura de transações; endereços de carteiras são informados explicitamente; Helius é configurada via ambiente; SQLite registra eventos; testes usam respostas simuladas.

### 2.2 Execução de testes em 2026-11-16

- Extração dos arquivos: concluída.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: **15 testes aprovados, 0 falhas** na versão recuperada.
- `python -m compileall -q src tests`: aprovado.
- `PYTHONPATH=src python -m smart_money_radar`: inicialização básica aprovada, sem rede.
- Testes não conectaram à Solana/Helius; portanto não comprovam disponibilidade da API, credenciais, latência ou funcionamento em produção.

### 2.3 Defeito reproduzido e correção na cópia de auditoria

- Defeito: `SQLiteEventStore(":memory:")` abria conexões independentes; o schema criado na inicialização desaparecia quando a conexão era fechada. A gravação falhava com `sqlite3.OperationalError: no such table: activity_events`.
- Correção aplicada somente na cópia temporária de auditoria: manter uma conexão de memória viva, reutilizá-la nas operações e oferecer `close()`.
- Teste de regressão adicionado em `tests/test_event_store.py`.
- Resultado após correção: **16 testes aprovados, 0 falhas**.
- Estado da correção: corrigida e testada na cópia de auditoria; ainda NÃO aplicada ao ambiente original do usuário nem sincronizada ao pacote-fonte da Library.

## 3. Inventário de implementação comprovada

| Área | Evidência atual | Estado |
|---|---|---|
| Estrutura Python / CLI | Arquivos presentes; CLI inicia | Implementação parcial |
| Configuração Helius | Leitura de ambiente, bloqueio de rede por padrão | Implementada na base; integração real não validada |
| Helius JSON-RPC | Cliente de leitura e testes simulados | Implementação parcial; sem teste remoto |
| WebSocket `logsSubscribe` | Monitor de carteiras explícitas e reconexão | Implementação parcial; sem validação em produção |
| Parser de transações | Saldos de tokens e transferências SOL decodificadas | Implementado parcialmente; cobertura limitada |
| SQLite Event Store | Persistência e deduplicação; defeito `:memory:` corrigido na cópia | Implementação parcial |
| Métricas por mint | Contagens descritivas | Implementadas; não é inteligência preditiva |
| Testes automatizados | 16 testes locais aprovados após correção | Testado isoladamente |
| Integração ponta a ponta Helius → decisão → portfólio | Não encontrada no pacote | Ausente |
| Launch Radar | Especificação prévia; não consta no pacote | Especificado, não implementado |
| Market Radar | Especificação prévia; não consta no pacote | Especificado, não implementado |
| Decision Engine completo | Requisitos prévios; não consta no pacote | Especificado, não implementado |
| Risk Manager completo | Requisitos prévios; não consta no pacote | Especificado, não implementado |
| Portfolio Manager | Não consta no pacote | Especificação prévia; implementação não comprovada |
| Execução de swaps/compras/vendas | Não consta no pacote; base atual é somente leitura | Ausente |
| Interface/app operacional | Não consta no pacote | Ausente / não comprovada |
| VPS, deploy, supervisão 24/7 | Não consta no pacote | Não implementado / não validado |

## 4. Lacunas e riscos prioritários identificados

1. **Perda de eventos durante desconexões:** reconexão WebSocket existe, mas não foi encontrada rotina de backfill com `getSignaturesForAddress` após reconectar. Risco de lacunas no histórico.
2. **Transação temporariamente indisponível:** se `getTransaction` retornar `None`, o evento é ignorado; não foi encontrada fila durável ou política de repetição.
3. **Processamento serial:** enriquecimento e gravação ocorrem no fluxo de recebimento; throughput e latência sob volume ainda não foram medidos.
4. **Cobertura do parser:** parser atual cobre determinados saldos e instruções system decodificadas; não equivale a decodificar integralmente todos os swaps/programas Solana.
5. **Descoberta de tokens/pools:** não encontrada. O monitor acompanha endereços fornecidos manualmente.
6. **Sem motores de decisão/risco/portfólio integrados:** não há caminho operacional desde sinal até decisão de trade.
7. **Sem execução de transações:** correto para a base atual, que é explicitamente somente leitura.
8. **Sem validação remota:** Helius, limites de plano, latência e confiabilidade da conexão ainda não foram testados nesta auditoria.

## 5. Decisões estratégicas já aprovadas a preservar

- Solana é prioridade absoluta na V1; preparar extensibilidade multichain sem construir outras chains agora.
- Dois radares independentes: SMR Launch Radar e SMR Market Radar.
- Dois modos de entrada configuráveis desde o início: `IMMEDIATE` e `CONFIRMATION`, ambos sujeitos aos mesmos bloqueios de segurança.
- Nenhuma aprendizagem autônoma pode ignorar bloqueios de segurança ou alterar regras de execução sem validação.
- Aprendizagem exige histórico, avaliação em simulação e implantação controlada.
- Segurança, risco e portfólio são camadas centrais, não opcionais.
- Monitoramento de carteiras deve considerar desempenho histórico, qualidade das saídas, relações probabilísticas entre carteiras, coordenação, latência e contexto de mercado.
- Medir latência de ponta a ponta e invalidar/reavaliar sinais atrasados.
- Registrar consumo de Helius e alertar antes de atingir limites.
- Objetivo de operação contínua 24/7 em VPS independente do celular.
- VPS Contabo Cloud VPS Plus 4 foi preferência preliminar, sujeita a teste de latência/estabilidade e conferência de preço antes de contratação.
- Não contratar infraestrutura paga ou habilitar chamadas externas sem decisão explícita e conferência de custos/limites.

## 6. Plano de execução — ordem de trabalho

### Etapa 1 — Fechar auditoria do código-base existente
- Verificar integralmente os 18 módulos Python e 6 arquivos de teste.
- Corrigir e testar lacunas do monitor (backfill, retry de `getTransaction`, shutdown e duplicidade).
- Auditar parser e cobertura dos programas/formatos necessários à V1.
- Registrar cada achado com arquivo, função, evidência, impacto e teste.

### Etapa 2 — Consolidar arquitetura executável V1
- Mapear contratos de dados e interfaces entre fontes, Launch Radar, Market Radar, Wallet Intelligence, Decision Engine, Risk Manager e Portfolio Manager.
- Identificar módulos realmente ausentes versus já cobertos pela base.
- Definir fronteiras e critérios de aceite sem inventar novos motores.

### Etapa 3 — Construir integração vertical em modo simulado
- Pipeline de dados → normalização → análise → bloqueios → decisão → portfólio simulado → logs.
- Validar ambos os modos de entrada sem executar transações reais.

### Etapa 4 — Simulação histórica e validação
- Persistência, replay de eventos, métricas, latência, falhas e avaliação de risco.
- Critérios de aprovação objetivos antes de qualquer execução real.

### Etapa 5 — Integração remota e implantação
- Só após validação offline: credenciais Helius, limites, testes remotos controlados, VPS, supervisão, alertas e operação contínua.
- Execução real permanece bloqueada até aprovação explícita e testes de segurança.

## 7. Protocolo anti-repetição entre conversas

Ao iniciar qualquer conversa nova sobre o SMR:

1. Consultar este `REGISTRO-MESTRE-SMR.md` e o pacote de código mais recente.
2. Ler a seção “Estado atual / Próxima tarefa” antes de propor qualquer trabalho.
3. Não repetir módulos classificados como especificados ou testados sem uma lacuna concreta identificada.
4. Atualizar este documento ao final de cada etapa, incluindo arquivos alterados, testes executados e resultado.
5. Manter separadas as etiquetas: **especificado**, **implementado**, **integrado**, **testado**, **validado remotamente** e **em produção**.
6. Se faltar acesso ao arquivo/código, informar precisamente o bloqueio e pedir somente o artefato indispensável; não reconstruir o projeto por suposição.

## 8. Estado atual / próxima tarefa exata

**Estado:** pacote-base extraído e auditado inicialmente; 16/16 testes aprovados na cópia corrigida; correção SQLite `:memory:` ainda não sincronizada ao pacote original.

**Próxima tarefa:** concluir auditoria técnica dos 18 módulos existentes, começando pelo `WalletMonitor` e `HeliusDataSource`, priorizando recuperação de eventos perdidos e retries de transações. Não iniciar novos motores de inteligência.

**Limite de evidência:** o pacote recuperado é um documento com arquivos-fonte. Não há evidência nesta etapa de que essa cópia esteja instalada no ambiente de desenvolvimento original, no celular, no Replit ou na VPS do usuário.


## 9. Atualização de execução — 2026-11-16 (WalletMonitor / Helius)

- Alterados: `storage/event_store.py`, `data_sources/helius.py`, `services/wallet_monitor.py`, `tests/test_wallet_monitor.py`, `README.md`.
- Checkpoint persistente `wallet_checkpoints` por carteira.
- Backfill incremental após conexão/reconexão, cronológico, com paginação e deduplicação.
- Retry de transação indisponível: 3 tentativas, backoff exponencial padrão de 0,5s. Cursor só avança após processamento.
- Backfill limitado a 10 páginas × 100 assinaturas; se cursor não encontrado, falha explicitamente sem avançar. Primeira execução sem checkpoint não varre histórico.
- Testes: 18 aprovados, 0 falhas; compilação aprovada. Testes simulados, sem rede.
- Ainda não sincronizado ao ambiente original/Replit/VPS.
- Próxima tarefa: testes de falhas de backfill/retry/deduplicação e revisão de encerramento limpo do monitor e SQLite.

## 10. Atualização consolidada — Etapa 2 (16/11/2026)

**Estado da cópia local:** Etapa 2 concluída e revalidada nesta sessão.

### Alterações/testes confirmados

- `WalletMonitor._collect_transaction` ignora assinaturas já processadas para
  aquela carteira, evitando duplicidade quando WebSocket e backfill se cruzam.
- `SQLiteEventStore.save_checkpoint` grava `processed_signatures` e atualiza
  `wallet_checkpoints` na mesma transação SQLite.
- CLI aguarda `shutdown_asyncgens()` e `shutdown_default_executor()` antes de
  fechar Event Store e event loop.
- Event Store fecha também no caminho de exceção; fechamento em memória é
  idempotente.
- Cobertura adicional para limite de backfill, retry esgotado, erro RPC,
  deduplicação de notificações sobrepostas e lifecycle normal/de erro.
- Reexecução em 16/11/2026: **26 testes aprovados, 0 falhas**; `compileall`
  aprovado. Testes simulados, sem conexão remota.

### Arquivos de referência desta etapa

- `AUDITORIA-WALLET-MONITOR-ETAPA2-2026-11-16.md`
- `SMR-CODIGO-BASE-ETAPA2-2026-11-16.zip`
- Este Registro Mestre atualizado.

### Limitações que permanecem

- Backfill com limite fixo de 10 páginas × 100 assinaturas por carteira por
  conexão; falha explicitamente ao ultrapassar o limite.
- Primeira execução sem checkpoint não faz histórico retroativo.
- Sem validação remota de paginação, disponibilidade, limites de crédito ou
  latência Helius.
- Parser Solana parcial; processamento serial; sem benchmark sob carga.
- A base segue somente leitura e não contém pipeline integrado de radar,
  decisão, risco, portfólio ou execução.

### Próxima tarefa exata

Prosseguir a auditoria do código-base existente, sem criar novos motores: revisar
a semântica e robustez do backfill/paginação e auditar o parser de transações
Solana, documentando programas e formatos suportados, lacunas e testes
necessários. Depois concluir inventário dos módulos existentes e mapa de
dependências para integração V1.

**Limite de implantação:** esta etapa está validada apenas na cópia local de
auditoria. Não está instalada no ambiente do usuário, Replit ou VPS e não está em operação 24/7.


## 11. Atualização de execução — Etapa 3 (Parser Solana / Helius)

**Arquivos alterados:** `src/smart_money_radar/data_sources/transaction_parser.py`, `tests/test_helius_parser.py`, `tests/test_helius_rpc.py`, `README.md`.

- Parser deixou de inferir saldo zero quando um dos arrays de saldo está ausente ou malformado.
- Validação de `decimals` SPL limitada a inteiro não booleano de 0 a 255.
- Testes para agregação de múltiplas contas token por mint e transferência SOL em `innerInstructions`.
- Testes RPC para paginação `before`/`until` e limite inválido.
- README atualizado com os formatos suportados e os limites atuais.
- Resultado da suíte completa: **33 testes aprovados, 0 falhas**; `compileall` aprovado. Testes simulados, sem conexão real à Helius/Solana.

### Achado prioritário para próxima etapa

`WalletMonitor._collect_transaction` avança checkpoint e marca assinatura processada mesmo quando `parse_transaction` retorna lista vazia. Como o payload bruto não é arquivado, transações não reconhecidas podem ficar sem dados para replay após evolução do parser. Antes de confiar nos sinais, implementar armazenamento durável de transação observada/payload bruto, estado de parsing e replay versionado, com política de retenção e controle de armazenamento.

### Limites do parser confirmados

- Deltas de tokens por mint dependem de `owner` nos `preTokenBalances`/`postTokenBalances`.
- Transferências SOL cobertas apenas quando instruções System Program `transfer`/`transferWithSeed` aparecem decodificadas em `jsonParsed`, inclusive inner instructions.
- Sem reconstrução geral de swaps/rotas/pools, SOL líquido, taxas, rent, recompensas, preços, USD, slippage ou PnL.
- `maxSupportedTransactionVersion` está fixado em 0.
- Sem fixtures reais abrangentes nem teste remoto.

### Próxima tarefa exata

Auditar e corrigir a integridade do ciclo de ingestão: persistir payload bruto/observação antes de avançar checkpoint, estados explícitos de parsing e replay seguro/versionado. Depois concluir auditoria de armazenamento, dependências e inventário global dos módulos existentes. Não iniciar novos motores de inteligência nem habilitar execução de trades.

**Implantação:** somente cópia local de auditoria; não instalada no ambiente do usuário, Replit ou VPS.


## 12. Atualização de execução — Etapa 4 (Ingestão bruta e replay)

**Arquivos alterados:** `storage/event_store.py`, `services/wallet_monitor.py`, `data_sources/transaction_parser.py`, testes de EventStore/WalletMonitor e README.

- Criada tabela `observed_transactions` para guardar JSON bruto, estado de parsing, versão do parser, erro e timestamp.
- `save_observation` grava payload, eventos, assinatura processada e checkpoint na mesma transação SQLite.
- Estados registrados: `parsed`, `no_events`, `parse_error` e `failed_on_chain`.
- `get_raw_transaction` e `get_observation_metadata` permitem auditoria; `reprocess_observation` substitui eventos derivados sem alterar checkpoint e exige payload existente.
- WalletMonitor agora preserva payload quando parser não reconhece eventos ou lança exceção; falhas on-chain recebem estado explícito.
- Versão do parser centralizada em `PARSER_VERSION`.
- Compatibilidade de schema com banco preexistente verificada.
- Suíte completa: **41 testes aprovados, 0 falhas**; `compileall` aprovado. Testes simulados, sem rede.

### Riscos remanescentes

- Ainda sem política automática de retenção/compactação; o banco pode crescer em operação contínua.
- Ainda sem worker de replay em lote, dashboard de `no_events`/`parse_error`, backup automatizado, replicação ou benchmark de volume.
- Sem validação remota, teste de carga ou teste de crash/power-loss.
- Parser segue parcial; nenhum motor de trading foi integrado.

### Próxima tarefa exata

Auditar armazenamento para operação 24/7: dimensionamento e retenção, backup/recuperação, replay em lote e métricas de ingestão. Concluir inventário dos módulos e mapa de dependências da V1. Não iniciar novos motores nem execução de trades antes de fechar integridade e risco operacional.

**Implantação:** somente cópia local de auditoria; não instalada no ambiente do usuário, Replit ou VPS.

## 13. Atualização de execução — Etapa 5 (Armazenamento, integridade e backup)

**Arquivos alterados:** `src/smart_money_radar/storage/event_store.py`, `tests/test_event_store.py`, `README.md`.

- Conexões SQLite em disco usam timeout de 15 segundos, `busy_timeout=15000`, journal `WAL` e `synchronous=NORMAL`.
- Implementado `integrity_check()` com `PRAGMA integrity_check`.
- Implementado `storage_stats()` com contagens das tabelas operacionais e estimativa de tamanho lógico por páginas.
- Implementado `backup_to(destination)` com API online-backup do SQLite, criação de diretório, bloqueio de destino igual ao banco de origem e verificação de integridade do arquivo resultante.
- Teste de restauração abriu o backup como novo banco, verificou `integrity_check = ok` e recuperou payload bruto e checkpoint.
- Testes adicionais cobrem estatísticas e proteção contra sobrescrever o próprio banco.
- Suíte completa reexecutada: **44 testes aprovados, 0 falhas**; `compileall` aprovado. Testes locais/simulados; sem RPC real, carga, falha física de disco ou VPS.

### Limitações remanescentes

- Backup é uma capacidade explícita, não uma rotina agendada.
- Não há retenção/rotação, criptografia externa, cópia off-site, alerta de backup falho ou teste periódico de restauração em VPS.
- `storage_stats()` informa tamanho lógico estimado por páginas e não mede necessariamente os arquivos WAL/SHM.
- Política de retenção de payload bruto continua indefinida; não excluir dados automaticamente.
- Não há benchmark de escrita concorrente ou validação de comportamento após power-loss.

### Próxima tarefa exata

Fechar o ciclo operacional de armazenamento sem excluir dados: definir um procedimento agendável de backup e restauração, verificação de backup recente, alerta de espaço e métrica de crescimento. Depois concluir inventário global de módulos/dependências e mapa de integração V1. Só então priorizar integração dos dois radares e motores decisórios. Não iniciar execução de trades.

**Implantação:** mudanças existem apenas na cópia local de auditoria. Não estão instaladas no ambiente do usuário, Replit ou VPS e não estão em operação 24/7.

## 14. Atualização de execução — Etapa 6 (Inventário e validação estrita)

**Arquivos alterados:** `data_sources/transaction_parser.py`, `tests/test_helius_parser.py`, `README.md`; novo relatório `AUDITORIA-INVENTARIO-MODULOS-ETAPA6-2026-11-16.md`.

- Parser agora exige `blockTime`, `decimals` SPL e `lamports` como inteiros JSON não booleanos. Remove coerções permissivas de floats e strings que poderiam truncar escala ou aceitar quantias ambíguas.
- Inventário documenta o estado real dos módulos, dependências Python e componentes de arquitetura ainda inexistentes.
- Mapa atual confirma uma vertical slice de coleta/monitoramento Solana somente leitura e persistência; não há Launch/Market Radar integrado, Wallet Intelligence completo, Decision/Risk/Portfolio/Execution Engine, app, backtesting ou ML implementados.
- Suíte completa: **47 testes aprovados, 0 falhas**; `compileall` aprovado. Sem rede real ou benchmark.

### Próxima tarefa exata

Usar o inventário para especificar contratos de domínio mínimos e o pipeline de ingestão normalizada, seguido de decodificadores Solana por programa com fixtures reais anonimizadas. Em paralelo, planejar rate limit/budget Helius e observabilidade. Não criar motores duplicados nem habilitar execução financeira nesta fase.

**Implantação:** somente cópia local de auditoria; não instalada no ambiente do usuário, Replit ou VPS.
