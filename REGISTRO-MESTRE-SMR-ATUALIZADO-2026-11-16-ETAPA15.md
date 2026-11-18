# SMART MONEY RADAR (SMR) — REGISTRO MESTRE
Última atualização: 2026-11-16 — Etapa 15

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

Executar o coletor Etapa 11 em ambiente com RPC HTTPS acessível e autorizado, usando as cinco assinaturas candidatas; auditar cada resposta finalized com o auditor Etapa 12; revisar manualmente instruções, CPI, signers, token accounts, pools/vaults e contas de protocolo; rodar o anonimizador Etapa 13 com `--protect` completo; verificar hashes, aliases e mapa confidencial; aprovar a primeira fixture real. Só depois implementar o primeiro decodificador do programa correspondente à fixture aprovada.

## 10. Protocolo de continuidade

Usar este registro e `SMR-CODIGO-BASE-ETAPA13-2026-11-16.zip` como referência mais recente. Separar especificado, implementado, testado, validado remotamente e produção. Não declarar coleta/fixture real concluída até existir payload RPC integral finalized, hash conferido, proveniência e revisão semântica.


# Atualização de continuidade — Etapa 14 (2026-11-16)

## Estado da Etapa 14

**Preparação offline concluída; coleta RPC real bloqueada por DNS.**

- Os cinco candidatos mainnet da Etapa 10 foram consolidados em `data/fixtures/candidates/solana_mainnet_candidates.json`: Raydium CPMM, Raydium AMM v4, Jupiter v6, Meteora DLMM e Meteora DAMM v2.
- `tools/collect_solana_fixtures.py` agora aceita `--candidate-file`, valida a estrutura e deduplica assinaturas mantendo a ordem.
- Criado `tools/check_solana_rpc.py`, preflight somente leitura via `getHealth`, HTTPS obrigatório, timeout de 8 segundos e saída sem URL completa/credenciais.
- README atualizado com comandos de preflight e coleta em lote.
- Auditoria registrada em `AUDITORIA-ETAPA14-PREFLIGHT-COLETA-LOTE-2026-11-16.md`.
- Suíte completa: **88 testes aprovados, 0 falhas; 5 subtests aprovados**. Dois testes novos validam o catálogo e o caminho de lote/deduplicação.
- Teste real de conectividade: falha de DNS (`Temporary failure in name resolution`) ao acessar o RPC público. Nenhum payload real foi baixado; os cinco candidatos permanecem candidatos.

## Próxima tarefa pendente — coleta de evidências reais

Executar `PYTHONPATH=src python tools/check_solana_rpc.py` e, se aprovado, `PYTHONPATH=src python tools/collect_solana_fixtures.py --candidate-file data/fixtures/candidates/solana_mainnet_candidates.json --output data/fixtures/raw` em ambiente com RPC HTTPS gratuito/autorizado e DNS funcional. Depois auditar os manifestos com `tools/audit_solana_fixtures.py`, revisar programas/instruções/CPI/signers/token accounts/pools/vaults, anonimizar a projeção com a Etapa 13 e aprovar a primeira fixture real. Só então implementar o decodificador do protocolo correspondente.

## Limites inalterados

Nenhum endpoint pago, crédito Helius ou VPS sem autorização explícita. Nenhuma assinatura/envio de transação ou trade. Não tratar resumo de explorer ou payload sintético como fixture real. Não avançar para motores de decisão ou execução financeira.

## Referência de continuidade

Usar `SMR-CODIGO-BASE-ETAPA15-2026-11-16.zip` e este Registro Mestre atualizado. A Etapa 14 não deve ser descrita como coleta real concluída; somente a preparação offline foi implementada e testada.


# Atualização de continuidade — Etapa 15 (2026-11-16)

## Objetivo

Endurecer o coletor de evidências antes de voltar a executar chamadas RPC, sem contornar o bloqueio DNS e sem consumir serviços pagos.

## Alterações implementadas

- `src/smart_money_radar/data_sources/rpc_fixture_collector.py`: valida Base58 e tamanho decodificado de 64 bytes para cada assinatura antes de montar a requisição ou o nome do arquivo; rejeita resposta JSON cuja raiz não seja objeto; cria bruto e manifesto em modo exclusivo, executa `flush`/`fsync` e remove apenas o bruto criado pela chamada se a gravação do manifesto falhar.
- `tests/test_rpc_fixture_collector.py`: três testes adicionais para rejeição de assinatura inválida/path traversal antes da rede, raiz JSON inválida e conflito de manifesto sem deixar bruto órfão ou sobrescrever o manifesto.
- `README.md`: documentado o endurecimento e o limite da validação estrutural.

## Validação

- Testes direcionados do coletor e CLI de lote: 10 aprovados, 3 subtests aprovados.
- Suíte completa: 91 testes aprovados, 8 subtests aprovados, 0 falhas.
- `PYTHONPATH=src:. python -m compileall -q src tests tools`: aprovado.
- A validação Base58/64 bytes passou para as cinco assinaturas candidatas. Isso não comprova que as transações ainda estejam disponíveis nem que os metadados do explorer estejam corretos.

## Bloqueio externo mantido

O DNS do runtime não resolve `api.mainnet-beta.solana.com` (`socket.gaierror: [Errno -3] Temporary failure in name resolution`). Não foi possível executar `getHealth` nem `getTransaction`; nenhum payload mainnet foi coletado. Não houve uso de Helius, endpoint pago, créditos ou VPS.

## Próxima tarefa exata

Executar preflight e coleta dos cinco candidatos em ambiente com DNS funcional e RPC HTTPS gratuito/autorizado. Em seguida, auditar os manifestos, revisar semanticamente instruções/CPI/signers/token accounts/pools/vaults, anonimizar projeções com `--protect` completo e aprovar a primeira fixture real. Só depois iniciar o decodificador do protocolo comprovado pela fixture.

## Estado real do projeto

A Etapa 15 é endurecimento local do coletor; não altera o estado de implantação. O SMR permanece em preparação offline, somente leitura, sem fixture real aprovada e sem operação 24/7.
