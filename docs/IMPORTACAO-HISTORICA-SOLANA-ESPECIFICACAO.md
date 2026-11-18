# Especificação preliminar — importação histórica offline Solana

Data: 2026-11-18 (UTC)
Estado: especificação, não implementação
Branch: `feat/offline-fixture-inspector`
PR relacionado: #16

## 1. Objetivo e limites

Definir os requisitos mínimos para uma futura importação de transações RAW já coletadas, sem rede e sem executar operações on-chain. Esta especificação não autoriza criar SQLite, migrar schema, importar dados, avançar checkpoints ou iniciar monitoramento.

A primeira entrega funcional deverá ser apenas um **dry-run**, com relatório redigido e sem efeitos colaterais.

## 2. Entrada e identidade

Cada item de entrada deve conter:
- caminho para um manifesto RAW e seu arquivo bruto correspondente;
- manifesto válido segundo `audit_fixture()`;
- hash SHA-256 do payload bruto correspondente ao manifesto;
- assinatura e slot consistentes entre manifesto e payload;
- associação explícita da transação a uma carteira monitorada, fornecida por configuração/mapeamento externo e revisável pelo operador.

A associação não pode ser inferida do fee payer, primeiro signatário, posição em `accountKeys`, proprietário de token account ou qualquer heurística. Campo de carteira presente no manifesto é uma declaração, não prova independente de legitimidade. Divergência entre manifesto e mapeamento externo deve bloquear o item para revisão.

Não usar fixtures pseudonimizadas/anonimizadas como histórico real. Elas são material de teste.

## 3. Fases obrigatórias

1. **Descoberta:** enumerar pares de forma determinística; não seguir symlinks fora do diretório autorizado.
2. **Validação:** verificar manifesto, hash, assinatura, slot, status on-chain e estrutura RPC.
3. **Atribuição:** exigir mapeamento explícito por transação; sem ele, classificar como `WALLET_UNASSIGNED`.
4. **Classificação de cobertura:** detectar se há instruções de protocolos suportados; protocolo desconhecido/não suportado não pode ser declarado processado economicamente.
5. **Dry-run:** calcular o que seria arquivado/processado e colisões potenciais, sem abrir EventStore nem criar diretórios/arquivos.
6. **Importação futura (fora do escopo atual):** só após autorização explícita, com backup, política de colisão, transação atômica e relatório verificável.

## 4. Estados de resultado do dry-run

No mínimo:
- `READY_FOR_REVIEW`: integridade válida e carteira explicitamente associada; ainda não significa autorização para gravar.
- `WALLET_UNASSIGNED`: nenhuma associação explícita.
- `MANIFEST_INVALID` / `HASH_MISMATCH` / `SIGNATURE_MISMATCH` / `SLOT_MISMATCH`: falha de proveniência/integridade.
- `ON_CHAIN_FAILED`: execução on-chain falhou; preservar como observação, sem classificar swap positivo.
- `UNSUPPORTED_PROTOCOL`: protocolo fora da cobertura do processador disponível.
- `DUPLICATE_IDENTICAL`: identidade já existe com conteúdo/proveniência idênticos.
- `IDENTITY_COLLISION`: mesma chave lógica com conteúdo ou proveniência divergentes; bloquear, nunca sobrescrever silenciosamente.

Relatório deve conter contagens e razões, sem imprimir endereços, assinaturas, mints, URLs ou payload bruto.

## 5. Regras de persistência futura

- Não chamar RPC/Helius; usar somente arquivos locais validados.
- Não avançar `wallet_checkpoints` nem inserir `processed_signatures` durante importação histórica.
- Não chamar diretamente `process_raydium_cpmm_observation()` no modo atual: ele pode marcar transações falhadas ou sem swaps CPMM como processadas e avançar checkpoint.
- Não usar `SQLiteEventStore` no dry-run: seu construtor inicializa schema e pode criar banco.
- Não usar `save_observation()` sem política explícita de colisão: sua chave natural pode atualizar observação existente.
- Persistência futura deve separar arquivo bruto/observação, resultados de reconciliação e bundles; suportar replay idempotente e preservar tentativas negativas.
- Transações de venues não suportadas devem permanecer explicitamente não processadas/pendentes, nunca receber sucesso por passarem por um pipeline CPMM.
- Qualquer alteração de schema exige migração versionada, backup e autorização específica.

