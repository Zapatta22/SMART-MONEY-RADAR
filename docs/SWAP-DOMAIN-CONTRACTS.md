# Contratos separados de swap — SMR

## Objetivo

Separar o fato econômico observado, sua interpretação semântica e a proveniência técnica. Nenhuma transferência isolada deve ser promovida automaticamente a swap.

## Contratos

- `SwapObservation`: operação com carteira, transação, ativos, quantidades e `operation_id`. Não contém confiança, classificação ou evidências técnicas.
- `SwapClassification`: `BUY`, `SELL` ou `UNKNOWN`, com confiança decimal entre 0 e 1 e motivo obrigatório. `UNKNOWN` permanece válido quando a evidência não permite uma conclusão; não se presume direção.
- `SwapEvidence`: `program_id`, venue/DEX efetiva quando conhecida, índice da instrução, caminho CPI e evidências técnicas textuais.

Os três objetos compartilham `operation_id`, mas permanecem independentes. A relação entre eles deve ser validada pela camada de aplicação/persistência ao integrar o pipeline.

## Identidade estável

`build_swap_operation_id(chain, signature, instruction_index, cpi_path)` gera um identificador SHA-256 versionado a partir da cadeia, assinatura, índice da instrução externa e caminho CPI. Operações distintas na mesma transação recebem IDs distintos quando seus índices/caminhos diferem.

O helper não tenta descobrir índices ou caminhos: eles precisam vir da análise real das instruções e inner instructions. Não se deve fabricar esses dados.

## Limites desta entrega

Esta etapa define e testa os contratos de domínio. Não reconstrói swaps a partir do parser, não altera o SQLite, não identifica venue automaticamente e não autoriza execução de ordens. A integração deve ocorrer depois, com fixtures reais anonimizadas e evidências rastreáveis.
