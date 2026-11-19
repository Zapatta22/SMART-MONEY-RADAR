# Contrato do adapter de snapshots históricos Solana

**Status:** contrato arquitetural definido; adapter operacional ainda não implementado.

## 1. Objetivo e limite

Definir como uma futura camada provider-neutral pode produzir evidências históricas de mint e token accounts para a reconciliação econômica DAMM v2, sem misturar fontes ou comparar ordens que não pertencem ao mesmo domínio.

O adapter não classifica BUY/SELL, não cria sinais e não autoriza execução. Ele normaliza e preserva evidências. O reconciliador continua fail-closed.

## 2. Identidades que não podem ser confundidas

Cada evento histórico deve carregar separadamente:

- `source_id`: namespace estável do provider/nó. Deve permanecer igual em reconexões da mesma fonte lógica; não é ID de conexão.
- `ordering_domain_id`: identidade do domínio em que os valores de ordem são comparáveis. Em um stream Yellowstone multiplexado, pode corresponder ao identificador daquela conexão/stream. Um reconnect cria novo domínio, salvo se o provider oferecer explicitamente um cursor global comparável.
- `stream_id`: identidade de conexão/transporte. É metadado de continuidade; não prova, por si só, que sequências de streams diferentes sejam comparáveis.
- `stream_sequence`: ordem monotônica atribuída a cada mensagem recebida no mesmo domínio ordenado. Deve incluir mensagens de transação e account updates usados no mesmo pareamento.

**Regra obrigatória:** igualdade de `source_id` não autoriza comparar `transaction_order`, `pre_snapshot_order` ou `post_snapshot_order` de `ordering_domain_id` diferentes. A verificação agora exige domínio igual para mint e withheld snapshots.

Não derivar `stream_sequence` de timestamp, slot, `write_version`, `delivery_id`, ordem lexical de assinatura, ordem de instrução ou sequência observada em outra stream. `slot/write_version` descrevem ordem de ledger/account writes; não substituem a ordem de transporte que relaciona mensagens de famílias distintas.

Se o provider não garantir uma ordem comum para transaction updates e account updates, o adapter não deve inventar uma. O snapshot fica inelegível.

## 3. Contrato mínimo de eventos normalizados

### Transaction observation

Deve preservar:
- assinatura Solana validada;
- slot;
- payload RPC original e SHA-256 canonicalizado;
- `source_id`;
- `ordering_domain_id`;
- `stream_id` e `stream_sequence` observados;
- metadados de banco/fork e commitment disponibilizados pelo provider;
- inventário completo de instruções externas e CPI, incluindo posições e contas resolvidas.

O `transaction_order` usado nos snapshots deve ser a ordem da mensagem da transação no mesmo domínio ordenado dos account updates, não o slot ou o índice de instrução.

### Account update

Deve preservar:
- pubkey e owner do account;
- slot e `write_version`;
- bytes brutos completos da conta;
- `txn_signature` quando fornecida pelo provider;
- `bank_id`, `is_startup` e metadados de fork quando disponíveis;
- `source_id`, `ordering_domain_id`, `stream_id` e `stream_sequence`;
- referência durável ao RAW imutável e SHA-256 dos bytes.

O adapter deve validar o owner program e a identidade da conta antes de construir snapshots de Token-2022. A validação do TLV não substitui a validação do account owner, mint ou pubkey.

## 4. Regras para mint prestate

Para construir `DammV2MintPrestate`:

1. Capturar bytes completos do mint antes da mensagem da transação-alvo.
2. Exigir o mesmo `source_id` e `ordering_domain_id` da transação.
3. Exigir `pre_snapshot_order < transaction_order` no mesmo domínio. O contrato atual também exige o mesmo slot da transação; prestate de outro slot permanece inelegível nesta versão.
4. Preservar `source`, `state_ref`, bytes brutos e `source_id`.
5. O builder calcula SHA-256 dos bytes e decodifica `TransferFeeConfig` a partir desses mesmos bytes.
6. O inventário externo/CPI de `InitializeTransferFeeConfig` deve estar completo e demonstrar que não houve inicialização anterior à transferência. A semântica de `SetTransferFee` e epoch permanece validada separadamente.
7. Se houver lacuna, reconnect, baseline sem predecessor, fork não resolvido, stream/domain diferente ou estado ausente, não produzir snapshot elegível.

O adapter não pode substituir prestate histórico pelo estado atual retornado por RPC.

## 5. Regras para withheld pre/post

Para construir `DammV2WithheldFeeSnapshot`:

1. Obter a transição da token account específica associada à assinatura-alvo.
2. O prestate deve preceder a mensagem da transação; o poststate deve sucedê-la no mesmo `ordering_domain_id`.
3. Exigir `pre_snapshot_order < transaction_order < post_snapshot_order`.
4. O poststate precisa estar associado à assinatura exata da transação-alvo. Se o provider não fornecer essa associação, não presumir que a atualização pertence à transação.
5. Exigir continuidade sem gap/reconnect entre os estados, baseline válido e linhagem de banco utilizável. Bancos irmãos, parent slot isolado ou ordenação de entrega não provam ancestralidade.
6. Preservar bytes TLV pre/post e referências RAW separadas. O verifier recalcula os dois hashes, redecodifica `TransferFeeAmount` e compara o delta com a evidência recebida.
7. Validar pubkey, owner program, mint e identidade da token account antes de materializar o snapshot.

