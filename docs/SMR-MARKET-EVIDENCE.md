# SMR — Segurança, liquidez e volume: evidência de mercado

Estado 2026-11-20: validação **offline** em branch integrada, sem rede Helius real,
sem chaves, sem ordens ou endosso de rentabilidade.

## Contratos e componentes

- `market_safety_liquidity.py`: `MarketEvidenceEnvelope` inclui identidade
  de evidência, token, pool, slot, fonte, horário de observação e disponibilidade,
  commitment e SHA-256 do RAW. `TokenSafetySnapshot` registra alegações sobre
  autoridade de mint/freeze, programa SPL, concentração e risco de retirada de
  liquidez. `LiquiditySnapshot` vincula reservas a
  `cpmm_reserve_snapshot.validate_snapshot` existente.
- `market_volume_audit.py`: `SwapVolumeEvidence` descreve assinatura,
  origem, slot, instante, lado do swap, quote amount e SHA RAW. A auditoria
  bloqueia evidência futura, assinatura contraditória, hash inválido e
  sinaliza concentração de volume por carteira, sem dupla contagem.
- `market_opportunity_bridge.py`: substitui flags autodeclaradas do
  classificador por conclusões da auditoria; conserva riscos e flags de
  manipulação existentes. Nunca habilita execução financeira.

A classificação usa `as_of` point-in-time. O horário em que uma transação
aconteceu não é necessariamente o horário em que seus dados estavam disponíveis.

## Limitações explícitas

A checagem de hash prova somente que os bytes arquivados correspondem ao
hash fornecido. **Não autentica a origem da resposta RPC**, nem valida por
si só a distribuição de holders, o status SPL Token-2022, os direitos
administrativos de todos os programas, custódia dos LP tokens, bloqueios de
retirada de liquidez ou wash trading multicarteira.

Evidências auditadas pela camada local não equivalem a segurança operacional
comprovada. O `WalletConsensusService` existente ainda não comprova
independência entre controladores de carteiras. A classificação deve continuar
`UNKNOWN` ou `REJECTED` quando existirem lacunas críticas.

O adaptador conserva a separação `SIMULATION_CANDIDATE` x
`operational_authorized=False`. Não executar compras e vendas reais.

## Resultado de validação

PRs Draft #85, #86 e integração #87, base #84. Commit de código validado
`2295f583d15001a21e7275c39e006aaa32f240cc`, CI GitHub Actions:
**777 testes aprovados, zero falhas e compileall**,
https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44775208257.

## Próximo desbloqueio

1. Ligar envelopes a evidências realmente capturadas do arquivo SQLite
   de swaps e snapshots de pool, preservando first-publication timestamps.
2. Adicionar testes de reprocessamento histórico sem look-ahead e comparar
   os modos imediato e confirmado, sem executor financeiro.
3. Implementar auditoria externa de origem, permissões SPL, concentração
   de holders e risco de retirada de liquidez antes de promover estados VERIFIED.
4. Validar Solana Live real com Helius quando houver ambiente autorizado.

A quantidade de testes não fornece percentual global de conclusão.
