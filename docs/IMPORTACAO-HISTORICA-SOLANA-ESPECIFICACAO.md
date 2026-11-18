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
