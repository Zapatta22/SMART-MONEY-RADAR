# SMR — RAW local e pré-check de cotações observadas (Comando 12)

**Marco:** 20/11/2026. PRs Draft #91, #92 e integração #93.
Código validado no commit `e4a2e1b20159473e74c8fe092323bc39d949bfb6`:
**809 testes aprovados, zero falhas**, compileall no GitHub Actions:
https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44779992846.

## O que existe e o que é comprovável

- `services/receipt_raw_link.py` utiliza o `SQLiteEventStore` existente:
  `get_swap_bundle`, `get_raw_transaction` e
  `get_observation_metadata`. Cruza operação, carteira, assinatura,
  programa, pool, slot, observação e primeira disponibilidade.
  Compara SHA-256 do JSON **canonizado localmente** e, quando fornecidos,
  slot esperado e hash local esperado.
- Os bytes retornados são do JSON reserializado no SQLite.
  **Não equivalem aos bytes originais da resposta RPC**.
  A assinatura embutida/slot são checagens de consistência, não uma prova
  criptográfica independente da fonte. `provider_authenticated=False` e
  `finalized_attested=False` continuam incondicionais; o resultado
  `ReceiptRawLink.status` permanece `UNKNOWN`.
- `services/observed_quote_gate.py` recebe `ObservedQuoteEvidence`,
  com pool, slot, fonte, horários `market_at/observed_at/available_at`,
  bid/ask, tamanho, volume, taxa, slippage máximo e hash da evidência.
  Rejeita futuro, pool diferente, hash inválido, valor incoerente e
  profundidade insuficiente; tarifas/slippage sem prova resultam UNKNOWN.
- Mesmo se o operador declarar `provider_attested=True` e
  `depth_attested=True`, a saída permanece **paper only** e informa
  `economics_supported=False`. Uma declaração booleana não atesta
  fornecedor ou viabilidade de ordem. Nenhum resultado pode ser divulgado
  como retorno real/confiável a partir dessas flags.

## Dependência e próximo passo

O replay anterior `replay_with_required_risk` já impõe evidência
de cotação observada e gates de risco; não substituir nem duplicar.
A próxima entrega deverá vincular a observação RAW original assinada,
slot e pool a uma fonte autenticada de cotações, com hash/proveniência
conferíveis e custo/latência de disponibilidade temporal. Até lá,
a comparação entre entradas imediatas e confirmadas permanece
exploratória, sem PnL/ROI real nem entrada financeira.

Solana Live/Helius real pendente por falta de ambiente autorizado.
Não fazer merge na `main`, não contratar serviço e não operar fundos.
