# CM31 — persistent Launch integration


## CM31 — homologação offline concluída (2026-11-21)

- PR #111 Draft. Integração cirúrgica dos componentes Launch das PRs #68–#76: código inicial 50a615c274bc4676c4794d252cfefb3150811280, CI 44846283776 (1.107 testes). Restaurados writer RAW, cursor de entregas, checkpoint RPC atômico, backfill finalized, monitor WebSocket, métodos finalized do adapter Helius e CLI launch-scan/backfill/live. Não houve coleta real.
- Código complementar **824c93158e8fedf8111a97929e1e330744186900**: [CI SUCCESS](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44846804522), **1.113 testes, 12,251 s, zero falhas, compileall aprovado**. Seis regressões novas comprovam writer real→SQLite→reinício→projeção→DashboardReadService (fixture offline), concorrência entre writers em threads com conexões distintas, SHA e checkpoint falsos rejeitados, interrupção após último RPC e retomada, rollback em cursor RPC sem alteração do checkpoint de carteira, conflito de identidade mesmo fora do limite de página. Não afirmar crash físico/energia, concorrência multiprocesso ou browser real homologados. Proteções de paginação, slot e estado err. RAW de backfill é serialização do resultado RPC; não afirmar bytes exatos de transporte nem autenticação do provider.
- [CI risco e replay protegido](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44846812578): 6+14+5 testes direcionados aprovados, sobrepostos à suíte completa; não somar ao total. **CM31 concluído no escopo offline validado.** Origem/coverage UNKNOWN quando não atestadas; operação financeira e paper operacional bloqueados. PR #112 preservada; PR #113 revisão humana pendente. Main 5060bc65ddf181a4736fdb662c44c3fec0dd7259 intacta. Um executor, zero auxiliares.
- Próximo CM32: integrar sinais e risco às evidências arquivadas, separar Launch de consenso Smart, acoplar auditoria de mercado e risco sem promoção de UNKNOWN, preparar interface conservadora para CM33. Sem reduzir escopo definitivo.

## Remaining operational gates
Independent provider attestation, complete historical coverage, live notification/reconnect, full hardware/power-loss resilience, scoped trading economics, paper operational eligibility and real trading are not demonstrated. PR113 must receive human review; no dispatch or merge was performed. No services purchased or secrets supplied.
