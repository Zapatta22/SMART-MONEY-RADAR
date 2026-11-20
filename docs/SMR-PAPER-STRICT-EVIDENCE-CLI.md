# Replay protegido: integração inicial

Comando: `smr paper-replay scenario.json --strict-evidence evidence.json`.

`scenario.json` mantém a configuração normal de paper replay. Cada tick precisa conter `quote_id` estável. O arquivo `evidence.json` contém:

```json
{
  "pool": "POOL_ID",
  "risk_limits": {
    "max_position_fraction": "0.20",
    "max_daily_loss_fraction": "0.05",
    "max_slippage_bps": "100",
    "min_liquidity_quote": "1000"
  },
  "risk_by_quote": {},
  "evidence_by_quote": {}
}
```

Cada `risk_by_quote[quote_id]` precisa fornecer os campos de `EntryRiskSnapshot`; cada `evidence_by_quote[quote_id]` é uma lista de evidências com ID, pool, horários de observação e disponibilidade, `source="OBSERVED_MARKET_QUOTE"` e `is_observed_quote=true`.

**Atenção:** os dois mapas vazios no exemplo bloqueiam entradas. O comando apenas valida declarações fornecidas pelo operador; ainda não autentica criptograficamente as cotações nem seus saldos. Não é autorização de execução real.

`--strict-evidence` com `--archive` é rejeitado até existir uma integração de evidências históricas auditadas. Os testes de ponta a ponta e CI desta interface permanecem pendentes.