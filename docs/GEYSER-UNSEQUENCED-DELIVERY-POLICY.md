# Política de auditoria para entregas RAW sem sequência

**Status:** implementado e validado por CI/benchmark sintético na PR #26  
**Policy ID:** `geyser-unsequenced-delivery:v2`  
**Branch:** `feat/geyser-unsequenced-raw-audit`  
**Base:** `4a517ca15499746ddd3f5522f112c80aaac1433b`

## 1. Objetivo e invariantes

Esta política classifica entregas RAW cujo transporte não forneceu `stream_sequence`. Ela não altera a identidade lógica dos eventos, não modifica conteúdo RAW e não cria ordenação temporal artificial.

Invariantes obrigatórios:

1. `geyser_raw_events`, `geyser_raw_deliveries` e conflitos existentes permanecem a fonte de evidência imutável; a política não atualiza nem apaga essas linhas.
2. Toda classificação é uma projeção derivada e reconstruível a partir das tabelas RAW/deliveries/conflitos.
3. `delivery_id` representa ordem local de persistência/observação, não ordem do ledger nem ordem de transporte.
4. Timestamp de recebimento, slot, write_version ou ordem de inserção não substituem uma sequência de transporte ausente.
5. Uma entrega sem sequência nunca avança checkpoint de transporte e nunca fecha gap.
6. A classificação de uma entrega não concede, por si só, elegibilidade para a timeline.

## 2. Escopo e granularidade

A unidade classificada é cada linha de `geyser_raw_deliveries`, não apenas o evento lógico. Isso preserva a distinção entre várias entregas/replays do mesmo evento.

A projeção deve identificar cada entrega por `delivery_id` e carregar, quando disponível, `event_id`, `source_id`, `stream_id`, `stream_sequence`, `payload_sha256`, versão da política e geração.

A tabela de auditoria é derivada. Ela não deve inserir linhas em `geyser_raw_events`, reescrever deliveries, resolver automaticamente anomalias de transporte ou alterar checkpoints.

## 3. Classificações

- `SEQUENCED`: delivery possui sequência não nula e está ligada a um evento RAW íntegro, sem conflito impeditivo.
- `UNSEQUENCED_UNRESOLVED`: delivery sem sequência e sem evidência suficiente de correspondência sequenciada.
- `UNSEQUENCED_RECONCILED`: delivery sem sequência cujo evento lógico tem outra delivery sequenciada com mesmo `event_id`, mesma `source_id` e mesmo SHA-256 do conteúdo RAW.
- `IDENTITY_CONFLICT`: delivery associada a conflito RAW, evento ausente/ambíguo, ou identidade reutilizada com conteúdo divergente.
- `SEQUENCE_ANOMALY`: delivery sequenciada afetada por reutilização de sequência ou qualquer anomalia de transporte historicamente registrada, independentemente de estar `OPEN` ou `RESOLVED`.

A classificação deve incluir um código de motivo estável, não apenas texto livre. Texto explicativo pode ser armazenado adicionalmente.

## 4. Regra estrita de reconciliação

Uma delivery sem sequência só pode receber `UNSEQUENCED_RECONCILED` se existir pelo menos uma delivery sequenciada que satisfaça simultaneamente:

- mesmo `event_id` não nulo;
- mesmo `source_id`;
- mesmo SHA-256 obtido do evento RAW persistido;
- evento RAW sem conflito de conteúdo pendente para aquela identidade;
- delivery sequenciada sem qualquer anomalia registrada para sua combinação `(source_id, stream_id, stream_sequence)`. O status administrativo `RESOLVED` não reabilita a sequência.

A stream pode ser diferente: replays/backfills em streams diferentes são observações possíveis do mesmo evento lógico. A reconciliação identifica o evento, não transfere a sequência de uma stream para outra.

A delivery sem sequência permanece sem sequência para sempre. A evidência sequenciada relacionada é referenciada separadamente, incluindo `delivery_id`, `source_id`, `stream_id` e sequência da delivery testemunha.

Se duas ou mais deliveries sequenciadas elegíveis existirem, a projeção registra todas as referências ou seleciona deterministicamente uma testemunha apenas para navegação, mantendo a lista completa de evidências. Nunca combina sequências de streams distintas.

## 5. Casos que não autorizam reconciliação

