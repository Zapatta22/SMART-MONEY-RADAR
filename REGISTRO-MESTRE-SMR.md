# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-17 — PR #1 validado e integrado à main

## 1. Estado executivo

Fase atual: preparação e validação de fixtures Solana reais para decodificadores por programa.
Prioridade V1: Solana; arquitetura extensível sem implementar multichain agora.
Estado real: monitor/coletor somente leitura, ingestão e persistência normalizadas, catálogo de programas, coletor RPC de fixtures, auditor offline e anonimizador de projeções implementados na cópia local de auditoria. O SMR completo não está integrado, em produção ou operando 24/7.

## 2. Continuidade e base

Base de entrada: `SMR-CODIGO-BASE-ETAPA12-2026-11-16.zip`, preservada e extraída para esta etapa. A suíte de referência registrada na Etapa 12 era 76/76. O pacote Etapa 13 contém as alterações desta etapa e passou em 86/86 testes.

## 3. Etapas consolidadas

- Etapas 1–6: robustez monitor/Helius, backfill, retries, shutdown, parser conservador, payload bruto/replay, integridade/backup e inventário.
- Etapa 7: contratos de domínio mínimos.
- Etapa 8: normalizador de transação.
- Etapa 9: integração do normalizador no WalletMonitor e persistência atômica no EventStore.
- Etapa 10: matriz de 15 programas Solana, classificação e cinco assinaturas públicas candidatas.
- Etapa 11: coletor JSON-RPC HTTPS somente leitura para `getTransaction` finalized, manifesto, SHA-256 e proteção contra sobrescrita.
- Etapa 12: auditor offline de evidências, integridade, manifesto, SHA-256, assinatura e slot.
- Etapa 13: anonimizador de projeção com mapa reversível separado e confidencial.

## 4. Entregas da Etapa 13

Arquivos novos:
- `src/smart_money_radar/data_sources/fixture_anonymizer.py`
- `tools/anonymize_solana_fixture.py`
- `tests/test_fixture_anonymizer.py`
- `docs/fixtures/ETAPA13-ANONIMIZADOR.md`

Arquivos atualizados:
- `README.md`
- `docs/fixtures/ETAPA10-MATRIZ-PROGRAMAS-E-FIXTURES.md` (alinhado `encoding=json` com o coletor Etapa 11 e resolução por account keys/loaded addresses).

## 5. Política técnica de anonimização

- O payload bruto original é somente lido; não é reescrito nem substituído.
- O bruto e a projeção têm SHA-256 independentes.
- Signers/fee payer são reconhecidos pelo `header.numRequiredSignatures` e também pelo `signer` de respostas `jsonParsed`.
- `owner` dos saldos SPL e token accounts indicadas por `accountIndex` são pseudonimizados.
- Program IDs explícitos e os resolvidos por `programIdIndex` (incluindo inner instructions e `meta.loadedAddresses`) são preservados.
- Mints são preservados automaticamente; pools, vaults e outras contas de protocolo devem ser identificadas e passadas por `--protect`. Outros endereços pessoais (ex.: destinatário SOL fora dos saldos SPL) devem ser revisados e passados por `--anonymize`; `--protect` tem precedência.
- Alias Base58 determinístico de 32 bytes é derivado com HMAC-SHA256 usando segredo local não persistido. Mesma chave/endereço gera o mesmo alias.
- Substituição em strings/logs ocorre por igualdade exata ou token Base58 completo; não há substituição por substring.
- Mapa reversível é gravado em arquivo separado com modo `0600`, fora da pasta de fixtures. O segredo não é salvo e o mapa não deve ser distribuído/commitado.
- Projeção, manifesto e mapa não sobrescrevem arquivos existentes. Manifesto de origem é auditado contra bruto, assinatura, slot e SHA-256 antes da transformação.

## 6. Validação

- Suíte completa: **86 testes aprovados, 0 falhas**.
- `PYTHONPATH=src python -m compileall -q src tests`: aprovado.
- Os dez testes novos cobrem preservação byte a byte do bruto, anonimização de signer/fee payer, owner e token account, preservação de program IDs/mints/pools, logs, aliases estáveis, proteção explícita, loaded addresses/CPI, manifesto de origem, caminhos, segredo curto e sobrescrita.
- Testes locais/offline; nenhuma chamada RPC, Helius ou consumo de créditos.
- Payloads usados nos testes são construídos para testar o anonimizador; não são fixtures mainnet.

## 7. Limites e estado de evidência

- A conectividade DNS/RPC do runtime segue bloqueando coleta real. As cinco assinaturas documentadas continuam candidatas, não fixtures aprovadas.
- O anonimizador não faz decodificação semântica e não aprova transação.
- A lista de pools/vaults/contas de protocolo a preservar exige revisão por transação; não se deve anonimizar toda conta não-signatária.
- A cópia atual ainda não está sincronizada ao Replit, celular ou VPS.
- Nenhum decodificador de swap/launchpad/AMM foi aprovado com fixture real.

