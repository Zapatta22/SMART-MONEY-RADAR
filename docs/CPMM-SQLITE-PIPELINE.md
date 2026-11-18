# Pipeline de observação CPMM → SQLite

## Escopo

Este fluxo conecta o monitor de carteiras ao decoder Raydium CPMM, aos decoders SPL/Token-2022, à reconciliação econômica, ao builder dos contratos de domínio e ao EventStore SQLite.

É somente leitura. Não cria, assina ou envia transações, não calcula sinal de entrada e não executa compras ou vendas.

## Fluxo operacional

1. `WalletMonitor` recebe a assinatura via WebSocket ou backfill e consulta `getTransaction`.
2. `process_raydium_cpmm_observation()` valida a assinatura informada quando o payload contém `transaction.signatures`.
3. `normalize_transaction()` cria o envelope e os eventos legados.
4. `save_observation(..., advance_checkpoint=False)` arquiva o payload e a observação sem avançar o cursor.
5. Transações falhadas on-chain ou sem instruções CPMM reconhecidas são marcadas como processadas depois do arquivamento.
6. Para swaps CPMM, os decoders reconstroem instruções, transferências e deltas por token account (`include_unchanged=True`).
7. O reconciliador classifica cada swap como `MATCHED`, `INCOMPLETE` ou `AMBIGUOUS`; o builder recebe somente `MATCHED`.
8. Cada bundle (`SwapObservation`, `SwapClassification`, `SwapEvidence`) é persistido atomicamente e de forma idempotente.
9. O checkpoint só avança depois que todos os swaps CPMM decodificados tiverem uma reconciliação correspondente e todos os bundles `MATCHED` tiverem sido persistidos.

## Política fail-closed e replay

- Qualquer swap `INCOMPLETE` ou `AMBIGUOUS` mantém a transação pendente; nenhum checkpoint é avançado.
- Se o decoder reconhecer N swaps, mas o reconciliador retornar quantidade diferente de N, a transação também permanece pendente.
- Se houver falha de parsing/reconstrução, o payload bruto é preservado, o estado recebe `parse_error` e o checkpoint não avança. A mensagem bruta da exceção não é persistida; somente seu tipo.
- Bundles `MATCHED` já gravados permanecem no banco. O replay é seguro porque `operation_id` é determinístico e `save_swap_bundle()` é idempotente.
- `get_pending_signatures()` lista observações com payload que ainda não aparecem em `processed_signatures`. O monitor tenta recuperá-las antes do backfill normal, inclusive na primeira execução; não inicia varredura histórica ampla quando ainda não existe checkpoint.
- A lista de pendências é limitada por `backfill_page_limit × backfill_max_pages`; exceder o limite interrompe a recuperação sem avançar o cursor.

## Configuração

O monitor aceita `reference_mints` como sequência explícita de mints de referência. Sem configuração, o builder mantém a classificação `UNKNOWN`. A lista deve ser fornecida pelo operador ao construir `WalletMonitor`; não há inferência automática de ativo de cotação.

## Limites conhecidos

- A primeira versão reconstrói somente Raydium CPMM; outros programas/venues não são persistidos por este adaptador.
- O armazenamento dos bundles é atômico por operação, não para o conjunto inteiro de uma transação multi-swap. Se o processo falhar entre bundles, o replay completa as operações restantes sem duplicar IDs.
- Swaps não reconciliados ficam pendentes para replay/auditoria; a tabela append-only `swap_reconciliation_attempts` registra os resultados negativos e o motivo por operação/tentativa.
- `query_swap_reconciliation_attempts()` permite filtrar histórico por carteira, assinatura, `operation_id`, status e intervalo temporal, com limite explícito.
- `get_reconciliation_diagnostics()` retorna totais, operações/assinaturas distintas, contagem por status, motivos recorrentes e observações arquivadas ainda pendentes. O relatório limita a lista detalhada de pendências a 100 itens e informa a contagem total.
- A integração está isolada no PR #14, baseado na branch do PR #13, e não está na `main`.

## Auditoria persistente de reconciliação (PR #14)

A tabela `swap_reconciliation_attempts` registra histórico append-only por operação e tentativa, separada das tabelas dos bundles positivos.

Cada linha contém:
- `attempt_id`: identificador da execução de reconciliação (uma tentativa agrupa os swaps da transação);
- carteira e assinatura da transação observada;
- `operation_id` determinístico, índice da instrução, índice interno quando disponível e caminho CPI;
- status `MATCHED`, `INCOMPLETE`, `AMBIGUOUS` ou `UNRESOLVED`;
- motivo técnico retornado pelo reconciliador ou motivo explícito para ausência de resultado;
- horário de gravação.

A gravação de todos os resultados de uma tentativa é atômica. Cada replay gera novo `attempt_id`, preservando o histórico anterior. Se o decoder identificar um swap sem resultado correspondente do reconciliador, o adaptador grava `UNRESOLVED` para essa identidade e mantém o checkpoint bloqueado.

A tabela possui FK para a observação pai e índice por carteira/assinatura. Não possui FK para `swap_observations`, pois uma tentativa negativa deve existir mesmo quando nenhum bundle positivo foi produzido. O armazenamento expõe `save_swap_reconciliation_attempt()` e `get_swap_reconciliation_attempts()`; `storage_stats()` inclui a contagem da tabela.

A auditoria não transforma resultados negativos em bundles, não reclassifica swaps e não altera as regras de checkpoint. Ela apenas preserva evidência explicável de cada tentativa.
