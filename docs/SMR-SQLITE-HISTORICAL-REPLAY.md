# SMR — Replay SQLite point-in-time, ciclo 11

**Estado:** offline, sem execução financeira. PRs #88 (projeção do SQLite),
#89 (comparação dos modos) e #90 (integração) em Draft. Testes de integração:
**791 aprovados, zero falhas, compileall**, código
`f6dfa66b10f7feef803d600e57f4b2c2309494e7`,
https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44776739674.

## Contrato de reprodução

`archived_volume_at` usa `SQLiteEventStore.list_wallet_signal_receipts`
existente, filtrado por carteira/programa/pool/par de mints. Respeita
`available_at <= as_of`, uma janela única, valida o SQLite com
`PRAGMA integrity_check` e registra exclusões de evidência futura,
incompleta, duplicada ou de escopo inadequado. Não reescreve o EventStore.
Um replay com banco reaberto como `read_only=True` é determinístico em
fixtures; o conteúdo de um banco em mutação exige snapshot consistente
externo/backup para comparação de execuções em datas diferentes.

Os recibos existentes **não carregam** o slot certificado, o compromisso
finalized, o RAW HTTP do RPC ou cotação observada executável por si só.
Por isso a projeção **não fabrica** campos `SwapVolumeEvidence`. Seu volume
permanece `UNKNOWN`, sem qualificar o token apenas porque há recibos.
`HistoricalOpportunityFrame` chama `classify_with_market_evidence` no
mesmo cutoff, conservando falta de segurança e liquidez.

O adaptador `compare_gated_replay_modes` usa o motor
`domain.paper_replay.replay_paper` preexistente em ambos os modos, mesma
configuração `PaperConfig` de exposição, fees e slippage e observações
filtradas. Rejeita cutoff anterior à disponibilidade da cotação, timestamps
não ordenados, observações sem marcação de preço e gates negados.
Esta API é exploratória: o parâmetro `observed_quotes` é fornecido pelo
chamador e **não constitui atestado** de quote real. A integração SQLite
nunca preenche esse campo de forma positiva com base apenas em recibos.

## O que NÃO está aprovado

- Não existe validação Solana real Helius nesta sessão;
- Não existe PnL, win rate, drawdown ou preço de fill confiável derivado
  exclusivamente de recibos SQLite;
- Não há demonstração da política estrita com RAW autenticado + cotações
  assinadas/atreladas ao slot + snapshots de risco simultâneos em uma mesma
  sessão histórica;
- Independência econômica de carteiras e proveniência de fornecedor continuam
  não atestadas. Nenhum resultado habilita execução financeira.

## Próximo caminho crítico

1. Enriquecer os recibos históricos com evidência RAW ligada à assinatura,
   slot, pool e first-publication, sem substituir o histórico original.
2. Validar cotação **observada** no mesmo instante e política estrita de
   risco por quote_id; ao faltar evidência, bloquear o replay completo.
3. Comparar as duas modalidades com amostra suficiente, a mesma janela e
   política de custos, relatar métricas econômicas apenas quando ancoradas em
   cotações verdadeiramente observadas.
4. Validar Helius ao vivo quando rede, credenciais e quotas forem autorizadas.

Não fazer merge na `main` sem autorização. Nenhum percentual global é
mensurável sem pesos de módulos e critérios de aceite aprovados.
