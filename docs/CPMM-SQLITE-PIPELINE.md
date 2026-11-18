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


## Serviço de aplicação para diagnósticos (PR #15)

- `src/smart_money_radar/services/reconciliation_diagnostics.py` adiciona `ReconciliationDiagnosticsService`, uma fachada somente leitura sobre as consultas do EventStore.
- `get_report()` expõe métricas, motivos recorrentes e pendências; `list_attempts()` expõe o histórico com filtros de carteira, assinatura, operação, status e período.
- A camada de serviço não implementa SQL nem oferece métodos de escrita/checkpoint; validações e limites permanecem centralizados no EventStore.
- `tests/test_reconciliation_diagnostics_service.py` verifica delegação dos filtros, preservação do resultado e ausência de operações de mutação na interface pública do serviço.
- Esta camada prepara a futura API/interface, mas não cria endpoints HTTP, dashboard ou painel visual.


## Serviço de leitura para o futuro dashboard (PR #15)

- `src/smart_money_radar/services/dashboard_read.py` adiciona `DashboardReadService`, que compõe estatísticas do EventStore, diagnóstico de reconciliação e até 20 eventos recentes persistidos.
- O retorno declara `mode=read_only` e normaliza `datetime`, `Decimal` e tuplas para valores serializáveis em JSON.
- Aceita filtro opcional por carteira; não faz chamadas RPC/HTTP, não grava dados, não altera checkpoints e não executa transações.
- `tests/test_dashboard_read_service.py` cobre composição, serialização, injeção do serviço de diagnóstico e superfície sem mutações.
- Esta entrega é um serviço de consulta interno, não um servidor HTTP, endpoint REST, autenticação, nem interface gráfica. A escolha de framework HTTP fica para etapa própria após estabilizar o contrato de resposta.


### Correção após CI do dashboard
- O primeiro CI do `DashboardReadService` encontrou uma expectativa de mock incompleta no teste: o serviço delega corretamente todos os argumentos nomeados, inclusive `since=None`, `until=None` e `top_reasons_limit=10`.
- O teste foi ajustado para validar o contrato completo; nenhuma regra de produção foi alterada. Novo CI necessário.


## Adaptador HTTP local de leitura (PR #15)

- `src/smart_money_radar/services/dashboard_http.py` adiciona `create_read_only_server()` com endpoints GET `/health`, `/api/v1/dashboard` e `/api/v1/reconciliation/attempts`.
- Exige Bearer token com pelo menos 32 caracteres, comparação em tempo constante, bind exclusivamente em IP loopback, respostas `Cache-Control: no-store` e `X-Content-Type-Options: nosniff`.
- Métodos POST, PUT e DELETE são recusados com HTTP 405. Não há CORS, acesso externo, gravação, RPC ou execução de ordens.
- O servidor é criado sem iniciar automaticamente; o chamador controla explicitamente o ciclo de vida.
- `tests/test_dashboard_http.py` cobre autenticação, dashboard, rota desconhecida, método de mutação, host não-loopback e token curto.
- A implementação ainda depende de CI e revisão de segurança; não deve ser exposta em rede nem usada como serviço de produção nesta fase.


### Inicialização controlada da API local

O comando `smr-api` é registrado como entry point do pacote. Ele usa `SMR_API_TOKEN` (obrigatório, mínimo 32 caracteres) e `SMR_DB_PATH` (opcional; padrão `data/smr_history.sqlite3`). A inicialização não chama `HeliusSettings`, não exige `SMR_ALLOW_NETWORK` e não faz RPC. Opções `--host` e `--port` existem, mas `create_read_only_server()` recusa qualquer host que não seja loopback. Encerrar com Ctrl+C fecha o servidor e o EventStore.

Exemplo local (não compartilhar o token):

```bash
export SMR_API_TOKEN="$(openssl rand -hex 32)"
smr-api
```

A API continua restrita ao próprio dispositivo. Este comando não configura acesso remoto pelo Android nem substitui autenticação TLS para exposição em rede.


### Correção do empacotamento do comando smr-api

A primeira execução do CI após registrar o entry point falhou durante `pip install -e .`, antes dos testes, por `TOMLDecodeError` na linha `[project.scripts]`: a edição havia gravado os caracteres literais `\\n` entre as duas entradas, em vez de uma quebra de linha. O arquivo foi corrigido para duas linhas TOML válidas no commit `ec8445224ca88070f83cac9fb12862348fc876f1`. O conteúdo foi relido e confirma `smr` e `smr-api` em linhas separadas. Nova execução do CI é necessária; ainda não se declara validação dos testes do launcher.


### Limite de consulta HTTP

O endpoint `GET /api/v1/reconciliation/attempts` aceita `limit` entre 1 e 500 (padrão 100). Valores fora da faixa são rejeitados com HTTP 400 antes de consultar o EventStore. O limite superior reduz consultas excessivas e evita que o adaptador HTTP exponha o limite interno não limitado do EventStore.


### Validação do launcher e limite HTTP

CI run `44239943317` passou no head documental `8e509d8f6963e965b9d1f005f84c4d06c9f3d70a`, com instalação do pacote, 241 testes unitários aprovados e `python -m compileall -q src tests` aprovado. A execução inclui a correção de TOML do comando `smr-api`, seus testes de ciclo de vida e a validação do limite HTTP 1..500.
