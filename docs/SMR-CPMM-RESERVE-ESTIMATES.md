# Estimativas offline por reservas CPMM (não são cotações observadas)

O módulo `smart_money_radar.domain.cpmm_reserve_estimator` calcula uma aproximação genérica de produto constante (`x*y=k`) a partir de reservas efetivas informadas em unidades humanas, valor de entrada e taxa em basis points.

## Limites e procedência

- O cálculo **não acessa RPC**, não registra capturas e **não produz cotação executável**.
- `source=MODEL_ESTIMATE_NOT_OBSERVED` e `is_observed_quote=False` são invariantes do resultado.
- Antes de usar dados reais, registrar: endereço do pool e programa, slot e compromisso da leitura, mint e decimais de cada token, contas vault, reservas efetivas, configuração de taxas, hashes SHA-256 dos payloads brutos e horários de observação/disponibilidade.
- A captura de contas deve ser coerente no mesmo slot; validar propriedade e layout das contas e verificar a subtração de eventuais saldos indisponíveis/fees pendentes antes de tratá-los como reservas negociáveis.
- Verificar as regras específicas de arredondamento, transferência Token-2022, taxas dinâmicas e limites do programa Raydium CPMM antes de comparar com swaps finalizados.
- Uma simulação de compra e de venda requer orientar corretamente `reserve_in` e `reserve_out` para cada direção.
- Não alimentar `--quotes` com essas estimativas fingindo que são bid/ask observados. Manter um arquivo separado com procedência e classificação.
- A validação empírica exige uma série contemporânea de swaps finalizados e estados anteriores à execução, no mesmo pool, com horários, slot, valores líquidos e direção do swap; reportar erro absoluto e relativo sem seleção retrospectiva de amostras.

## Fórmula de referência

`net_in = amount_in * (1 - fee_bps / 10000)`

`estimated_out = reserve_out * net_in / (reserve_in + net_in)`

Esta fórmula não reproduz necessariamente a execução on-chain. Nenhuma conclusão de desempenho financeiro deve ser derivada sem a reconciliação empírica.
