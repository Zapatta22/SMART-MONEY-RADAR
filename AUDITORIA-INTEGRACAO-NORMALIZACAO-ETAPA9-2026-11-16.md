# SMR — Integração atômica da normalização — Etapa 9

Data: 16/11/2026  
Escopo: integrar os contratos da Etapa 7 e o adaptador da Etapa 8 ao fluxo existente de ingestão, mantendo compatibilidade e somente leitura.

## 1. Base de referência

A Library continha artefatos posteriores ao Registro Mestre colado na conversa: `REGISTRO-MESTRE-SMR-ATUALIZADO-2026-11-16-ETAPA7.md` e `REGISTRO-MESTRE-SMR-ATUALIZADO-2026-11-16-ETAPA8.md`, além do pacote `SMR-CODIGO-BASE-ETAPA8-2026-11-16.zip`. O pacote Etapa 8 foi recuperado e sua suíte original foi reexecutada antes das alterações: **58 testes aprovados, 0 falhas**.

## 2. Alterações realizadas

Arquivos alterados:
- `src/smart_money_radar/services/wallet_monitor.py`
- `src/smart_money_radar/storage/event_store.py`
- `src/smart_money_radar/domain/normalization.py`
- `tests/test_wallet_monitor.py`
- `tests/test_event_store.py`
- `tests/test_normalization.py`
- `README.md`

### WalletMonitor

- Substituído o uso direto de `parse_transaction` por `normalize_transaction`.
- O monitor continua preservando o comportamento de `parse_error`: se a normalização falhar, arquiva o payload bruto e registra o tipo da exceção.
- Quando normaliza com sucesso, envia ao EventStore o envelope, os deltas SPL e os eventos legados em conjunto.

### SQLiteEventStore

- Nova tabela `token_balance_deltas`, com chave por carteira, assinatura, mint e direção.
- Novas colunas em `observed_transactions`: `chain`, `slot` e `occurred_at`.
- Migração incremental por inspeção de `PRAGMA table_info` e `ALTER TABLE` somente para colunas ausentes; dados legados são preservados.
- `save_observation` aceita `normalized_observation` e grava envelope, deltas SPL, eventos legados, payload bruto, assinatura processada e checkpoint dentro da mesma transação SQLite.
- Valida correspondência entre carteira/assinatura, eventos legados e payload normalizado antes de gravar.
- `get_token_deltas` recupera os deltas tipados.
- `get_observation_metadata` passa a retornar cadeia, slot e horário on-chain.
- `reprocess_observation` substitui eventos e deltas derivados sem mover checkpoint nem modificar payload bruto; em replay sem resultado normalizado, remove deltas antigos para não deixar derivados obsoletos.
- `storage_stats` inclui a tabela de deltas.

### Normalização

- `TokenBalanceDelta.decimals` passa a ser preenchido quando os registros `preTokenBalances`/`postTokenBalances` da carteira concordam quanto à escala SPL.
- Escala ausente, inválida ou conflitante permanece `None`; não é inferida.
- SOL nativo continua excluído dos deltas SPL e permanece representado apenas no fluxo legado atual.

## 3. Testes adicionados/ajustados

- Persistência conjunta de envelope, deltas SPL e eventos legados.
- Migração de uma tabela `observed_transactions` legada sem perda de payload.
- Rollback forçado durante INSERT de delta: nenhum payload, evento, assinatura processada ou checkpoint fica parcialmente gravado.
- Replay de deltas normalizados sem mover checkpoint ou sobrescrever payload original.
- Backup/restauração preserva também deltas normalizados.
- Monitor utiliza normalizador integrado e preserva `parse_error` em exceção.
- Escala SPL propagada somente quando consistente.

## 4. Validação

- Suíte completa: **62 testes aprovados, 0 falhas**.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- Testes locais com SQLite e doubles; nenhuma chamada real à Helius/Solana.
- Sem benchmark, teste de carga, validação remota ou implantação.

## 5. Limites remanescentes

- `SwapObservation` e `PoolSnapshot` continuam sem origem semântica confiável; nenhum swap/pool é inferido nesta etapa.
- Não foram adicionadas fixtures de transações reais; não fabricar fixtures simuladas e rotulá-las como reais.
- `WalletMonitor` ainda não executa decodificação específica por programa.
- Sem rate limiter, budget de créditos Helius, circuit breaker, backpressure ou métricas completas de latência.
- Alterações existem apenas nesta cópia local de auditoria, não instaladas no ambiente original, Replit ou VPS.

## 6. Próxima tarefa exata

Iniciar a preparação dos fixtures reais anonimizados para os programas Solana prioritários da V1: definir uma matriz de programas/instruções a cobrir, obter transações públicas verificáveis, preservar proveniência (assinatura/slot/program IDs e origem), anonimizar dados identificáveis não necessários e registrar expectativas observáveis. Só depois implementar decodificadores por programa. Não iniciar Launch Radar, Market Radar, Decision/Risk/Portfolio ou execução financeira nesta etapa.
