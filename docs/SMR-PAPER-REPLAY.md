# Simulação offline

`smr paper-replay scenario.json` compara os modos `immediate` e `confirmed`
sobre as mesmas observações. Use `--mode` para executar só um deles.

```json
{
  "config": {
    "initial_cash": "1000",
    "max_entry_cash": "150",
    "max_exposure": "0.20",
    "fee_bps": "30",
    "slippage_bps": "20",
    "max_entry_deviation_bps": "300",
    "stop_loss": "0.10",
    "take_profit": "0.20"
  },
  "ticks": [
    {"at": "2026-01-01T00:00:00Z", "price": "10", "volume": "100", "signal": "BUY", "entry_allowed": true},
    {"at": "2026-01-01T00:01:00Z", "price": "10.1", "volume": "120", "entry_allowed": true},
    {"at": "2026-01-01T00:02:00Z", "price": "10.2", "volume": "130", "entry_allowed": true},
    {"at": "2026-01-01T00:03:00Z", "price": "10.4", "volume": "110", "signal": "SELL"},
    {"at": "2026-01-01T00:04:00Z", "price": "10.3", "volume": "100"}
  ]
}
```

Forneça observações em ordem estritamente crescente com fuso horário, uma
por instante e todas do mesmo mercado. O preço está na moeda do caixa por
unidade do ativo e o volume deve usar a mesma unidade em cada observação.
O cenário fornece o sinal e o resultado dos filtros de entrada.

- No modo imediato, um sinal elegível gera uma decisão na observação atual.
- No modo confirmado, a observação seguinte precisa ter preço e volume
  maiores que os do sinal. Uma observação sem confirmação encerra a tentativa.
- A entrada simulada usa a primeira observação posterior à decisão e exige
  filtro aprovado, volume positivo e ausência de sinal de venda. Se
  `max_entry_deviation_bps` for configurado, os dois modos também rejeitam
  um preço de execução acima do teto relativo ao preço da decisão.
- O gasto de entrada inclui a taxa e respeita o menor valor entre o teto
  fixo e a fração configurada do caixa disponível. O replay comporta uma
  posição comprada por execução. Uma observação com `halted: true` cancela
  uma entrada pendente e agenda a liquidação se houver posição aberta.
- Sinal de venda, stop ou take profit gera uma ordem de saída para a
  próxima observação com volume positivo. O stop e o take profit usam o
  valor líquido estimado de liquidação.
- O relatório inclui horários de decisão e execução, fills, taxas, exposição
  em unidades do ativo, patrimônio líquido, drawdown e ordens pendentes.
  O histórico de decisões registra ordens agendadas, confirmação e
  rejeições. O resultado inclui P&L realizado, taxas totais e tempo médio
  simulado entre a decisão e o fill.
  A última observação marca uma posição aberta a mercado.

Estimativas usam taxa e slippage fixos. O volume funciona como confirmação
e disponibilidade e ainda falta modelar a profundidade do mercado,
preenchimentos parciais, qualidade de preço e latência real. Este comando
consome JSON local e opera exclusivamente sobre caixa simulado.

## Replay de swaps arquivados

`smr paper-replay scenario.json --archive monitor.sqlite` usa o arquivo
prospectivo gravado pelo pipeline CPMM em vez da lista manual de ticks.
O cenário fornece a mesma configuração de simulação e uma seção `market`
com `wallet`, `program`, `base_mint`, `quote_mint` e `min_confidence`.
O banco é aberto em modo somente leitura para o replay. Use `--as-of` com
um instante ISO 8601 e fuso para reproduzir apenas o que estava disponível
até aquele momento. O relatório registra o SHA-256 dos recibos selecionados.

O pipeline arquiva os valores do primeiro processamento concluído de cada
operação, com o horário original de mercado e o horário local de publicação
no SQLite. Operações pendentes ou sem horário de mercado são omitidas.
Reprocessar uma operação pode atualizar a classificação atual, mas preserva
a classificação inicialmente arquivada. Dados anteriores à migração não
recebem um horário retroativo de disponibilidade.

O preço histórico é o quociente entre as quantidades de cotação e base do
swap da carteira e do programa escolhidos. O volume é o valor em cotação.
Só gera sinal uma classificação coerente com o fluxo base/cotação e acima
ou igual ao limiar informado. Preço e volume de um swap arquivado são
aproximações para simulação neste escopo. O relatório lista operações
omitidas por horário inválido, repetido ou regressivo. O instante do sinal
é o da sua disponibilidade. Confirmações e fills exigem uma observação cujo
evento de mercado ocorreu estritamente depois da decisão correspondente.
Esses dados ainda não representam cotações executáveis, liquidez geral do
mercado ou todos os filtros de risco da operação.

## Sinais arquivados com cotações independentes

Use `--archive monitor.sqlite --quotes quotes.json` e acrescente à seção
`market` do cenário `"signal_ttl_seconds": 30` (entre 1 e 86400).
O arquivo de cotações contém uma `source` explícita, os mesmos identificadores
`program`, `base_mint` e `quote_mint` do cenário e uma lista `quotes`.
Cada linha tem `quote_id` único, `market_at` e `available_at` em ISO 8601 com
fuso, `bid`, `ask`, `bid_size`, `ask_size` e `volume`. As duas séries de
horários crescem estritamente. Os tamanhos estão em unidades do ativo base,
o preço em moeda de cotação por unidade e o volume em moeda de cotação.

O sinal do swap só é apresentado ao simulador na primeira cotação cujo
evento de mercado aconteceu depois da chegada do sinal. Sinais vencidos
são descartados. Sinais de compra e venda concorrentes bloqueiam entrada.
O modo confirmado compara o preço médio bid/ask e o volume. O fill seguinte
usa o ask para compra e o bid para venda, com slippage e taxa configurados.
Uma entrada acima da profundidade informada é rejeitada, e uma saída
aguarda profundidade suficiente. Cada fill indica a cotação usada.

O relatório inclui fonte e SHA-256 da seleção de cotações. O cutoff
`--as-of` limita swaps e cotações pelo momento de disponibilidade.
Cotações e profundidade são fornecidas pelo arquivo e a execução continua
simulada. O modelo opera com fills integrais.
