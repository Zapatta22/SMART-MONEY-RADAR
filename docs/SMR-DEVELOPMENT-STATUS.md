# Estado de desenvolvimento do Smart Money Radar

Auditoria de 19/11/2026. A referência de integração é a `main` em `5060bc6`. O histórico de PRs abaixo distingue merges em branches intermediárias de integração na `main`.

## Critérios de conclusão

Os percentuais medem três marcos binários de aceitação por módulo, de peso igual. **I** exige o escopo do módulo integrado à `main` pelo caminho normal de uso. **T** exige teste automatizado do módulo completo contra seus critérios abaixo. **O** exige validação operacional com evidência reproduzível. A medição global dá peso igual aos nove módulos enquanto não houver pesos aprovados. O resultado de **0/27 marcos (0%)** indica que nenhum módulo completo cruzou esses gates. Os componentes implementados e exercitados constam na tabela.

| Módulo | I/T/O | Marcos | Evidência disponível | Critério para fechar o módulo |
|---|---|---:|---|---|
| A. Infraestrutura e persistência | 0/0/0 | 0% | Na main há SQLite, checkpoints, backup/replay e CI. A PR #4 inclui persistência de swaps, com revisão de concorrência nesta etapa. | Integrar migração e persistência no caminho normal. Validar atualização a partir de banco anterior, recuperação e observabilidade estruturada. |
| B. Monitoramento Solana | 0/0/0 | 0% | Na main há RPC e WebSocket para monitoramento e coleta. As branches Geyser contêm adaptadores, RAW, timeline e testes locais. | Validar receptor, sequência compartilhada, persistência, reconexão, lacunas, duplicatas e replay com eventos do provider. |
| C. Interpretação econômica | 0/0/0 | 0% | Na main há contratos de swap e parser conservador. As branches CPMM/DAMM v2 têm decodificadores, reconciliação e fixtures. | Integrar CPI, CPMM, DAMM v2, Token-2022 e wSOL. Validar evidência de BUY/SELL e rejeição da ambiguidade. |
| D. Launch Radar | 0/0/0 | 0% | Catálogo de programas na main. | Integrar detecção de mints e pools, liquidez, permissões, concentração, volume, preço e sinais de fraude. |
| E. Smart Money Radar | 0/0/0 | 0% | Monitor de carteiras na main. | Validar histórico, acumulação, atividade coordenada e classificação de sinais com evidência. |
| F. Motor de decisão | 0/0/0 | 0% | Contratos de observação e classificação na main. | Testar entrada imediata e confirmação por preço/volume com os mesmos bloqueios. Demonstrar pontuação, exposição, slippage, deduplicação, kill switch e saídas. |
| G. Simulação | 0/0/0 | 0% | Há replay de ingestão na main. | Validar paper trading, custos, backtest sem dados futuros, comparação dos modos, drawdown e latência. |
| H. Interface | 0/0/0 | 0% | Serviço de dashboard somente leitura e testes em branches avançadas. | Integrar e testar em desktop e celular monitoramento, configurações, modos, sinais, alertas e relatórios. |
| I. Preparação operacional | 0/0/0 | 0% | CI, configuração local e documentação de coleta e execução Android. | Exercitar implantação, segredos, disponibilidade, recuperação, integração, carga e checklist de segurança. |

## Dependências verificadas no Git