## 6. Critérios de aceite antes de qualquer gravação

- Testes de fixtures válidas, manifesto/hash/assinatura/slot divergentes, arquivo ausente, JSON inválido, carteira ausente/divergente, protocolo não suportado, duplicata idêntica e colisão.
- Teste de dry-run comprova ausência de criação/modificação de arquivos e ausência de abertura/criação de SQLite.
- Teste comprova que nenhum caminho, endereço, assinatura, mint, blockhash, URL ou segredo aparece no relatório.
- Mapeamento carteira↔transação é revisado explicitamente pelo operador.
- Plano de backup, rollback, idempotência e checkpoint aprovado.
- Autorização explícita do usuário para a etapa de persistência.

## 7. Evidência atual e bloqueios

- Inspeção local em 18/11/2026: cinco manifestos, cinco pares íntegros, zero inválidos; todos os payloads reportaram estado on-chain success.
- Os cinco manifestos não declaram `wallet_address` nem `monitored_wallet_address`.
- A presença de owners nos snapshots pre/post não identifica por si só a carteira monitorada.
- Não há banco SQLite localizado no Termux; nenhum banco foi criado.
- Não há importador offline implementado.
- Nenhum RAW local foi enviado ao GitHub.
- CI do commit documental anterior `01a410833650c022909f97c475b468631130b47e`: run `44249289181`, concluído com sucesso.

## 8. Próxima etapa técnica permitida

Implementar e testar somente um planejador/dry-run offline, sem SQLite e sem persistência. Antes disso, a política de associação deve aceitar mapeamento explícito por transação; quando o operador não fornecer a associação, o resultado deve ser `WALLET_UNASSIGNED`. Não presumir que as cinco transações pertencem a uma única carteira.


## 9. Implementação inicial do planejador (18/11/2026)

Foi adicionado `tools/plan_solana_historical_import.py` e sua suíte `tests/test_historical_import_planner.py`.

Comportamento implementado:
- Descoberta determinística de manifestos `*.manifest.json` no diretório fornecido.
- Reutiliza `audit_fixture()` para validar hash, assinatura, slot, commitment, encoding e marcador de não anonimizado.
- Rejeita manifesto/payload via symlink e caminhos resolvidos fora do diretório autorizado.
- Aceita mapeamento explícito local JSON no formato `{signature: monitored_wallet}`; não imprime os valores.
- Sem associação explícita: `WALLET_UNASSIGNED`.
- Divergência entre mapeamento e campo explícito do manifesto: `WALLET_MAPPING_CONFLICT`.
- Transação com `meta.err` não nulo: `ON_CHAIN_FAILED`.
- Associação explícita válida: `READY_FOR_REVIEW`, nunca autorização para gravar.
- Falhas de auditoria recebem estados de manifesto/hash/assinatura/slot.
- Saída limitada a índice e estado, sem caminhos, carteiras ou assinaturas.
- Declara `network_access=false`, `database_access=false`, `writes_files=false`, `checkpoint_changes=false` e `execution_authorized=false`.

Uso:
`PYTHONPATH=src python tools/plan_solana_historical_import.py /caminho/para/raw`
Opcionalmente:
`--wallet-map /caminho/privado/wallet-map.json`

O mapeamento deve permanecer local e não deve ser enviado ao GitHub. O planejador não detecta nem valida a cobertura de protocolos DEX; `READY_FOR_REVIEW` exige uma revisão posterior de protocolo e carteira. Nenhuma persistência foi implementada.

### Limites da implementação
- Ainda não há importação SQLite nem escrita de observações.
- Não há comparação com duplicatas já persistidas, pois não existe acesso ao banco neste dry-run.
- Não existe classificação automática de venue/protocolo neste planejador; essa revisão permanece pendente.
- O script não é autorização para importar os dados.


