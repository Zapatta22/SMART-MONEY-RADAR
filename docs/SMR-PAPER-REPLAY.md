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
