# Plano de integração Raydium e reconciliação de swaps — SMR

**Estado:** planejamento técnico; não implementado.  
**Branch de trabalho:** `feat/raydium-swap-reconciliation`  
**Escopo:** Solana V1, observação e análise somente leitura.

## 1. Objetivo

Integrar os decodificadores Raydium CPMM e AMM v4 existentes na cópia local ao pipeline remoto, reconstruindo operações de swap a partir de instruções externas, inner instructions/CPI e variações de saldo. Persistir separadamente observação econômica, classificação semântica e evidências técnicas.

Este documento não declara que os módulos locais foram revisados, portados ou validados. Seus conteúdos ainda precisam ser transferidos e comparados antes de qualquer integração de runtime.

## 2. Estado remoto verificado

- `domain/models.py` contém `SwapObservation`, `SwapClassification`, `SwapEvidence` e `build_swap_operation_id`.
- `domain/normalization.py` atualmente normaliza o envelope da transação, eventos legados e deltas de tokens SPL; não integra analisadores Raydium.
- `storage/event_store.py` já persiste payload bruto, eventos legados, metadados da transação, deltas SPL, assinaturas processadas e checkpoints.
- `save_observation()` grava os dados atuais em uma transação SQLite; `reprocess_observation()` permite substituir derivados sem alterar o checkpoint.
- O armazenamento ainda não tem tabelas dedicadas aos três contratos de swap.

## 3. Princípios obrigatórios

1. **Não inferir swap a partir de transferência isolada.** A reconstrução deve correlacionar instruções, CPI, contas e deltas.
2. **Separação de responsabilidades.** Observação econômica, classificação e evidência são registros distintos ligados por `operation_id`.
3. **Conservadorismo.** Classificação `UNKNOWN` quando a evidência for incompleta, conflitante ou ambígua; confiança não substitui evidência.
4. **Venue efetiva.** Registrar o programa/instrução que executou a troca, sem confundir roteador/agregador com DEX subjacente.
5. **Rastreabilidade.** Preservar índice externo, caminho CPI, programa, contas relevantes, versão do parser e origem dos dados.
6. **Idempotência.** Reprocessar a mesma assinatura não deve duplicar operações.
7. **Atomicidade.** Não deixar observação sem classificação/evidência correspondente quando a operação for considerada persistível.
8. **Compatibilidade.** Manter eventos legados, envelopes e deltas SPL existentes.
9. **Somente leitura.** Sem assinatura, envio de transações ou ordens de compra/venda.
10. **Custos controlados.** Nenhum RPC pago, Helius, VPS ou serviço externo pago sem autorização explícita.

## 4. Fluxo proposto

1. Receber payload RPC bruto e preservar sua proveniência.
2. Normalizar envelope, status on-chain e deltas SPL existentes.
3. Percorrer instruções externas e inner instructions, preservando índices e relação pai/filho (CPI).
4. Identificar programas conhecidos via registro de programas; encaminhar instruções Raydium aos decodificadores específicos após revisão dos módulos locais.
5. Interpretar contas/ativos/quantidades e reconciliar os resultados com deltas de saldo da carteira.
6. Produzir zero ou mais `SwapObservation` para a transação. Cada operação deve ter identidade determinística baseada em chain, assinatura, índice e caminho CPI.
7. Produzir `SwapEvidence` com programa, venue efetiva quando comprovada, índice, caminho CPI e evidências concretas.
8. Classificar BUY/SELL somente quando a relação entre ativo de referência e ativo adquirido/vendido estiver definida pela regra de domínio. Caso contrário, `UNKNOWN` com motivo explícito.
9. Persistir derivados de forma atômica com a observação já existente.
10. Permitir replay do payload bruto após atualização de parser, preservando versão e trilha de auditoria.

## 5. Persistência proposta

Adicionar tabelas específicas, com esquema final definido após revisão dos contratos e padrões atuais de migração:

- `swap_observations`: uma linha por `operation_id`; campos para chain, carteira, assinatura, mints, quantidades, timestamp e versão do parser.
- `swap_classifications`: classificação, confiança e motivo por `operation_id`.
- `swap_evidence`: programa, venue, índice da instrução, caminho CPI e evidências por `operation_id`.