Se a conta não tiver update pós-transação associado à assinatura, não inferir poststate a partir de saldo, timestamp ou próxima observação não vinculada.

## 6. Continuidade, replay e forks

- RAW é imutável e recebe todos os deliveries disponíveis, inclusive os não sequenciados.
- Delivery sem sequência nunca recebe sequência inferida.
- Gap, reconnect ou mudança de `ordering_domain_id` cria uma fronteira: o primeiro update subsequente é baseline e não prova transição pre/post através da fronteira.
- Replay idêntico é idempotente; conflito de identidade não sobrescreve RAW nem vira testemunha.
- `slot/write_version` ordenam account writes no ledger; `stream_sequence` estabelece apenas ordem de mensagens dentro do domínio de transporte. Não trocar uma semântica pela outra.
- Banco morto, invalidado ou com ancestralidade desconhecida não pode produzir transição elegível. Histórico órfão permanece auditável, mas inelegível.

## 7. Commitment e promoção a VERIFIED

A camada atual verifica identidade, bytes, TLV e ordem declarada. SHA-256 não autentica o provider, e `source_id/ordering_domain_id` não provam que o adapter recebeu todos os eventos.

Antes de uso operacional, ainda deve ser formalizada uma política explícita de commitment/fork finality e sua representação tipada no snapshot/verifier. Até essa política ser implementada e validada, dados sintéticos e snapshots apenas processados/observados não devem ser descritos como prova mainnet nem usados para autorizar execução.

## 8. Interface pretendida do adapter

O adapter provider-neutral deverá expor operações equivalentes a:

- normalizar transaction observations e account updates, preservando bytes e metadados originais;
- atribuir/transportar `ordering_domain_id` e `stream_sequence` sem fabricar continuidade;
- obter transição pre/post de account updates pela timeline bank-aware;
- construir `DammV2MintPrestate` e `DammV2WithheldFeeSnapshot` somente após todas as invariantes;
- emitir resultado explícito `ELIGIBLE` ou `INELIGIBLE` com razões e referências RAW.

A implementação deverá permanecer provider-neutral. Yellowstone/Helius é uma possível fonte de eventos, não uma dependência conectada ou aprovada nesta etapa.

## 9. Critérios de aceitação antes de integrar provider

- Testes de streams separadas com o mesmo `source_id` e sequências incompatíveis: rejeição.
- Testes de reconnect/gap e baseline: rejeição de pares através da fronteira.
- Testes de assinatura ausente/divergente no poststate: rejeição.
- Testes de banco morto, fork irmão e ancestralidade desconhecida: rejeição.
- Testes de bytes pre/post adulterados, owner/mint/pubkey divergentes e TLV inválido: rejeição.
- Replay idêntico preserva idempotência; conflito não altera evidência original.
- Fixture positiva usa um único domínio ordenado e percorre ingestão -> RAW -> timeline bank-aware -> snapshot -> verifier.
- CI integral e auditoria de proveniência aprovados antes de qualquer execução financeira.


## 10. Yellowstone transaction observation — contrato inicial

A implementação inicial em `geyser_transaction_updates.py` normaliza o wrapper `SubscribeUpdateTransaction` sem decodificar sua semântica econômica:

- valida assinatura de 64 bytes e exige igualdade com a primeira assinatura contida no objeto Transaction;
- preserva slot e o valor de bank_id do wrapper quando exposto pelo schema, índice de transação quando disponível, flag de vote, bytes serializados de Transaction e bytes serializados de TransactionStatusMeta;
- o schema oficial declara bank_id como escalar proto3; zero pode ser o valor padrão. Nenhum valor deste campo confirma linhagem ou finalidade por si só;
- preserva ausência de meta como evidência incompleta. Um campo presente, inclusive vazio, indica apenas presença de meta;
- exige `source_id`, `stream_id`, `ordering_domain_id` e `stream_sequence` explícitos;
- o receptor deve atribuir a sequência monotônica a cada mensagem SubscribeUpdate recebida, antes da dispatch por tipo. Não usar contadores separados para transaction/account/slot;
- `ordering_domain_id` precisa ser o mesmo domínio declarado para os account updates que serão correlacionados. Esta implementação ainda não cria o sequenciador nem persiste a observação no RAW;
- quando o transporte fornece `raw_message_bytes`, o adaptador decodifica os bytes e exige que o resultado corresponda à mensagem no mesmo nível protobuf (`SubscribeUpdate` na dispatch, `SubscribeUpdateTransaction` na chamada direta). Os bytes exatos e seu SHA-256 são então preservados como proveniência `WIRE`. A correspondência verifica conteúdo, e a captura e autenticação continuam sob responsabilidade do receptor. Sem esses bytes, a implementação registra apenas uma serialização protobuf determinística, explicitamente identificada como `PROTOBUF_DETERMINISTIC_RESERIALIZATION`, que não pode ser apresentada como wire RAW original;
- a observação normalizada não atribui `transaction_order`, não decodifica instruções/CPI, não constrói snapshots e não classifica BUY/SELL.

