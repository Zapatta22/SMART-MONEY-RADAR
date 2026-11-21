# SMART MONEY RADAR — COMANDO MESTRE 29 (2026-11-20 UTC)

## Estado e bloqueio da homologação live

- PR #111 Draft: `88784877fcdac78eba8f8b291d615e1be04a3fba`, base `codex/smr-cpmm-ws-resilience`; `main` mantida em `5060bc65ddf181a4736fdb662c44c3fec0dd7259`. PR #112 divergente: comparação indicou +13 commits na #112 e 49 commits atrás da #111, não incorporar sem revisão.
- **Workflow live NÃO executado:** `.github/workflows/smr-cm27-live-gate.yml` está apenas na branch `codex/smr-cpmm-ws-integrated-recovery`; em `main` existem somente `smr-tests.yml` e `import-smr-archives.yml`. O arquivo contém `on.workflow_dispatch` e exige `approve_read_only=READ_ONLY_BOUNDED_CM27`. O GitHub conectado permite leitura/escrita de repositório, mas a ferramenta não possui `workflow_dispatch` (POST), nem shell autenticado `gh workflow run`; `fetch` é apenas GET. Portanto nenhum disparo foi simulado ou contornado por push. Para habilitar a UI de dispatch, requer revisão/autorização humana para registrar um workflow equivalente na branch padrão; não alterar `main` por automação desta etapa. Um operador com permissão poderá usar **Actions > workflow > Run workflow > branch PR #111 > input** depois de registrado oficialmente na default branch.
- Sem 75s de captura, nenhuma evidência nova RPC/WS/ACK/notificação/reconexão. Último slot real conhecido `471887787`, 4 ACKs anteriores, zero notificações anteriores. Cobertura `UNKNOWN`, execução financeira bloqueada.
- Nota: ter permissões GitHub admin na metadata do repositório NÃO significa que a conexão tenha acesso de comando para disparar workflows. Não usar outra automação não prevista.

## Entrega funcional da PR #111

Implementado no mesmo branch:
- `src/smart_money_radar/services/radar_integration_status.py`: contrato observacional independente para `launch` e `smart_money` com origem, pool, assinatura, slot, data, RAW/SHA-256, cobertura, resultado, justificativas e avaliação de risco reutilizando `OpportunityClassification` e `evaluate_entry_risk`. Evidência local não autentica RPC; nenhum sinal e nenhuma condição remove bloqueio operacional ou paper. Não é engine de ordens.
- `tests/test_radar_integration_status.py`: dez testes de separação de radares, hash adulterado, ausência de evidência, conflito origem/pool/cutoff, emergência, fontes não autenticadas e bloqueio financeiro.
- `src/smart_money_radar/services/dashboard_read.py`: dois canais observacionais `launch` e `smart_money` integrados à API de visão geral já existente, default `UNKNOWN`, `operational_authorized=false`, modos paper `BLOCKED`. Nenhuma rota de escrita adicionada.
- `tests/test_dashboard_read_service.py`: um teste adicional que confirma separação dos canais e bloqueios.

**Última CI confirmada:** 1.063 testes aprovados, 0 falhas, compileall aprovado, commit `88784877fcdac78eba8f8b291d615e1be04a3fba`, https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44841067362. Antes 1.052, não somar suítes.

## Inventário enxuto — 87 PRs abertas

Metadados GitHub 20/11/2026; estado CI por PR **não verificado individualmente** (apenas #111 com CI confirmada). As bases/head a seguir são caminhos reais; nenhuma integração em `main`:

| Linha | PRs críticas e dependências | Função/presença de código | Risco e próximo gate |
| --- | --- | --- | --- |
| RAW, decoders, integridade | #4–#8; #24–#26; #29, #31–#33, #43–#58 | persistência SQLite, DAMM v2, Geyser/Yellowstone | revisitar prova banco/sequence/taint, sem fundir branches divergentes |
| Replay e risco | #59→#64, #90→#96 | paper, cutoff, cotações, hashes, risk gates | preço executável não autenticado; seguir BLOCKED |
| Launch Radar | #68→#73→#76; laterais #74/#75 | detecção CPMM, journal, backfill, WS | testes de estado isolado e integração do Launch real ainda pendentes |
| Smart Money | #66→#80→#84→#87 | evidência de carteiras, consenso, classificação | identidade independente de carteiras não demonstrada |
| Prova pública CPMM e baseline | #99→#111 | provas RAW e WS; slot e recibos, baseline | prova live e cobertura UNKNOWN, PR #112 divergente |
| Controle celular | #65, `dashboard_read.py`, `dashboard_http.py` na #111 | API loopback token + status read_only | estado UNKNOWN deve ser mostrado, nunca disparar ordens |

Outras PRs permanecem preservadas no repositório; o inventário é de **metadados**, não auditoria completa das 87.

## Contratos e caminho crítico

1. Dados: `RadarObservation` com `radar,source_id,pool,signature,slot,available_at,raw_sha256,coverage`. Hash SHA-256 local não comprova origem do RPC.
2. Inteligência: `WalletConsensusReport`, `OpportunityClassification` e módulos Launch independentes, sem duplicar sinais.
3. Decisão: `EntryRiskLimits/Snapshot`, `evaluate_entry_risk`, emergência e bloqueio para cobertura incompleta.
4. Simulação: `strict_economic_replay` permanece BLOCKED sem cadeia autenticada, quote executável e corte temporal correto; modos `immediate/confirmed`.
5. Controle: painel de leitura HTTP local existente agora expõe ambos os canais inicialmente UNKNOWN; futuras informações verificadas só por adapters explícitos auditados.

**Estimativas de engenharia, não medidas objetivas:** recuperação WebSocket CM27 offline 100% dos testes acordados; homologação live 0% nesta sessão; contrato de integração inicial CM29 100% do escopo local testado, mas integração funcional total entre os dois motores permanece parcial/indeterminada; operação autônoma 24h e trading real **não homologados**; sem porcentagem global defensável.

## Continuidade

Próximos gates: inspecionar evento real Launch e recibo real Smart Money, adaptar ambos ao contrato com proveniência explícita, validar lado a lado no painel e testes de integração que exigem same-source/time/cutoff; depois workflow live via autorização da default branch e artifact durável. Uma executor, zero auxiliares: economia de créditos não mensurada. Sem VPS, credenciais, operações reais, merge, alteração de `main` ou omissão de funcionalidade planejada.