## 10. Validação CI do planejador (18/11/2026)

- Head funcional/documental validado: `0c493b51fc98f5453f5b3763b0aeee48631464a6`.
- Workflow `SMR tests`, run `44249986290`, concluído com sucesso.
- 255 testes unitários aprovados; compileall de `src` e `tests` aprovado.
- CI valida os testes do planejador, mas não substitui a execução local sobre os cinco RAW do usuário.
- Próxima validação: dry-run local sem mapa de carteiras; resultado esperado pela evidência atual é `WALLET_UNASSIGNED` para os cinco registros.


## 11. Auditoria offline de cobertura de programas (18/11/2026)

Foi adicionado `tools/audit_solana_protocol_coverage.py`, com testes em `tests/test_protocol_coverage_audit.py`.

- Revalida cada par RAW/manifesto antes de inspecionar instruções.
- Resolve `programId` direto ou `programIdIndex` contra `accountKeys` e endereços ALT carregados em payloads `json`.
- Conta instruções top-level e CPI por nome de programa presente no registro; IDs, endereços, assinaturas, caminhos e nomes de arquivos não são exibidos.
- Separa programas conhecidos no registro da cobertura estreita dos decoders existentes nesta branch.
- Cobertura estrutural explicitamente reconhecida: Raydium CPMM (`swap_base_input/output`), SPL Token e Token-2022 (`Transfer/TransferChecked`). Isso não significa suporte integral a todos os tipos de instrução desses programas.
- Programas registrados sem decoder de swap permanecem identificados como conhecidos, mas fora da cobertura de decoder; IDs não registrados são apenas contados.
- Rejeita symlinks antes de ler payload externo.
- Somente leitura: sem rede, SQLite, escrita de arquivos ou alteração de checkpoint.

Uso:
`PYTHONPATH=src python tools/audit_solana_protocol_coverage.py /caminho/para/raw`

A execução local nos cinco RAW ainda está pendente. Não confundir os cinco candidatos documentados com resultado de cobertura observado: o relatório local é necessário para saber quais programas aparecem efetivamente em cada transação.


### 12. CI da auditoria de cobertura

