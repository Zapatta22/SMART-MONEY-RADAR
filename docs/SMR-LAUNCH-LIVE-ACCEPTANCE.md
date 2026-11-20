# SMR — Matriz objetiva de aceitação (2026-11-20)

A aprovação de testes não é aprovação para negociação com dinheiro real.
Estados: **implementado**, **CI validado**, **integrado em branch**, **bloqueado**.
Branches de PRs em Draft não estão incorporadas à main.

| Módulo | Critério de aceitação | Implementação | Testes | Integração | Pendências/dependências |
| --- | --- | --- | --- | --- | --- |
| RAW/reconciliação Solana | RAW íntegro, identidade, checkpoints e recuperação | Sim, em PRs anteriores | CI anterior | Cadeia de PRs pendente de merge | Revisão da cadeia e proveniência do provedor |
| Launch detection CPMM | Detectar initialize com contas, roles e pool corretos | Sim, offline (#68) | Fixture mainnet e CI | #69/#70 dependem de #68 | Cobertura de outros DEX e fontes |
| Journal/cursor Launch | RAW e cursor atômicos, idempotência e rollback | Sim (#69/#70) | 756 testes em #70 | Base para #73 | Sem garantia de completude histórica |
| Solana RPC backfill | Histórico finalized dentro de limite, cursor só avança com RAW | Sim (#73) | 762 testes no SHA e62266c | #73, Draft | RPC real, rate limiting, paginação em reorganizações |
| Solana WebSocket | Subscrições, reconexão, re-assinatura e reconciliação finalized | Sim, monitor na branch de integração | 769 testes no SHA 7069706 | Branch Draft de integração; main não alterada | Testes reais de rede, consumo de API, cobertura, autenticação, latência, notificações fora de ordem |
| Smart Money | Padrões de carteiras, falsos positivos, ranking e concentração | Parcial (#66) | Testes direcionados anteriores | PR separada | Ranking, heurísticas, alertas |
| Simulação e risco | Evidência de quote externa, cutoff, slippage, ambos modos | Parcial (#64/#67) | CI específico anterior | Não conectado ao Live | Prova de proveniência e swaps contemporâneos do mesmo pool |
| Aplicativo/observabilidade | Estado dos módulos, histórico, métricas e alertas | Parcial (#65) | Testes anteriores | Pendente | Consolidação, operação acessível e alarmes |
| Operações reais | Validação independente, autorização e controles financeiros | Desabilitado | Não aplicável | Proibida | Autorização separada após aceite |

**Critério de progresso global:** não existe decomposição aprovada de entregáveis com pesos e critérios mensuráveis para todas as linhas. Assim, percentual global não deve ser calculado a partir da quantidade de testes.

## Resultados da rodada WebSocket

- PR #74: monitor WebSocket em `src/smart_money_radar/services/launch_live_monitor.py`, `logsSubscribe` confirmed como **sinal de atualização**; resultados finais são sempre buscados no RPC finalized. Reconexão com backoff/jitter e backfill em toda nova sessão. Reconciliação periódica diante de silêncio, heartbeat de transporte, métricas locais.
- PR #75: testes independentes em `tests/test_launch_live_monitor.py`, cobrindo ACK, reconexão, erro RPC, assinatura incorreta, falta de notificações, recuperação e parada.
- Branch integradora `codex/smr-launch-websocket-integration`: soma as duas frentes e habilita `smr launch-live`, com `SMR_ALLOW_NETWORK=true` e configuração Helius obrigatórias.
- No primeiro CI houve uma falha real de fixture de silêncio, corrigida sem alterar código de produção. CI **aprovado** no SHA `70697064780f7a738b5e02f439dcb64d9c988097`: **769 testes**, `compileall`, zero falhas: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44761362086.
- Não foram executadas sessões externas WebSocket/RPC, e os números de latência são ainda apenas instrumentação interna; **cobertura UNKNOWN**. O monitor não garante todos os lançamentos da rede: monitora apenas endereços explicitamente informados. Perda permanente de histórico fora da janela de backfill exige intervenção; sem avanço silencioso do cursor.
- **Próximo marco bloqueante**: teste de ponta a ponta autorizado com fonte RPC/WebSocket real, registro de horários de disponibilidade, taxa de reconexão, divergência do provedor, eventos skipped/reorg e política de limitação de recursos. Nunca usar a presença de um evento confirmed como prova de finalized.


## Revisão de aceite — PR #79 (2026-11-20)

| Módulo | Critério | Implementação | Testes | Integração | Bloqueador |
| --- | --- | --- | --- | --- | --- |
| Telemetria Solana Live | Medir hints confirmed vs assinatura em finalized, contadores de 429 e duplicatas, p50/p95/p99 somente com >=20 observações | Código preparado | 786 testes aprovados no SHA `4dc388f` | PR #79 Draft | Sem amostras reais, sem horário do validador e sem atestado independente |
| Limitação RPC | Evitar uma consulta por mensagem em rajadas sem encobrir lacunas | Configuração padrão de 1s por endereço | Teste de rajada aprovado | PR #79 Draft | Benchmarks e quotas do provedor real pendentes |
| Registro de validação | JSON local seguro/atômico, sem chave, com cursores e checagem SQLite | CLI com duração limitada | Testes de proteção de credenciais aprovados | PR #79 Draft | Falta executar com RPC/WebSocket real autorizado |

Validação CI geral: https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44764651003.
Validação operacional **PENDENTE**. Eventos reais coletados nesta sessão: 0;
latência p95 real: não medida; cobertura: UNKNOWN.
Procedimento: `docs/SMR-SOLANA-LIVE-REAL-VALIDATION.md`.