## 8. Restrições preservadas

- Solana V1; sem multichain nesta fase.
- Somente leitura; sem assinatura/envio de transações ou trades reais.
- Sem endpoints pagos, créditos Helius ou VPS sem autorização explícita.
- Não rotular payload sintético, resumo de explorer ou teste do anonimizador como fixture mainnet real.
- Launch Radar, Market Radar, Decision/Risk/Portfolio e execução financeira não entram nesta etapa.

## 9. Próxima tarefa exata

Antes de alterar o parser, reconciliar a cópia local do Termux com o repositório remoto. O caminho local `~/SMART-MONEY-RADAR-ETAPA16` foi identificado como diretório sem metadados Git; portanto, não executar `git pull`, não inicializar Git nessa pasta e não sobrescrever arquivos. A árvore atual da `main` remota contém `transaction_parser.py`, `domain/normalization.py` e `storage/event_store.py`, mas não contém os decodificadores Raydium CPMM/AMM v4 mencionados no trabalho local. A cópia local registrou esses decodificadores e regressão 25/25, ainda sem integração Git comprovada. A próxima ação é comparar e transportar com segurança esses arquivos e testes para uma branch baseada na `main` atual, preservando a cópia local e sem duplicar testes já aprovados.

Depois da reconciliação, implementar a reconstrução econômica em camada separada: associar instruções externas/CPI, deltas de saldo e contas/venues; gerar `SwapObservation`, `SwapClassification` e `SwapEvidence` sem inferir BUY/SELL quando houver ambiguidade; persistir os três registros de forma atômica no SQLite. Criar fixtures de transações reais anonimizadas e testes de regressão antes de avançar para Smart Money Intelligence e Risk Manager.

## 10. Protocolo de continuidade

Usar este registro, `REGISTRO-MESTRE-SMR-ATUALIZADO-2026-11-16-ETAPA16.md` e a `main` remota após o merge do PR #1 como referências atuais. Separar especificado, implementado, testado, validado remotamente e produção. Não declarar coleta/fixture real concluída até existir payload RPC integral finalized, hash conferido, proveniência e revisão semântica.


## 11. Atualização 2026-11-17 — PR #1

- Repositório: `Zapatta22/SMART-MONEY-RADAR`.
- PR #1: [Implement separated swap domain contracts](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/1).
- Branch de origem: `feat/swap-domain-contracts`; destino: `main`.
- Validação: workflow GitHub Actions `SMR tests` concluído com sucesso; etapas de instalação, suíte `unittest` e `compileall` aprovadas. PR sem conflitos e sem comentários/revisões pendentes.
- Merge concluído em 2026-11-17 21:21:44 (horário local UTC-4). Merge commit: `8e20bbdeeb2e7cdb1d785539c9b6504f47ed59e0`.
- Confirmação remota: PR fechado como merged e `main` aponta para o mesmo SHA.
- Arquivos integrados: `src/smart_money_radar/domain/models.py`, `tests/test_domain_models.py`, `docs/SWAP-DOMAIN-CONTRACTS.md`, `.github/workflows/smr-tests.yml`.
- Contratos agora existentes na `main`: `SwapObservation`, `SwapClassification`, `SwapEvidence` e `build_swap_operation_id()`.
- Limite: o PR não conectou parser/decodificadores, não alterou persistência SQLite e não habilitou execução de ordens. A integração econômica continua pendente.

## 12. Estado atual confirmado e limites

- A `main` remota está atualizada com o merge commit acima.
- Na árvore remota consultada após o merge existem `transaction_parser.py`, `domain/normalization.py` e `storage/event_store.py`; não foram encontrados arquivos de decodificadores Raydium CPMM/AMM v4 nessa árvore.
- O histórico local do Termux registra decodificador CPMM, mapeamento de contas e testes conjuntos CPMM/normalização/AMM v4 aprovados em 25/25. A pasta local informada não é um repositório Git; esses arquivos ainda precisam ser reconciliados com a `main` sem perda.
- Nenhuma integração parser→reconstrução econômica foi iniciada nesta etapa.
- O SMR permanece em monitoramento/análise somente leitura, sem execução de compras ou vendas reais.


## 13. Atualização 2026-11-18 — reconciliação da cópia local e branch de trabalho