- Mesmo timestamp ou timestamp próximo.
- Mesmo slot, pubkey, write_version ou assinatura isoladamente.
- Mesmo `event_id` com SHA-256 diferente.
- Fonte diferente, mesmo que os campos de negócio coincidam.
- Uma sequência observada em outra stream sem identidade RAW idêntica.
- Ordem de chegada/ordem crescente de `delivery_id`.
- Inferência por vizinhança de eventos.

Nesses casos, a delivery continua não resolvida ou é marcada como conflito, sem ser incorporada à timeline.

## 6. Relação com a timeline

A timeline continua consumindo somente eventos com evidência sequenciada elegível, conforme o contrato atual de rebuild. A auditoria de entregas sem sequência é uma camada paralela, consultável e reconstruível.

Uma delivery reconciliada não cria uma segunda ocorrência lógica na timeline. O evento é projetado uma única vez pela regra determinística já existente para escolher uma delivery sequenciada elegível.

Uma delivery sem sequência e sem testemunha sequenciada não entra na timeline. Sua existência deve aparecer nas métricas de auditoria/skipped, sem ser confundida com evento RAW perdido.

A política não altera a semântica atual de baseline/cobertura (`COMPLETE`, `PARTIAL`, `UNKNOWN`). A ausência de sequência deve ser exposta como métrica/classificação separada; não deve ser convertida automaticamente em gap, pois não há número de sequência ausente conhecido.

## 7. Determinismo e rebuild

- Ordenação de leitura da projeção: `delivery_id` para estabilidade de auditoria local, explicitamente não semântica.
- Reconciliação: igualdade exata de identidade, fonte e hash.
- Mesma entrada RAW + mesma versão de política deve produzir as mesmas classificações e relações de evidência, desconsiderando metadados operacionais como horário de execução.
- Cada rebuild substitui atomicamente a geração derivada.
- Checkpoints de recuperação só avançam depois do commit da geração da auditoria, seguindo o padrão já adotado pela timeline.
- Falha antes do commit mantém a geração e checkpoints anteriores.

## 8. Evolução de schema e testes

A implementação deve usar migração aditiva versionada; não alterar nem reconstruir tabelas RAW existentes. Índices devem cobrir delivery, evento e classificação.

Testes mínimos:

1. Entrega isolada sem sequência permanece `UNSEQUENCED_UNRESOLVED`.
2. Entrega sem sequência seguida de replay sequenciado, mesmo evento/hash/fonte, torna-se reconciliada.
3. Replay sequenciado em outra stream pode servir de testemunha sem transferir sua sequência.
4. Mesmo event_id com hash divergente nunca reconcilia.
5. Fonte diferente nunca reconcilia.
6. Timestamp, slot ou ordem de chegada iguais não reconciliam.
7. Várias deliveries sem sequência do mesmo evento são preservadas individualmente.
8. Duplicação/rebuild repetido produz a mesma classificação lógica.
9. Evento com conflito RAW não reconcilia.
10. Sequência afetada por qualquer anomalia histórica, inclusive `RESOLVED`, não é testemunha elegível; a resolução administrativa não remove o taint.
11. Falha forçada durante gravação reverte toda a geração derivada.
12. RAW, deliveries, hashes e checkpoints de transporte permanecem byte/logicamente inalterados.
13. Evento não sequenciado isolado não entra na timeline nem avança checkpoint.
14. Quando uma testemunha sequenciada chega posteriormente, rebuild atualiza a classificação sem reescrever RAW.

## 9. Fora de escopo

- Conexão com Yellowstone, Helius ou qualquer provedor.
- Alteração de `main`, merge ou execução on-chain.
- Inferência de ordem por timestamp, slot ou ordem de chegada.
- Reescrita retroativa de sequência em deliveries.
- Resolver automaticamente conflitos ou anomalias de transporte.

## 10. Critério de aceite

A implementação desta política está presente na PR #26, com projeção derivada, schema versionado, rebuild transacional, testes de invariantes/rollback, CI e `compileall` aprovados, benchmark sintético e Registro Mestre atualizado. Esta validação comprova os testes automatizados e os cenários sintéticos documentados; não comprova ainda operação com provider Geyser real, RPC, tráfego contínuo ou ambiente de produção.