- Workflow `SMR tests`, run `44250502846` (#381), concluído com sucesso.
- 259 testes unitários aprovados; compileall aprovado.
- CI valida a lógica em fixtures sintéticas. A análise dos cinco arquivos RAW reais depende da execução local pelo usuário.


## 13. Resultado da auditoria de cobertura nos cinco RAW (18/11/2026)

A execução local de `tools/audit_solana_protocol_coverage.py` reportou cinco manifestos auditados, 60 instruções no total e nenhum program ID não resolvido. Foram reconhecidas 46 instruções de programas registrados e 14 de programas fora do registro atual.

| Programa registrado | Contagem de instruções |
|---|---:|
| SPL Token | 22 |
| System Program | 9 |
| Associated Token Account | 4 |
| Meteora DAMM v2 | 4 |
| Jupiter Aggregator v6 | 2 |
| Meteora DLMM | 2 |
| Token-2022 | 1 |
| Raydium AMM v4 | 1 |
| Raydium CPMM | 1 |

Ocorrência por payload:
- Índice 1: Meteora DAMM v2, Token-2022, SPL Token, System Program e Associated Token Account.
- Índice 2: Raydium AMM v4 e SPL Token.
- Índice 3: Jupiter v6, Meteora DAMM v2, SPL Token, System Program e Associated Token Account.
- Índice 4: Meteora DLMM e SPL Token.
- Índice 5: Raydium CPMM, SPL Token e System Program.

O decoder contabilizado nesta branch cobre somente 22 instruções SPL Token, uma Token-2022 e uma Raydium CPMM. Registro de programa não implica decoder. Contagens de instruções não são contagens de swaps: agregadores, CPI e transferências auxiliares exigem reconstrução econômica por operação.

A auditoria não acessou rede ou banco, não escreveu arquivos e não alterou checkpoints. Os RAW continuam apenas no dispositivo local. A sequência de desenvolvimento proposta é DAMM v2, AMM v4, DLMM e, separadamente, Jupiter como roteador; a ordem é uma priorização de engenharia, não inferência de volume ou relevância financeira.


## 14. Fingerprints redigidos para especificação de decoders

A auditoria de cobertura também produz venue_instruction_profiles para programas registrados como venue e para Jupiter v6 como agregador. O perfil agrupa:
- nome do programa (sem Program ID);
- origem top_level ou inner;
- primeiros oito bytes dos dados da instrução, em hexadecimal;
- comprimento total dos dados;
- quantidade de contas da instrução;
- stack height quando presente;
- número de ocorrências com o mesmo perfil.

Os bytes após o prefixo, os índices e endereços das contas, valores, assinaturas e caminhos não são exibidos. O prefixo é uma impressão digital estrutural, não prova semântica de BUY/SELL nem substitui a validação contra IDL/documentação oficial. A quantidade de contas não identifica por si só o papel de cada conta.

Após CI, executar novamente localmente nos RAW originais. Compartilhar somente o relatório redigido; não copiar payload bruto ou mapa de aliases para o chat/GitHub.


### 15. CI dos fingerprints

O CI run 44251053718 (#393), para o commit funcional ab6a09522d4347f53e474082188cd926e90872a3, concluiu com sucesso: 259 testes unitários e compileall aprovados.


## 15. Resultado dos fingerprints e validação documental inicial de DAMM v2 (18/11/2026)

A execução local no clone PR16 atualizado até `65c03c8c423302a89c09ea6a4de29b78396c3c1d` auditou novamente os cinco manifestos: cinco auditados, zero inválidos e zero programas não resolvidos. O auditor confirmou ausência de rede, banco, gravação e alteração de checkpoints.

### Perfis observados

| Programa/localização | Prefixo | Comprimento | Contas | Stack height | Ocorrências |
|---|---|---:|---:|---:|---:|
| DAMM v2 / top-level | `f8c69e91e17587c8` | 24 | 14 | 1 e 2 | 2 |
| DAMM v2 / inner | `e445a52e51cb9a1d` | 196 | 1 | 2 e 3 | 2 |

O prefixo top-level é igual aos primeiros oito bytes de SHA-256 de `global:swap`, discriminador Anchor da instrução `swap`. A documentação Meteora lista `swap` como caminho legacy exact-in e `swap2` como caminho atual que aceita ExactIn, PartialFill e ExactOut. O discriminador Anchor de `global:swap2` é `414b3f4ceb5b5b88`, não observado nos perfis top-level recebidos.

A documentação e o código-fonte oficiais esclarecem a estrutura: p_emit_cpi() prefixa Event::data(&EvtSwap2 { ... }) com EVENT_IX_TAG_LE. Assim, e445a52e51cb9a1d é o wrapper Event CPI; o discriminador Anchor do evento EvtSwap2 (bd4233a826507599) deve estar nos bytes 8–15. O tamanho observado de 196 bytes corresponde a 8 bytes de wrapper + 8 bytes de discriminador + 180 bytes de payload. A confirmação nos RAW depende da leitura redigida dos bytes 8–15.

O prefixo `e445...` também aparece sob programas Jupiter v6 e Meteora DLMM e com outros comprimentos. A coincidência não demonstra semântica comum, porque o programa, o contexto CPI e a estrutura completa são parte da identidade da instrução.

### Requisitos para o decoder DAMM v2

1. Fixar a versão/commit do IDL oficial correspondente ao programa mainnet no período das transações; registrar proveniência e hash do IDL.
2. Confirmar layout de `swap` e `swap2`, discriminadores, argumentos, enum de modo e ordem/semântica das contas antes de implementar parser.
3. Identificar o payload inner `e445...` a partir do IDL e da origem do CPI; até lá classificá-lo como `UNRESOLVED`.
4. Separar instrução de execução, event CPI e transferências Token/SPL/Token-2022; nunca contar os três como swaps separados.
5. Reconstruir input/output por operação e reconciliar deltas das token accounts/vaults, considerando transfer fees e taxas do protocolo.
6. Criar fixtures sintéticas redigidas e testes positivos/negativos para instrução top-level, CPI, evento, swap2, modos, Token-2022, dados truncados, identidade CPI e múltiplos swaps.
7. Só produzir `SwapObservation` após reconciliação econômica; manter dados insuficientes como `INCOMPLETE` e direção sem mint de referência como `UNKNOWN`.

A evidência atual confirma chamada top-level compatível com `swap` legacy, mas não prova por si só a operação econômica completa nem direção BUY/SELL. Não há decoder DAMM v2 implementado nesta etapa. Nenhum RAW foi enviado ao GitHub; não houve acesso a SQLite, importação, RPC, Helius, checkpoint ou execução on-chain.

## 16. Event CPI e EvtSwap2 DAMM v2: especificação e auditor redigido (18/11/2026)

Fonte oficial fixada para esta análise: MeteoraAg/damm-v2 commit 18936b18c26708f6e9b52cacc01ea2f99868ba8e.

O código oficial em programs/cp-amm/src/instructions/swap/ix_p_swap.rs executa a lógica do swap e emite EvtSwap2 por p_emit_cpi(Event::data(&EvtSwap2 { ... }), event_authority). A função p_emit_cpi prefixa o conteúdo com EVENT_IX_TAG_LE, depois faz CPI ao próprio programa. O wrapper é e445a52e51cb9a1d; os oito bytes seguintes são o discriminador Anchor do evento. Para EvtSwap2, o discriminador é bd4233a826507599.

O layout do evento tem 188 bytes (8 do discriminador + 180 do payload). O CPI completo tem 196 bytes (8 wrapper + 188 evento). Isso coincide com o perfil inner DAMM v2 observado localmente: 196 bytes, uma conta de autoridade, stack height 2 ou 3. A coincidência é estruturalmente forte, mas a confirmação transacional exige verificar o discriminador no offset 8 do payload RAW.

O evento contém direção e parâmetros, SwapResult2, fees, timestamp e reservas. SwapParameters2 usa amount_0, amount_1 e swap_mode (0 ExactIn, 1 PartialFill, 2 ExactOut). Para ExactOut, amount_0 é output desejado e amount_1 é input máximo; não interpretar os campos como sempre input/minimum output.

### Extensão implementada no auditor

O auditor passa a emitir event_cpi_profiles para instruções internas de venues/agregadores registradas cujo payload começa pelo wrapper Event CPI. Exibe apenas nome do programa, discriminador de evento, tamanho, quantidade de contas, stack height, nome allowlisted quando conhecido e contagem. Reconhece EvtSwap2 somente para Meteora DAMM v2 + discriminador exato; outros eventos são UNKNOWN. Nenhum payload, endereço, mint, valor, carteira, assinatura, ID de programa ou caminho é exibido.

Teste sintético valida wrapper, discriminador, 196 bytes, uma conta, stack height e redação. O código continua sem rede, SQLite, gravação ou checkpoint. O novo head ainda não tem CI/status check confirmado.

### Critérios de validação local

- Atualizar clone PR16 por fast-forward e executar tools/audit_solana_protocol_coverage.py nos cinco RAW originais.
- Confirmar se DAMM v2 inner aparece com discriminador bd4233a826507599, event_name=EvtSwap2, comprimento 196 e uma conta.
- Se confirmado, associar o Event CPI à instrução swap correspondente por stack height/ordem/contexto CPI; nunca contabilizar evento e instrução como dois swaps.
- Decodificar campos do evento somente após fixar a versão de IDL/estrutura; reconciliar transferências SPL/Token-2022 e deltas de token accounts/vaults. Não criar SwapObservation apenas a partir do evento.

Nenhum RAW foi enviado ao GitHub; nenhuma importação, banco, RPC/Helius, checkpoint ou operação on-chain foi realizada.