- Branch criada a partir da `main`: `feat/raydium-swap-reconciliation`. No momento da criação, comparação confirmou zero commits de diferença em relação à `main` (base `c87ef7005e1dc0b70336986df54da58b208b0aba`). Nenhum código foi ainda adicionado à branch.
- Inventário Termux em `~/SMART-MONEY-RADAR-ETAPA16` encontrou seis módulos locais: `raydium_cpmm_decoder.py`, `raydium_cpmm_accounts.py`, `raydium_cpmm_analyzer.py`, `raydium_amm_v4_decoder.py`, `raydium_amm_v4_accounts.py`, `raydium_amm_v4_analyzer.py`; também `domain/normalization.py` com imports desses dois analisadores, `solana_token_instruction_decoder.py`, `dex_interpreter.py`, `transaction_parser.py`, `domain/models.py` e `domain/program_registry.py`.
- Testes locais identificados: `test_raydium_amm_v4_decoder.py`, `test_raydium_parser_integration.py`, `test_raydium_account_semantics.py`, `test_raydium_account_decoder.py`, `test_raydium_analyzer.py`, `test_raydium_cpmm_analyzer.py` e `test_normalization.py`.
- Inventário local encontrou referências de testes a `tests/data/fixtures/raw` e `tests/data/fixtures/anonymized`, mas ambos os diretórios estavam ausentes no caminho esperado. A busca posterior por `*.raw.json`, `*.anon.json` e diretórios com nome fixture ainda não foi executada.
- Verificação remota confirma que a `main` tem `domain/normalization.py` sem imports Raydium e que não contém os módulos Raydium. Portanto, a normalização local é uma versão modificada que exige comparação cuidadosa; não substituir a versão remota nem `domain/models.py` (que contém os contratos do PR #1) sem revisão de diff.
- Documentos remotos das Etapas 10/11 confirmam que as cinco assinaturas listadas são candidatas, não fixtures reais aprovadas; nenhuma coleta RPC real foi comprovada. Testes sintéticos não devem ser apresentados como evidência mainnet.
- O SQLite remoto `event_store.py` já persiste observações normalizadas, eventos legados e `token_balance_deltas`, com replay/transação atômica; ainda não há persistência específica dos três contratos de swap.
- Fluxo de trabalho reafirmado: GitHub + Codespaces + ChatGPT como fluxo principal; Termux é cópia local preservada e fonte de arquivos ainda não enviados. Não executar `git pull`, inicializar Git na pasta local, nem modificar ou apagar originais.
- Próxima ação: trazer os arquivos locais necessários para revisão no GitHub/Codespaces, começando pelos seis módulos Raydium e testes, depois dependências estritamente necessárias. Fixtures brutas/anônimas só devem ser incluídas após localizar, auditar e verificar proveniência; não inventar nem gerar fixtures rotuladas como reais.
- Limites: branch de trabalho sem alterações de código até agora; nenhuma integração parser→swap, persistência dos contratos, validação com fixture real ou execução financeira foi concluída. SMR permanece somente leitura.

## 14. Atualização 2026-11-18 — plano técnico Raydium e persistência

- Criado `docs/RAYDIUM-SWAP-INTEGRATION-PLAN.md` na branch `feat/raydium-swap-reconciliation`.
- Commit do plano: `2ec79b53474815d6b96e2fb0d98de11e5fed31d0`.
- O documento registra o fluxo proposto de instruções externas/CPI → decodificação por programa → reconciliação com deltas → `SwapObservation`/`SwapClassification`/`SwapEvidence` → persistência SQLite atômica.
- Também define princípios conservadores (`UNKNOWN` em ambiguidade), idempotência, replay, proveniência de fixtures, plano de testes e sequência de implementação.
- A revisão do código remoto confirma que `normalization.py` hoje produz envelope, eventos legados e deltas SPL; `event_store.py` já persiste esses dados e permite replay. A persistência dedicada dos três contratos ainda não existe.
- **Estado desta entrega:** documentação de planejamento criada; nenhum módulo Raydium local foi transferido ou integrado; nenhum runtime, parser ou esquema SQLite foi alterado; nenhum teste foi executado por causa deste documento.
- Próxima ação permanece: transferir os módulos e testes locais para revisão controlada. Após isso, implementar adaptadores e reconciliação em etapas pequenas, sem substituir arquivos remotos inteiros.
- Limites preservados: branch isolada, `main` intacta, V1 somente leitura, sem RPC pago ou execução financeira.

## 15. Atualização 2026-11-18 — persistência dos três contratos (em revisão)

- Implementada na branch a migração incremental de três tabelas: `swap_observations`, `swap_classifications` e `swap_evidence`.
- Adicionados `SQLiteEventStore.save_swap_bundle()` e `get_swap_bundle()`: gravam/recuperam os três contratos em uma transação SQLite, mantêm quantidades/confiança como Decimal textual, serializam caminho CPI/evidências em JSON e fazem upsert idempotente por `operation_id`.
- A gravação exige que a transação pai já exista em `observed_transactions`, que os três contratos compartilhem o mesmo ID e que o ID corresponda ao helper determinístico `build_swap_operation_id(chain, signature, instruction_index, cpi_path)`.
- Criado `tests/test_swap_persistence.py` com cobertura de round-trip, precisão decimal, idempotência, divergência de IDs e ausência da transação pai.
- CI do commit `d090b9d973e297834b8edb3a29d1132b9e603811`: workflow `SMR tests` passou; 102 testes aprovados e `compileall` aprovado. Essa execução ocorreu antes da validação adicional de identidade determinística; os commits posteriores estão aguardando a execução de CI atualizada.
- PR #2 aberto como draft: [Draft: persist separated swap contracts in SQLite](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/2). Não foi mesclado; `main` permanece intacta.
- Commits posteriores adicionaram validação determinística do `operation_id` e ajustaram os testes para usar o helper real. A validação dessa revisão ainda depende do próximo resultado CI.
- Limite importante: a persistência está implementada como API do EventStore, mas ainda não está conectada ao pipeline de reconstrução de swaps; não há decodificação Raydium integrada nem fixture mainnet real aprovada.
- Próxima tarefa: confirmar CI do commit mais recente e revisar eventuais falhas; em seguida, trazer os módulos locais Raydium e testes para integrar o produtor dos contratos.

## 16. Atualização 2026-11-18 — validação da persistência e estado do PR #2

- CI atualizado para o commit `07fa7739b997cabf5b1cdda121b9c7f6c53b5617`: workflow `SMR tests` aprovado; **104 testes passaram** e `python -m compileall -q src tests` passou. Execução: [GitHub Actions](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44217615420).
- Os dois testes adicionais cobrem: rejeição de `operation_id` não determinístico e rollback integral quando a inserção de evidência falha. Isso confirma atomicidade do bundle na suíte automatizada.
- PR #2 continua aberto como draft, não mesclado, com estado mergeable reportado pelo GitHub: [PR #2](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/2).
- Correção de histórico operacional: uma atualização de teste foi enviada por engano à `main` sem indicar a branch; o arquivo foi imediatamente removido em commit corretivo. Comparação da árvore entre o SHA-base anterior e a `main` confirmou **nenhuma diferença de arquivos** (árvore de trabalho restaurada), mas a `main` contém dois commits adicionais de criação/remoção. A branch de trabalho está 2 commits atrás e 12 à frente da `main`; PR permanece mergeable. Não houve alteração persistente de código/arquivos na `main`.
- O CI de 104 testes é validação do código de persistência e testes existentes; não valida decodificadores Raydium, reconstrução econômica nem fixtures mainnet.
- Estado técnico: persistência dedicada implementada e validada em CI; ainda não conectada ao parser/normalizador que produzirá swaps reais.
- Próxima tarefa: revisar e integrar os módulos Raydium locais e os respectivos testes. Não mesclar PR #2 até revisão técnica completa e confirmação do estado da branch/base.

## 17. Atualização 2026-11-18 — branch limpa e PR de persistência validado

- Para eliminar a divergência de histórico criada pelos commits corretivos de criação/remoção do arquivo de teste na `main`, foi criada uma branch limpa diretamente da `main` atual: `feat/swap-contract-persistence`.
- Os quatro arquivos de trabalho foram reaplicados nessa branch, sem alterar o conteúdo-base da `main`: `REGISTRO-MESTRE-SMR.md`, `docs/RAYDIUM-SWAP-INTEGRATION-PLAN.md`, `src/smart_money_radar/storage/event_store.py` e `tests/test_swap_persistence.py`.
- Comparação confirmada: branch limpa **4 commits à frente e 0 atrás** da `main` no momento da criação; o diff contém somente os quatro arquivos acima.
- PR #2 foi fechado sem merge por estar baseado no histórico anterior. PR #3 foi aberto como draft, baseado na `main` atual: [Draft: persist separated swap contracts in SQLite](https://github.com/Zapatta22/SMART-MONEY-RADAR/pull/3).
- CI na branch limpa, commit `1c2c45018b439d60e427182143f4558e744560fe`: **104 testes aprovados**, `compileall` aprovado. Execução: [GitHub Actions](https://github.com/Zapatta22/SMART-MONEY-RADAR/actions/runs/44217759046).
- A `main` contém dois commits corretivos de criação/remoção do arquivo de teste; a comparação da árvore antes/depois confirmou que não há diferença de arquivos. O PR #3 parte do HEAD atual da `main`, sem divergência de commits.
- Persistência dos três contratos está implementada e validada em CI. Ela ainda não está ligada a um reconstrutor real de swaps; Raydium continua aguardando a transferência/revisão dos módulos locais.
- Próxima ação técnica: revisar os módulos Raydium CPMM/AMM v4 e seus testes, então conectar a saída do reconciliador a `save_swap_bundle()`. Não mesclar PR #3 até concluir revisão.