- A PR #4 está aberta contra `main`. A correção SQLite desta etapa parte dela. A PR #5 também parte de `main`. A pilha CPMM passa por #6–#8 e pelos merges em branches intermediárias #9, #10 e #12–#16. A persistência usada nessa pilha chegou pelo merge da #14 e terá de ser reconciliada com a revisão da #4.
- A PR #23 foi mesclada em `feat/damm-v2-referral-transfer-attribution` e sua branch de origem inclui o trabalho das PRs #34–#36. A trilha de adaptação e pipeline DAMM v2 continua nas PRs abertas #24 e #25.
- A PR #26 está aberta contra `feat/damm-v2-economic-reconciliation`. O histórico de #26 já contém #27 (rebuild com memória limitada) e #28 (elegibilidade de entregas) por meio da #30. A PR #29 segue aberta, mas sua árvore difere da #26 apenas nos registros e na documentação da política RAW. Conferir o delta residual antes de promover.
- A PR #31 trata sequências anômalas e a #33, conflitos de linhagem. Ambas apontam para `feat/damm-v2-economic-reconciliation`. A #32 exclui sequências historicamente comprometidas e aponta para a branch da #26. Os três heads estão fora da história da #39.
- A PR #39 está em Draft sobre `feat/token2022-transfer-checked-with-fee`; sua história já alcança `main` e `d08c146` (#23). A suíte offline da #39 tem 617 testes. Os campos de fonte, stream, domínio e sequência são declarados pelo chamador. A correção de proveniência verifica conteúdo protobuf, enquanto autenticação da origem e continuidade exigem o receptor compartilhado. Índice da transação no bloco e sequência de transporte têm finalidades distintas. A presença de meta, inclusive protobuf vazio, significa presença do campo. A evidência para classificação requer verificações adicionais.
- A revisão do Yellowstone parte da #39 e verifica a correspondência dos bytes com a mensagem protobuf no nível correto. Seguem pendentes a integração com conta e slot, o armazenamento desses frames no RAW e os testes com captura do provider.

## Verificações executadas localmente

| Referência | Evidência |
|---|---|
| `main@5060bc6` | 98 testes aprovados. |
| `817069c` + correção SQLite `0a13a77` | 109 testes aprovados, incluindo concorrência, colisão entre carteiras e rollback. `compileall` e `git diff --check` aprovados. |
| `51ea578` (PR #39) | 617 testes aprovados. |
| Correção Yellowstone sobre `51ea578` | 617 testes aprovados. `compileall` e `git diff --check` aprovados. Os testes protobuf são offline. |

Validação operacional pendente para as duas revisões. Permanecem pendentes a migração e o replay pelo pipeline integrado, a captura de eventos Yellowstone, testes de recuperação ponta a ponta, carga e implantação.

## Próxima tarefa prioritária

Reconciliar a correção SQLite com o pipeline CPMM da PR #14 em branch isolada. Exercitar a abertura de um banco criado pela main, a gravação e o replay de uma fixture auditada e o rollback forçado sem avanço de checkpoint.

Em seguida, compor #26, #31, #32 e #33 em cima da revisão de #39 em uma branch de integração. Cobrir identidade de fonte e domínio, frames divergentes, evento de conta e transação no mesmo domínio, gaps, replay e reconexão, antes de habilitar o receptor. A primeira rodada pode usar fixtures e uma simulação de transporte.

## Retomada

A branch `codex/smr-sqlite-readiness` parte de `817069c` (#4). A correção SQLite está em `0a13a77`. A branch `codex/smr-yellowstone-wire-integrity` parte de `51ea578` (#39). Use o SHA exibido no resumo do GitHub Actions para vincular a validação ao commit. Inicie a retomada pelo critério da seção anterior, com ambas as branches e suas bases identificadas.

Para reproduzir localmente:

```sh
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -q
python -m compileall -q src tests
git diff --check
```

O workflow SMR tests executa verificações de código no push, em PRs direcionadas às bases cobertas ou por disparo manual no ref selecionado. Ele registra o SHA, os resultados e a tarefa prioritária no resumo do GitHub. Cada job tem limite de 10 minutos. Para o mesmo ref e tipo de evento, uma execução nova cancela a anterior, com uma tentativa por disparo e sem retry automático. Falha de instalação, testes ou compilação bloqueia a promoção da etapa. A proteção de branch depende da configuração do repositório.

A ação oficial `openai/codex-action` inicia Codex CLI via API e depende de credencial e orçamento. A sessão atual não confirmou uma integração autorizada para disparar novas sessões do Codex Cloud. A retomada do agente permanece manual. O workflow usa runner padrão e não provisiona serviços pagos nem agenda consumo recorrente. [Documentação da Codex GitHub Action](https://github.com/openai/codex-action)

Execução financeira real permanece desabilitada. Antes de qualquer alteração desse limite, são necessárias autorização específica e validação operacional independente.
