# Auditoria de Integridade de Ingestão e Replay — Etapa 4

**Data:** 2026-11-16  
**Escopo:** `SQLiteEventStore`, `WalletMonitor._collect_transaction`, persistência de payload bruto, estado de parsing e replay.

## Problema corrigido

Antes desta etapa, uma assinatura podia ser marcada como processada e o checkpoint avançado mesmo quando o parser não reconhecia eventos. Como o payload bruto não era armazenado, a transação ficava sem possibilidade de reinterpretação local quando a cobertura do parser evoluísse.

## Implementação

1. Nova tabela `observed_transactions`, com chave por carteira/assinatura, JSON bruto, `parse_status`, `parser_version`, `parse_error` e timestamp de observação.
2. Novo método `save_observation`: grava payload bruto, eventos derivados, assinatura processada e checkpoint dentro da mesma transação SQLite.
3. Estados explícitos:
   - `parsed`: parser produziu um ou mais eventos;
   - `no_events`: payload foi obtido, mas o parser não produziu eventos;
   - `parse_error`: parser lançou exceção; payload permanece armazenado;
   - `failed_on_chain`: assinatura identificada como transação falha na listagem on-chain, sem payload `getTransaction`.
4. `get_raw_transaction` recupera payload para auditoria/replay.
5. `get_observation_metadata` consulta estado e versão sem carregar o JSON bruto.
6. `reprocess_observation` substitui eventos derivados e atualiza versão/estado sem mover checkpoint; exige payload bruto existente.
7. `WalletMonitor` passou a usar persistência atômica e a registrar falhas de parsing sem descartar o payload.
8. `PARSER_VERSION` centraliza a versão do parser.
9. Compatibilidade de schema verificada ao reabrir banco SQLite criado antes da nova tabela.

## Testes

- Arquivamento atômico do payload e checkpoint.
- Reprocessamento com substituição de eventos e checkpoint preservado.
- Rejeição de reprocessamento sem observação/payload.
- Rejeição de eventos vinculados a outra assinatura.
- Payload preservado quando não há eventos reconhecidos.
- Payload preservado e estado `parse_error` quando parser lança exceção.
- Falha on-chain registrada com estado explícito.
- Migração aditiva do schema em banco existente.

Resultado da suíte completa: **41 testes aprovados, 0 falhas**. `compileall` aprovado. Testes simulados, sem rede.

## Riscos remanescentes

- Não há política automática de retenção/compactação de `observed_transactions`; o banco pode crescer significativamente em operação 24/7.
- Não há worker de replay em lote nem painel de observações `no_events`/`parse_error`; os métodos de base existem, a orquestração ainda não.
- Parser ainda não reconstrói swaps e semântica completa de programas Solana.
- Não houve validação remota Helius/Solana, benchmark de escrita, teste de carga ou teste de crash/power-loss no meio da transação.
- Os dados continuam em SQLite local; não há replicação/backup automatizado implementado.

## Próxima tarefa exata

Auditar armazenamento e operação contínua: definir retenção de payloads, índices/volume, backup/recuperação, fila de replay e métricas de ingestão. Em paralelo, concluir inventário dos módulos existentes e mapa de dependências. Não iniciar motores de inteligência ou execução de trades antes de fechar integridade, cobertura de dados e risco operacional.

## Estado de implantação

Somente cópia local de auditoria. Não instalado no ambiente do usuário, Replit ou VPS. Sem chamadas reais à Helius/Solana.
