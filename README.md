# SMART MONEY RADAR (SMR)

Infraestrutura local para observar atividade pública de carteiras na blockchain
Solana. A integração Helius usa JSON-RPC e WebSocket padrão, enriquece
notificações com detalhes de transação e grava eventos em SQLite.

## Garantias e limites

- Somente leitura: são usados `getVersion`, `getSignaturesForAddress`,
  `getTransaction` e `logsSubscribe`. Não existe envio ou assinatura de
  transações.
- O monitor acompanha somente endereços públicos passados explicitamente.
- Nenhuma chave privada ou frase-semente é aceita ou armazenada.
- Chamadas externas ficam bloqueadas por padrão. `SMR_ALLOW_NETWORK=true` é uma
  autorização explícita para o SMR fazer requisições; antes disso, verifique os
  limites e possíveis custos do seu plano Helius. Este projeto não contrata um
  plano nem faz uma conexão automaticamente.
- A API key é lida de `HELIUS_API_KEY`, nunca impressa em logs ou incluída no
  README.
- O arquivo `.env` local e o banco SQLite são ignorados pelo Git.

## Estrutura e módulos

```text
smart-money-radar/
├── .env.example
├── README.md
├── pyproject.toml
├── src/smart_money_radar/
│   ├── cli.py
│   ├── settings.py
│   ├── analysis/metrics.py
│   ├── data_sources/
│   │   ├── base.py
│   │   ├── helius.py
│   │   ├── solana.py
│   │   └── transaction_parser.py
│   ├── domain/models.py
│   ├── services/
│   │   ├── wallet_monitor.py
│   │   └── wallet_tracker.py
│   └── storage/event_store.py
└── tests/
```

- `settings.py`: carrega ambiente/`.env`, valida cluster e bloqueia acesso de
  rede sem autorização explícita.
- `data_sources/helius.py`: cliente HTTP JSON-RPC de leitura, valida respostas
  e evita expor a URL que contém a API key.
- `data_sources/transaction_parser.py`: extrai deltas por token a partir dos
  saldos pré/pós e transferências SOL identificadas em instruções decodificadas.
  O mint sentinela `SOL` representa SOL nativo, não um mint SPL.
- `data_sources/solana.py`: mantém o nome da classe inicial e encaminha para o
  adaptador Helius quando recebe configuração.
- `services/wallet_monitor.py`: abre WebSocket com `logsSubscribe` por endereço,
  consulta detalhes das assinaturas e reconecta com backoff exponencial. O
  WebSocket envia ping periódico para manter a sessão ativa.
- `storage/event_store.py`: histórico SQLite local, com deduplicação por
  carteira, assinatura, mint e direção.
- `domain/models.py`: modelos para carteiras públicas e eventos observados.
- `analysis/metrics.py`: contagens descritivas por mint; não classifica
  carteiras nem fornece recomendação financeira.
- `services/wallet_tracker.py`: serviço existente preservado para consultas
  através de uma fonte compatível.
- `tests/`: testes `unittest` com respostas HTTP/WebSocket simuladas; não
  conectam à blockchain.

## Instalação e configuração

Na pasta `smart-money-radar`:

```bash
python -m pip install -e .
cp .env.example .env
```

Preencha `HELIUS_API_KEY` somente no arquivo local `.env` ou no mecanismo de
Secrets do ambiente. Nunca envie a chave pelo chat nem a grave no código. Para
autorizar acesso externo, revise as condições da sua conta Helius e então altere
`SMR_ALLOW_NETWORK` para `true`. O valor de exemplo é `false`.

`SOLANA_CLUSTER` aceita `mainnet` ou `devnet`. O histórico fica em
`data/smr_history.sqlite3`, salvo se `SMR_DB_PATH` apontar para outro local.

## Comandos

Sem argumentos, o SMR mostra ajuda de estado e não faz chamadas de rede:

```bash
smr
```

`check` faz uma consulta RPC `getVersion` e só informa sucesso após receber uma
resposta válida:

```bash
smr check
```

`watch` abre um monitor WebSocket para endereços públicos e grava novos eventos
no banco local. Encerre com `Ctrl+C`:

```bash
smr watch <ENDERECO_PUBLICO> [OUTRO_ENDERECO_PUBLICO ...]
```

O método padrão `logsSubscribe` aceita um endereço por assinatura; o SMR cria
uma assinatura para cada endereço informado na mesma conexão. Para eventos
confirmados, consulta `getTransaction` e extrai o mint, assinatura, horário
quando fornecido pelo RPC, direção e quantidade quando os dados permitem. SOL é
extraído apenas de instruções `system` decodificadas; taxas não são tratadas como
transferências.

Referências do protocolo:

- [Helius `logsSubscribe`](https://www.helius.dev/docs/api-reference/rpc/websocket/logssubscribe)
- [Helius endpoints RPC e WebSocket](https://www.helius.dev/docs/api-reference/endpoints)
- [Solana `getTransaction`](https://solana.com/docs/rpc/http/gettransaction)

## Testes

```bash
python -m unittest discover -s tests -v
```

Os testes simulam RPC, notificações WebSocket, reconexão, parser e SQLite. Não
fazem requisições reais e, portanto, não verificam credenciais, disponibilidade
do Helius ou conexão com a blockchain. A conexão real só deve ser verificada
executando `smr check` ou `smr watch` após habilitar a rede e configurar uma API
key válida.
## Recuperação incremental de monitoramento

O monitor mantém um checkpoint por carteira em `wallet_checkpoints`. Após uma
reconexão, consulta `getSignaturesForAddress` e recupera assinaturas posteriores
ao último checkpoint, processando-as da mais antiga para a mais recente. O
checkpoint só avança depois de a transação estar disponível e ser persistida; uma
transação temporariamente indisponível recebe até três tentativas com espera
exponencial. A recuperação é limitada a 10 páginas de até 100 assinaturas por
carteira por conexão. Se o checkpoint não for encontrado nesse limite, o
monitor interrompe a recuperação com erro explícito em vez de avançar e ocultar
uma possível lacuna. Na primeira execução, não faz varredura histórica: começa
a acompanhar notificações novas.


## Robustez do monitor — Etapa 2 (16/11/2026)

- Assinaturas que já constam como processadas para a carteira são ignoradas
  antes de consultar novamente `getTransaction`. Isso elimina a duplicação entre
  notificações WebSocket recebidas durante o backfill e o próprio backfill.
- `save_checkpoint` grava a assinatura processada e atualiza o checkpoint na
  mesma transação SQLite.
- O encerramento da CLI aguarda tarefas assíncronas e o executor padrão
  (`asyncio.to_thread`) antes de fechar o Event Store e o event loop.
- O fechamento do Event Store é idempotente para o banco em memória.
- Testes adicionais cobrem limite de páginas, esgotamento de retries, erro RPC,
  sobreposição WebSocket/backfill, encerramento normal e encerramento após erro.

Validação local da Etapa 2: 26 testes `unittest` aprovados e `compileall`
aprovado. Os testes usam doubles/mocks; não houve conexão real com Helius ou
Solana, benchmark de latência, nem implantação em Replit/VPS.


### Limites atuais do parser Solana

O parser atual é conservador e trabalha com respostas `getTransaction` em `jsonParsed`:

- calcula deltas agregados por mint usando `preTokenBalances` e `postTokenBalances` cujo `owner` corresponde à carteira monitorada;
- identifica instruções System Program `transfer` e `transferWithSeed` explicitamente decodificadas, inclusive em `innerInstructions`;
- não reconstrói a semântica completa de swaps, rotas de agregadores, pools, LP, staking, lending, criação/fechamento de contas, rent, taxas ou recompensas;
- não calcula preço, valor em USD, slippage, PnL nem atribui intenção à movimentação;
- não deve ser usado ainda como fonte única para decisão de compra/venda.

Respostas sem os dois arrays de saldos de tokens não geram deltas de token. O campo `decimals` é limitado ao intervalo u8 do SPL Token (0–255). A cobertura de programas e instruções precisa ser ampliada com fixtures reais anonimizadas e testes específicos antes de qualquer decisão automatizada.


### Arquivamento bruto e replay de parsing

Cada transação obtida com sucesso é agora registrada em `observed_transactions` junto com o payload JSON bruto, estado de parsing, versão do parser e eventual classe de erro. A gravação do payload, dos eventos derivados, da assinatura processada e do checkpoint ocorre na mesma transação SQLite. Transações sem eventos reconhecidos ficam marcadas como `no_events`; exceções do parser ficam como `parse_error`; falhas on-chain conhecidas ficam como `failed_on_chain`.

`get_raw_transaction` permite recuperar o payload para auditoria e `reprocess_observation` substitui os eventos derivados de uma observação sem mover o checkpoint. A retenção dos payloads ainda não tem política automática: o crescimento do banco deve ser medido e uma política de retenção/compactação precisa ser definida antes de operação contínua em volume.

### Estados de observação

Os estados de parsing registrados são `parsed`, `no_events`, `parse_error` e `failed_on_chain`. `no_events` não significa que a transação foi irrelevante: significa apenas que o parser atual não produziu eventos. O payload bruto é preservado para replay. `reprocess_observation` substitui os eventos derivados e atualiza a versão/estado sem alterar o checkpoint. A versão atual do parser é `PARSER_VERSION = "1"`.

### Persistência, integridade e backup — Etapa 5

- Bancos SQLite em disco usam `WAL`, `synchronous=NORMAL` e `busy_timeout=15000` para melhorar a convivência entre leituras e gravações e tolerar contenção transitória.
- `integrity_check()` executa `PRAGMA integrity_check` e retorna o resultado integral do SQLite.
- `storage_stats()` informa contagens de eventos, transações observadas, assinaturas processadas e checkpoints, além do tamanho lógico estimado por páginas.
- `backup_to(path)` cria uma cópia consistente usando a API online-backup do SQLite e valida a integridade do arquivo de destino antes de retornar.
- O backup não apaga nem modifica o banco de origem. O destino não pode ser o próprio arquivo de banco.
- Não há ainda agendamento automático, retenção, criptografia externa, cópia off-site nem teste de restauração operacional em VPS. Esses itens permanecem necessários antes de operação 24/7.

Validação local da Etapa 5: 44 testes `unittest` aprovados e `compileall` aprovado. O teste de backup restaura payload bruto e checkpoint em um segundo banco e confirma `integrity_check = ok`. Não houve teste de carga, falha física de disco, backup remoto ou conexão real com Helius.

### Validação estrita de campos RPC — Etapa 6

O parser agora exige tipos JSON coerentes com os campos do protocolo: `blockTime` inteiro, `decimals` SPL inteiro não booleano e `lamports` inteiro não booleano. Strings e floats não são convertidos silenciosamente, evitando truncamento de escala e quantias ambíguas. A suíte cobre esses casos. Isso não amplia a cobertura semântica de programas Solana nem transforma o parser em decodificador de swaps.

### Contratos de domínio normalizados — Etapa 7

`domain/models.py` agora define contratos tipados para `ObservedTransaction`,
`TokenBalanceDelta`, `SwapObservation`, `PoolSnapshot` e `WalletProfile`.
Eles validam identificadores, estados de parsing, quantidades `Decimal`, escala
SPL, confiança, evidências e consistência temporal/métrica. Os contratos são
fundação de integração, não indicam que Launch Radar, Market Radar, Swap
Decoder, Wallet Intelligence ou execução estejam implementados. O parser e o
monitor ainda usam `ActivityEvent`; a migração dos fluxos para os novos tipos
será feita de forma incremental, com compatibilidade e testes.

Validação da Etapa 7: 53 testes `unittest` aprovados e `compileall` aprovado.
Não houve chamada real à Solana/Helius, nem integração operacional dos novos
contratos com os pipelines de monitoramento.

### Normalização e persistência integrada — Etapas 8 e 9

`domain/normalization.py` fornece `normalize_transaction`, que produz o envelope
`ObservedTransaction`, deltas SPL `TokenBalanceDelta` e os `ActivityEvent`
legados. O SOL nativo continua fora do modelo SPL. A escala `decimals` é
preenchida somente quando os registros de saldo da carteira concordam.

O `WalletMonitor` usa o adaptador durante a ingestão. O `SQLiteEventStore`
persiste os metadados normalizados (`chain`, `slot`, `occurred_at`) e os deltas
na tabela `token_balance_deltas`, mantendo `observed_transactions` como arquivo
bruto e `activity_events` como compatibilidade legada. A gravação dos três
conjuntos derivados, payload, assinatura processada e checkpoint é atômica.

A inicialização migra bancos existentes adicionando colunas normalizadas
ausentes sem apagar observações anteriores. `get_token_deltas` recupera os
deltas tipados. `reprocess_observation` pode substituir eventos e deltas
normalizados quando recebe um novo resultado normalizado, sem mover checkpoint
nem alterar o payload bruto original. `storage_stats` inclui a nova tabela.

Os testes cobrem migração de banco legado, rollback forçado durante a gravação
de deltas, persistência conjunta, replay e compatibilidade dos eventos antigos.
A validação permanece local e simulada; não houve RPC real, carga, benchmark ou
implantação.

### Adaptador de normalização — Etapa 8

`domain/normalization.py` introduz `normalize_transaction`, que recebe o payload
RPC e devolve `NormalizedObservation`: envelope `ObservedTransaction`, deltas
SPL tipados em `TokenBalanceDelta` e eventos legados `ActivityEvent`. O adaptador
classifica `parsed`, `no_events` e `failed_on_chain`, preserva o payload bruto,
registra slot/horário quando válidos e mantém SOL nativo fora dos deltas SPL.

O adaptador ainda não substitui o fluxo de persistência do WalletMonitor nem
altera o esquema SQLite. A integração transacional no EventStore será feita em
etapa própria, com testes de regressão e migração explícita.

Validação da Etapa 8: 58 testes `unittest` aprovados e `compileall` aprovado.


### Registro de programas Solana — Etapa 10

`domain/program_registry.py` contém a matriz inicial de programas prioritários da V1, com IDs Base58, papel (core/launchpad/AMM/agregador), prioridade e fonte de referência. O registro não significa que os decodificadores estejam implementados. Jupiter é classificado como agregador, não como venue, para evitar dupla contagem de rotas e swaps internos.

A matriz, assinaturas públicas candidatas e critérios para fixtures reais anonimizadas estão em `docs/fixtures/ETAPA10-MATRIZ-PROGRAMAS-E-FIXTURES.md`. As assinaturas listadas ainda não são fixtures: o payload RPC bruto e seu hash precisam ser coletados e verificados antes de testes de parsing.

### Coleta controlada de fixtures Solana (Etapa 11)

O utilitário `tools/collect_solana_fixtures.py` baixa transações finalized via JSON-RPC HTTPS somente leitura, preserva bytes brutos e gera manifesto SHA-256. Configure `SMR_SOLANA_RPC_URL` no ambiente; consulte `docs/fixtures/ETAPA11-COLETOR-RPC-EVIDENCIAS.md`. O coletor não usa Helius por padrão, não envia transações e não sobrescreve evidências.

### Auditoria offline de fixtures (Etapa 12)

Depois de coletar evidências, execute `python tools/audit_solana_fixtures.py <diretorio>` para verificar manifesto, hash, slot e assinatura sem rede. A aprovação semântica e a anonimização continuam sendo etapas separadas; fixtures sintéticas dos testes não contam como evidência mainnet.

### Anonimização de fixtures Solana — Etapa 13

`data_sources/fixture_anonymizer.py` cria uma projeção de teste separada do
payload RPC bruto. O fluxo de coleta da Etapa 11 usa `encoding=json`; instruções
compiladas são resolvidas com `accountKeys` e `meta.loadedAddresses`. O JSON original é lido sem alteração; signers/fee payer,
owners de tokens e token accounts identificadas por `accountIndex` recebem
aliases Base58 determinísticos derivados de uma chave secreta local. Program IDs
resolvidos por `programIdIndex`, IDs explícitos de programa, mints e endereços
informados em `--protect` são preservados. Substituições em logs são feitas por
token Base58 completo, nunca por substring.

O mapa reversível é confidencial e deve ficar fora da pasta de fixtures; o CLI
exige `SMR_FIXTURE_ANONYMIZATION_KEY` (mínimo 16 bytes), não grava o segredo e
cria o mapa com permissão de arquivo `0600`. Projeção, manifesto e mapa não
sobrescrevem arquivos existentes. O manifesto da projeção registra SHA-256 do
bruto e da projeção, assinatura/slot e contagem de endereços substituídos.

Exemplo offline, após obter o JSON bruto e manifesto por um canal RPC autorizado:

```bash
export SMR_FIXTURE_ANONYMIZATION_KEY='use-um-segredo-aleatorio-local-com-mais-de-16-bytes'
PYTHONPATH=src python tools/anonymize_solana_fixture.py \\
  fixtures-private/<assinatura>.raw.json \\
  tests/fixtures/solana/<nome>.anonymized.json \\
  ../smr-private-maps/<nome>.map.json \\
  --manifest fixtures-private/<assinatura>.manifest.json \\
  --protect <POOL_OU_CONTA_DE_PROTOCOLO> \
  --anonymize <CARTEIRA_PESSOAL_FORA_DOS_SALDOS_SPL>
```

O mapa não deve ser commitado, compartilhado nem incluído no pacote de testes.
A preservação de contas de pool/vault depende de serem identificadas e passadas
em `--protect`; a anonimização não aprova semântica de swap. O teste automatizado
usa payload construído apenas como entrada de teste do anonimizador, não como
fixture mainnet. Ainda não há fixture real aprovada, pois a coleta RPC real
continua bloqueada por DNS no runtime.


Relatório da Etapa 13: `docs/fixtures/ETAPA13-ANONIMIZADOR.md`.
Validação atual da cópia de auditoria: 86 testes `unittest` aprovados e `compileall` aprovado; testes locais/offline.

## Etapa 14 — coleta em lote e preflight RPC

Os cinco candidatos mainnet documentados na Etapa 10 foram consolidados em `data/fixtures/candidates/solana_mainnet_candidates.json`. Para verificar conectividade sem exibir URL completa ou credenciais:

```bash
PYTHONPATH=src python tools/check_solana_rpc.py
```

Para coletar os cinco candidatos em lote, após configurar `SMR_SOLANA_RPC_URL` com endpoint HTTPS autorizado:

```bash
PYTHONPATH=src python tools/collect_solana_fixtures.py \
  --candidate-file data/fixtures/candidates/solana_mainnet_candidates.json \
  --output data/fixtures/raw
```

O arquivo de candidatos registra assinaturas e metadados resumidos do explorer; não contém payloads e não representa fixtures aprovadas. O preflight usa somente `getHealth`; a coleta continua usando `getTransaction` finalized, sem assinatura ou envio de transações. Não usar endpoints pagos nem créditos Helius sem autorização explícita.


## Etapa 15 — endurecimento do coletor de fixtures

O coletor RPC valida agora a assinatura Solana como Base58 com exatamente 64 bytes decodificados antes de qualquer chamada de rede. Isso também impede que conteúdo arbitrário seja usado como nome/caminho de arquivo. A resposta JSON-RPC precisa ser um objeto; respostas JSON com outra estrutura são rejeitadas.

A gravação do payload bruto e do manifesto usa criação exclusiva (`xb`/`x`), `flush` e `fsync`, evitando sobrescrita inclusive em conflitos entre processos. Se a criação do manifesto falhar após a criação do bruto, o bruto criado por aquela tentativa é removido; arquivos preexistentes permanecem intactos.

Os cinco candidatos documentados passam na validação estrutural Base58/64 bytes. Isso valida apenas o formato das assinaturas, não a existência, finalização ou semântica das transações.

## Etapa 16 — execução assistida pelo Android

Em Android com Termux, Python e o projeto extraído, execute `bash tools/run_smr_android.sh`. O fluxo usa por padrão o RPC público Solana (`getHealth` e `getTransaction`), é somente leitura e não usa Helius nem endpoint pago. A coleta é retomável: pares de evidências já existentes são auditados e pulados; evidências parciais ou inválidas são preservadas e interrompem o fluxo. Consulte `docs/fixtures/ETAPA16-EXECUCAO-ANDROID.md`. A auditoria estrutural não substitui revisão semântica nem aprova fixture.
