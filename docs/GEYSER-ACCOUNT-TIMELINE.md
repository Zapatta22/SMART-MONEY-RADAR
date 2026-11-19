# Geyser account timeline — contrato inicial

## Escopo

`AccountUpdateTimeline` mantém, em memória, uma linha do tempo provider-neutral de `NormalizedAccountUpdate`. Não abre conexão, não persiste em SQLite/RAW, não consulta RPC e não classifica swaps.

## Duas ordens distintas

- **Ordem de ledger:** `slot` e `write_version`. É a chave de ordenação das escritas de uma conta.
- **Ordem de transporte:** `stream_id` e `stream_sequence`. Serve para detectar replay, reutilização de sequência, reconexão e lacunas na entrega.

A sequência do stream nunca desempata uma colisão de identidade de ledger. Para a mesma pubkey, slot e write_version, payloads diferentes geram conflito e não sobrescrevem o estado anterior.

## Regras de timeline

1. A primeira atualização observada de cada pubkey é baseline: não existe pre-state conhecido antes dela.
2. Updates são ordenados por `(slot, write_version)`, independentemente da ordem em que chegaram ao método `add`.
3. Reentrega idêntica é deduplicada por fingerprint. Colisão de identidade com conteúdo diferente é registrada como conflito.
4. Uma lacuna de `stream_sequence` ou troca de `stream_id` cria uma fronteira de continuidade. A primeira atualização subsequente de cada conta conhecida vira novo baseline; ela não gera par pre/post.
5. Depois desse baseline, escritas seguintes no mesmo epoch podem gerar transição se houver predecessor observado.
6. Update sem `txn_signature` permanece na timeline, mas não pode ser associado a uma transação específica.
7. `rollback_from_slot` só deve ser chamado após sinal autoritativo de rollback/fork do provider. Updates removidos são mantidos em `orphaned_updates`; a primeira escrita posterior vira baseline.

## Pareamento pre/post

`transition_for(signature)` retorna somente contas com update associado à assinatura e predecessor observado imediatamente anterior na mesma continuidade. Não retorna:
- primeiro estado conhecido da conta;
- primeiro estado depois de lacuna, reconexão ou rollback;
- update sem assinatura;
- escrita com colisão de identidade.

O par é evidência de estados observados na sequência de account writes; não prova sozinho que o stream capturou todos os dados, nem promove o commitment.

## Limitações intencionais

- Ainda não há adapter protobuf Yellowstone oficial; o normalizador recebe envelope canônico.
- A timeline é em memória e não sobrevive a reinício.
- Não armazena commitment, blockhash, parent slot ou identidade de fork. Rollback é sinal externo explícito, não inferência local.
- `write_version` é preservado como metadado de ordenação de account writes; não é substituto de índice de instrução/transação nem de ordem de execução interna.
- Uma transição não deve ser usada para reconciliação econômica até o adapter/provider comprovar a semântica do stream e o compromisso da transação em nível superior.
- Nenhum dado de fixture sintética é considerado prova mainnet.

## Testes

A suíte `tests/test_geyser_account_timeline.py` cobre ordenação ledger versus entrega, replay, colisões, lacuna de sequência, reconexão, assinatura ausente, rollback explícito e independência entre contas.
