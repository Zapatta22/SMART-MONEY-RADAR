# SMR — Auditoria dos contratos de domínio — Etapa 7

Data: 16/11/2026

## Escopo

Criar estruturas tipadas e validações centrais para normalizar dados observados
na Solana e preparar integração incremental entre ingestão, parser, radares e
inteligência de carteiras. Esta etapa não implementa os radares nem decisões de
trading.

## Contratos adicionados

- `ObservedTransaction`: envelope da transação, cadeia, carteira, assinatura,
  instante de observação, payload bruto, versão e estado de parsing, slot e
  horário on-chain opcionais.
- `TokenBalanceDelta`: variação por mint, direção, quantidade Decimal e escala
  SPL opcional validada.
- `SwapObservation`: hipótese de swap com ativos/quantidades, confiança entre
  0 e 1, evidências explícitas e versão do parser. Não equivale a swap
  definitivamente decodificado.
- `PoolSnapshot`: reservas observadas de dois ativos, instante, slot e fonte.
  Não calcula preço USD nem liquidez total.
- `WalletProfile`: resumo versionado de observações e métricas, com validação
  temporal, contagens e win rate.

## Compatibilidade e limites

Os tipos existentes `Wallet` e `ActivityEvent` foram preservados. O monitor,
parser e EventStore continuam usando os tipos antigos nos fluxos atuais; os
novos contratos ainda não estão integrados ponta a ponta. Essa separação evita
uma migração ampla e arriscada sem adaptadores e testes de regressão.

Não há ainda cálculo confiável de PnL, win rate ou preço para `WalletProfile`;
esses campos são recipientes tipados e exigem uma metodologia futura para
custos, taxas, transferências, posições abertas, preços históricos e atribuição
de carteira. `SwapObservation.confidence` exige evidências, mas não é um
modelo probabilístico calibrado. `PoolSnapshot` é um registro de reservas, não
um indexador de pools.

## Validação

- `PYTHONPATH=src python -m unittest discover -s tests -v`: 53 testes aprovados.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- 6 testes novos para contratos e validações.
- Todos os testes locais; sem RPC real, benchmark, carga ou implantação.

## Próxima etapa recomendada

Implementar adaptadores de normalização entre `parse_transaction` e os novos
contratos, sem quebrar `ActivityEvent` ou o esquema histórico. Depois adicionar
fixtures reais anonimizadas para pelo menos um swap conhecido em cada programa
prioritário e validar mints, quantidades, taxas e contas envolvidas. Somente
após isso criar `SwapDecoder` com classificação explícita e evidências.