A camada permanece offline e provider-neutral. A próxima integração deve provar que o mesmo sequenciador, domínio e persistência RAW abrangem transaction e account updates, incluindo reconnect/gap/replay, antes de snapshots históricos se tornarem elegíveis.

### Evidência de transação pelo replay Yellowstone

`YellowstoneFrameReceiver.replay_transaction_evidence` deriva inventário,
transferências e deltas com a factory Solana já usada no caminho RPC. A projeção
traduz índices compilados, CPI, endereços carregados e valores inteiros dos
saldos. O hash do envelope wire permanece na observação e o hash da projeção
JSON permanece no bundle. Uma execução com erro, ausência de metadados ou CPI
indisponível deixa a evidência estruturalmente incompleta. Endereços carregados
com cardinalidade incompatível interrompem a projeção. O consumidor deve
concluir o replay antes de publicar resultados, pois um frame posterior pode
revelar falha de integridade. Esta etapa não associa snapshots históricos nem
atribui finalidade ao bundle.

`transaction_evidence_at` materializa uma transação por sequência e confere as
transições de conta no mesmo snapshot do journal. Exige assinatura não
ambígua, conta presente na transação, slot e banco compatíveis e finalidade
reportada pelo provedor para o par de estados. Um banco zero, ausente ou
divergente, uma conta com conflito ou uma segunda conexão deixa a transição
inelegível. A ordenação no transporte não é convertida em ordem de execução
no ledger. A finalidade reportada fica explícita como proveniência e ainda
depende da validação operacional do provedor.

### Inspeção operacional de um journal local

Com o descriptor compilado do schema confiável, execute:

```bash
smr geyser-evidence journal.sqlite --descriptor yellowstone.desc \
  --source validator-a --stream connection-a --domain domain-a --sequence 40
```

O comando abre um arquivo existente em modo somente leitura, sem migrar o
schema, e valida o snapshot antes de emitir JSON com hashes, diagnóstico dos
decodificadores e proveniência das transições. A inspeção usa exclusivamente
o arquivo local e o descriptor. Um domínio interrompido, uma assinatura
ambígua ou uma sequência sem transação produz erro.

### Reconciliação econômica DAMM v2

Acrescente `--damm-wallet ENDERECO_SOLANA` à inspeção do journal para obter
o resultado da reconciliação e os estados de verificação das taxas. O
comando exige evidência estruturada e o banco da transação com finalidade
reportada na mesma captura. Um banco morto ou um banco sem finalidade deixa
a reconciliação incompleta. O resultado pode reconciliar transferências e
deltas da transação com taxas históricas ainda marcadas como
`EXPECTED_NOT_VERIFIED`. Este caminho não usa sequência de transporte como
ordem no bloco, nem cria snapshots históricos.

### Índice no bloco comprovado no journal

O argumento opcional `--block-sequence` indica o envelope de bloco a conferir
durante a mesma leitura do journal. O comando exige banco finalizado, hash
compatível com os metadados do banco, mesmo slot e banco, total executado
compatível com a lista de transações, índices únicos e sem lacunas e
correspondência de assinatura, conteúdo, meta e índice da transação.
O JSON informa o índice no ledger, a sequência do frame do bloco e seu
SHA-256. Um bloco filtrado que omite transações falha nessa validação.
Com `--damm-wallet`, a inspeção usa o índice comprovado para verificar o
withheld de Token-2022 quando todos os destinos têm um par de estados no
mesmo banco. O estado anterior deve estar ligado à transação imediatamente
anterior no bloco e o estado posterior deve estar ligado à transação alvo.
O verificador compara mint, bytes TLV, hashes e delta esperado. Sem cobertura
dos pares, o withheld permanece como `EXPECTED_NOT_VERIFIED`. A configuração
histórica das taxas do mint continua sem verificação.

### Configuração histórica da taxa do mint

Com `--damm-wallet` e `--block-sequence`, passe uma resposta arquivada de
`getEpochSchedule` da rede capturada via `--epoch-schedule CAMINHO`. A
inspeção deriva o epoch a partir do slot, valida as fronteiras de warmup e
inclui o SHA-256 do arquivo com a proveniência `operator_supplied`. O
arquivo é fornecido pelo operador e precisa corresponder à rede capturada.

O verifier usa apenas mints Token-2022 cujo estado está associado à
transação imediatamente anterior do mesmo banco comprovado. O caminho
confere a taxa ativa para o epoch e mantém `EXPECTED_NOT_VERIFIED` se
faltarem todos os estados exigidos. A verificação é posterior à reconciliação
base. Casos que exigem o prestate para calcular o fee de referral antes da
reconciliação base seguem incompletos.
