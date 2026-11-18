# SMART MONEY RADAR — Registro Mestre atualizado — Etapa 7

Data: 16/11/2026

## Estratégia preservada

- Solana é prioridade absoluta da V1; arquitetura extensível, sem implementar
  outras chains agora.
- Dois radares independentes planejados: Launch Radar e Market Radar.
- Modos IMMEDIATE e CONFIRMATION devem compartilhar os mesmos bloqueios de
  segurança.
- Inteligência de carteiras e aprendizagem histórica não podem contornar
  segurança nem alterar regras produtivas sem validação.
- Operação futura 24/7 em VPS independente do celular.
- Nenhum serviço pago, rede externa ou execução de transação será ativado sem
  autorização explícita e verificação de custos.

## Estado técnico comprovado

Base atual é um monitor Solana somente leitura, ainda parcial. O conjunto
existente cobre cliente Helius HTTP/WebSocket, monitor de carteiras, backfill,
parser conservador, EventStore SQLite, payload bruto, replay, backup e métricas
básicas. Testes são simulados.

### Etapas concluídas nesta sequência

1. WalletMonitor/Helius: checkpoint, backfill e retry.
2. Robustez/lifecycle: deduplicação de notificações, shutdown do loop/executor.
3. Parser: validações de campos RPC e testes de instruções internas.
4. Ingestão/replay: arquivamento bruto e reprocessamento sem mover checkpoint.
5. Armazenamento: integrity_check, estatísticas e backup SQLite consistente.
6. Inventário e validação estrita do parser.
7. Contratos tipados de domínio (esta etapa).

## Etapa 7 — contratos de domínio

Adicionados em `src/smart_money_radar/domain/models.py`:
- `ObservedTransaction`
- `TokenBalanceDelta`
- `SwapObservation`
- `PoolSnapshot`
- `WalletProfile`

Os contratos têm validações para campos obrigatórios, quantidades, escala SPL,
confiança/evidências, reservas, métricas e consistência temporal. `Wallet` e
`ActivityEvent` permanecem compatíveis.

**Limite importante:** os novos tipos ainda não foram conectados ao monitor,
parser e armazenamento. Não existem Launch Radar, Market Radar, Swap Decoder,
Wallet Intelligence, Decision Engine, Risk Manager, Portfolio Manager,
Execution Engine ou app operacional implementados nesta base.

## Testes e qualidade

- 53 testes `unittest` aprovados.
- `compileall` aprovado.
- 6 testes novos de contratos de domínio.
- Sem conexão real com Helius/Solana, teste de carga, benchmark ou deploy.

## Próxima tarefa exata

Criar adaptadores de normalização para ligar o parser atual aos contratos
`ObservedTransaction` e `TokenBalanceDelta`, preservando `ActivityEvent` e o
esquema SQLite. Adicionar fixtures anonimizadas de swaps reais de programas
Solana prioritários. Só depois criar um `SwapDecoder` verificável. Não iniciar
novos motores de inteligência antes de estabilizar a semântica de ingestão.

## Artefatos

- `SMR-CODIGO-BASE-ETAPA7-2026-11-16.zip`
- `AUDITORIA-CONTRATOS-DOMINIO-ETAPA7-2026-11-16.md`
- `REGISTRO-MESTRE-SMR-ATUALIZADO-2026-11-16-ETAPA7.md`

Esta cópia é local de auditoria. Não está implantada no telefone, Replit ou VPS.