Restrições recomendadas:
- chave primária em `operation_id` para observações;
- chave estrangeira de classificação/evidência para observação;
- índices por carteira/tempo, assinatura e mint;
- quantidades e confiança armazenadas como texto decimal, sem conversão para float;
- caminho CPI/evidências serializados em JSON determinístico;
- substituição dos derivados de uma assinatura dentro da mesma transação SQLite no replay, sem avançar ou retroceder indevidamente o checkpoint.

A cardinalidade de evidências (uma ou várias por operação) deve ser confirmada durante a implementação. Não fixar uma restrição de unicidade que descarte proveniência legítima.

## 6. Revisão dos módulos locais antes do porte

Arquivos identificados na cópia Termux, ainda não transferidos/revisados:

- `raydium_cpmm_decoder.py`
- `raydium_cpmm_accounts.py`
- `raydium_cpmm_analyzer.py`
- `raydium_amm_v4_decoder.py`
- `raydium_amm_v4_accounts.py`
- `raydium_amm_v4_analyzer.py`
- `solana_token_instruction_decoder.py`
- `dex_interpreter.py`
- `transaction_parser.py`
- `domain/normalization.py` local (diverge da versão remota)

Testes locais identificados incluem decodificadores, semântica de contas, analisadores, integração do parser Raydium e normalização. Os arquivos de teste devem ser transferidos junto com seus módulos. Não copiar `__pycache__` ou arquivos `.pyc`.

A versão local de `models.py` não deve substituir a remota: a versão remota já contém os contratos aprovados no PR #1. Qualquer diferença local deve ser revisada como diff e aplicada seletivamente.

## 7. Fixtures e critérios de evidência

Antes de declarar suporte validado:
- localizar as fixtures brutas e anonimizadas referenciadas pelos testes;
- confirmar que cada fixture veio de transação real e manter assinatura/proveniência auditável em registro apropriado;
- anonimizar dados pessoais/sensíveis sem alterar os campos técnicos necessários;
- não classificar dados sintéticos como reais;
- incluir casos CPMM, AMM v4, roteamento/CPI, múltiplas operações numa transação, transação falha, ausência de metadados e sinais conflitantes;
- incluir casos negativos em que a saída correta é zero swaps ou classificação `UNKNOWN`.

Se uma fixture não puder ser comprovada, rotulá-la como sintética ou não verificada e não usá-la como evidência de validação real.

## 8. Plano de testes

1. Testes unitários de decodificação de instrução e contas por programa.
2. Testes de árvore de instruções externas/CPI e preservação dos índices/caminhos.
3. Testes de reconciliação entre instruções e deltas SPL/SOL.
4. Testes de identidade determinística e distinção de operações na mesma transação.
5. Testes de classificação BUY/SELL/UNKNOWN, incluindo ambiguidade e confiança.
6. Testes de persistência, chaves estrangeiras, atomicidade, deduplicação e replay.
7. Regressão de toda a suíte existente (incluindo parser, normalização e EventStore).
8. `compileall` e CI no GitHub Actions.

Nenhuma aprovação deve ser inferida apenas da existência dos testes. Registrar os comandos executados, resultado e commit exato.

## 9. Sequência de implementação

- **Fase A — transferência e revisão:** receber os módulos/testes locais, comparar cada arquivo com o remoto e resolver dependências sem sobrescrever código aprovado.
- **Fase B — adaptadores:** integrar decodificadores Raydium ao parser/normalizador por interfaces pequenas e testáveis.
- **Fase C — reconciliação:** construir operações a partir de instruções/CPI e reconciliar com deltas, com saída conservadora.
- **Fase D — persistência:** adicionar tabelas e métodos atômicos ao EventStore, com migração incremental e replay idempotente.
- **Fase E — validação:** executar testes unitários, fixtures verificadas, regressão e CI; registrar evidências.
- **Fase F — revisão:** abrir PR para revisão; não mesclar automaticamente.

## 10. Critério de conclusão desta integração

A integração só será considerada concluída quando:
- módulos e testes tiverem sido revisados e incorporados;
- fixtures e sua proveniência estiverem classificadas;
- operações, classificação e evidências forem reconstruídas sem inferências indevidas;
- persistência/replay forem atômicos e idempotentes;
- suíte completa e CI passarem no commit submetido;
- PR for revisado e aprovado.

Até lá, o estado correto é **planejado / parcialmente disponível em código local não revisado**, não produção.

## 11. Limites operacionais

O SMR V1 continua restrito à observação e análise de dados públicos da Solana. Este plano não autoriza execução financeira, gerenciamento de chaves, assinatura ou envio de transações, nem contratação de infraestrutura paga.
