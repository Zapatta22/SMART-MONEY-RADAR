# Replay protegido

Execute `smr paper-replay scenario.json --strict-evidence evidence.json`.
Para limitar a leitura à informação disponível até um instante, acrescente
`--as-of INSTANTE_ISO8601_COM_FUSO`. Os dois modos usam a mesma janela.
O cenário usa o formato do replay normal e exige um `quote_id` por tick.

O arquivo de evidência contém `pool`, `risk_limits`, `risk_by_quote` e
`evidence_by_quote`. Os limites de risco são `max_position_fraction`,
`max_daily_loss_fraction`, `max_slippage_bps` e `min_liquidity_quote`.
Cada tick elegível para entrada tem um `EntryRiskSnapshot` associado. O
snapshot precisa declarar `available_at` com fuso e só pode ser usado em
ticks no mesmo instante ou posteriores à sua disponibilidade.

Cada `evidence_by_quote[quote_id]` é uma lista com um único registro:
`evidence_id`, `pool`, `observed_at`, `available_at`,
`source="OBSERVED_MARKET_QUOTE"`, `is_observed_quote=true`,
`raw_capture_base64` e `raw_capture_sha256`. Os bytes RAW contêm JSON
com `quote_id`, `pool`, ambos os horários e valores de `price`, `volume`,
`bid`, `ask`, `bid_size` e `ask_size`. Os campos opcionais ausentes
da cotação podem ser explicitados como `null` no RAW. Entradas protegidas
exigem ask e profundidade no preenchimento.

O replay confere o digest e compara os campos RAW com o tick antes de
rodar os dois modos. Uma lacuna ou divergência dentro da janela encerra
o replay. Os valores de risco são reavaliados no preenchimento com o
orçamento comprometido, a profundidade do ask, patrimônio simulado,
perda diária e desvio adverso desde a decisão. Resultados são simulados.

O SHA-256 prova consistência entre os dados apresentados. A identidade
do provedor, os horários de captura e os saldos externos ainda dependem
de cadeia de custódia verificável. O indicador `evidence_verified` do
snapshot de risco é uma declaração do operador. A opção
`--strict-evidence` com `--archive` continua indisponível até integrar
as duas trilhas com proveniência validada.

Para verificar a cotação contra um registro independente, forneça
`--strict-quote-manifest quotes-manifest.json --strict-quote-manifest-sha256 HASH`.
Obtenha o hash por uma via confiável e separada do arquivo de replay. O
manifesto tem schema `smr-paper-quote-manifest-v1`, `pool` e `quotes`
mapeando cada identificador ao SHA-256 dos bytes RAW. Um tick ausente ou
com hash divergente não entra no replay. O manifesto atesta apenas o que
sua fonte validou. O caminho sem manifesto mantém as checagens locais.

Configure `max_quote_staleness_seconds` para bloquear cotações cuja
disponibilidade exceda a idade máxima medida desde `market_at`. Nesse
modo, uma cotação sem horário de mercado também é ignorada para fins de
preço. Uma venda pendente aguarda uma observação fresca e o relatório
contabiliza os ticks rejeitados por idade.
